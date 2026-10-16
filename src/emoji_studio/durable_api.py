"""Explicit opt-in local API factory. Default api.create_app remains unchanged.

Call create_app with a fresh database path and an explicitly selected renderer.
No listener, cloud worker or data migration is started by importing this module.
"""

import asyncio
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from .alpha import AccessPolicy, AlphaUser
from .api import FeedbackRequest, GenerationRequest
from .durable_worker import DurableWorker
from .service import Metrics, RetentionManager, create_seeds
from .worker_queue import Conflict, QuotaExceeded, WorkerQueue


def timestamp(value):
    return datetime.fromtimestamp(value, UTC).isoformat()


def public_job(job):
    result = {"id": job["id"], "status": job["status"], **job["payload"], "results": job["results"]}
    for key in ("request_id", "error"):
        if job[key] is not None:
            result[key] = job[key]
    for key in ("created_at", "updated_at", "started_at", "finished_at"):
        if job[key] is not None:
            result[key] = timestamp(job[key])
    return result


class RetentionStore:
    def __init__(self, store):
        self.store = store

    def delete_expired(self, cutoff):
        return self.store.delete_expired(datetime.fromisoformat(cutoff).timestamp())


class DurableRetention(RetentionManager):
    last_error = None

    async def _run(self):
        while not self._stopping.is_set():
            try:
                await asyncio.to_thread(self.cleanup)
                self.last_error = None
            except Exception as error:
                self.last_error = type(error).__name__
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass


def create_app(
    database_path,
    *,
    renderer,
    api_key=None,
    access_policy=None,
    trial_image_cap=100,
    retention_days=7,
    retention_interval_seconds=3600,
    worker_enabled=True,
    lease_seconds=60,
    poll_seconds=0.1,
    idle_unload_seconds=300,
    hourly_cost_dollars=0.0,
):
    policy = access_policy or AccessPolicy.single_key(api_key or "")
    store = WorkerQueue(database_path, trial_image_cap=trial_image_cap)
    metrics = Metrics()
    worker = DurableWorker(
        store,
        renderer,
        metrics,
        ttl=lease_seconds,
        poll_seconds=poll_seconds,
        idle_unload_seconds=idle_unload_seconds,
        hourly_cost=hourly_cost_dollars,
    )
    retention = DurableRetention(RetentionStore(store), retention_days, retention_interval_seconds)

    @asynccontextmanager
    async def lifespan(app):
        try:
            await retention.start()
            if worker_enabled:
                await worker.start()
            yield
        finally:
            try:
                await retention.stop()
            finally:
                if worker_enabled:
                    await worker.stop()

    app = FastAPI(
        title="Emoji Studio durable API (opt-in local)", version="0.3.0", lifespan=lifespan
    )
    app.state.store, app.state.worker = store, worker
    app.state.metrics, app.state.retention, app.state.access_policy = metrics, retention, policy

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(ValueError)
    async def storage_error(request, error):
        return JSONResponse({"detail": "Job storage temporarily unavailable"}, status_code=503)

    @app.middleware("http")
    async def request_ids(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied) else uuid.uuid4().hex
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def require_user(authorization: str | None = Header(default=None)):
        user = policy.authenticate(authorization)
        if user is None:
            raise HTTPException(
                401, "A valid bearer API key is required", headers={"WWW-Authenticate": "Bearer"}
            )
        return user

    def require_admin(user: AlphaUser = Depends(require_user)):
        if not user.admin:
            raise HTTPException(403, "Administrator access is required")
        return user

    async def owned(job_id, user):
        row = await asyncio.to_thread(store.get, job_id, user.id)
        if row is None:
            raise HTTPException(404, "Generation job not found")
        return row

    @app.get("/healthz")
    async def health():
        depth = await asyncio.to_thread(store.pending_count)
        return {
            "status": "degraded" if worker.last_error or retention.last_error else "ok",
            "renderer": type(renderer).__name__,
            "model_loaded": bool(renderer.loaded),
            "queue_depth": depth,
            "worker_enabled": worker_enabled,
            "storage": "sqlite",
        }

    @app.get("/v1/me")
    async def me(user: AlphaUser = Depends(require_user)):
        usage = await asyncio.to_thread(
            store.usage, user.id, daily_image_quota=user.daily_image_quota
        )
        usage["daily"]["resets_at"] = timestamp(usage["daily"]["resets_at"])
        return {
            "id": user.id,
            "admin": user.admin,
            "quota": usage["daily"],
            "trial": usage["trial"],
            "retention_days": retention_days,
        }

    @app.post("/v1/generations", status_code=202)
    async def create_generation(
        payload: GenerationRequest, request: Request, user: AlphaUser = Depends(require_user)
    ):
        allowed, retry = policy.allow_request(user)
        if not allowed:
            raise HTTPException(
                429, "Generation request rate limit reached", headers={"Retry-After": str(retry)}
            )
        prompts = payload.expanded_prompts()
        seeds, job_id = create_seeds(len(prompts), payload.seed), uuid.uuid4().hex
        try:
            await asyncio.to_thread(
                store.enqueue,
                job_id,
                user.id,
                prompts,
                seeds,
                daily_image_quota=user.daily_image_quota,
                request_id=request.state.request_id,
            )
        except QuotaExceeded as error:
            headers = (
                {"Retry-After": str(max(1, round(error.resets_at - time.time())))}
                if error.resets_at
                else None
            )
            detail = "Daily image quota" if error.scope == "daily" else "Private-alpha image cap"
            raise HTTPException(
                429,
                detail + f" reached; {max(0, error.limit - error.used)} remaining",
                headers=headers,
            ) from error
        metrics.record_job("queued")
        return public_job(await owned(job_id, user))

    @app.get("/v1/generations")
    async def list_generations(limit: int = 20, user: AlphaUser = Depends(require_user)):
        if not 1 <= limit <= 100:
            raise HTTPException(422, "Limit must be between 1 and 100")
        rows = await asyncio.to_thread(store.list, user.id, limit)
        return {"jobs": [public_job(row) for row in rows]}

    @app.get("/v1/generations/{job_id}")
    async def get_generation(job_id: str, user: AlphaUser = Depends(require_user)):
        return public_job(await owned(job_id, user))

    @app.get("/v1/generations/{job_id}/artifacts/{filename}")
    async def get_artifact(job_id: str, filename: str, user: AlphaUser = Depends(require_user)):
        await owned(job_id, user)
        content = await asyncio.to_thread(store.artifact, job_id, user.id, filename)
        if content is None:
            raise HTTPException(404, "Artifact not found")
        return Response(
            content,
            media_type="image/png" if filename.endswith(".png") else "image/webp",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/v1/generations/{job_id}/feedback", status_code=201)
    async def feedback(
        job_id: str, payload: FeedbackRequest, user: AlphaUser = Depends(require_user)
    ):
        try:
            result = await asyncio.to_thread(
                store.save_feedback, job_id, user.id, payload.rating, payload.comment
            )
        except Conflict as error:
            raise HTTPException(409, str(error)) from error
        if result is None:
            raise HTTPException(404, "Generation job not found")
        result["created_at"] = timestamp(result["created_at"])
        return result

    @app.delete("/v1/generations/{job_id}", status_code=204)
    async def delete_generation(job_id: str, user: AlphaUser = Depends(require_user)):
        try:
            deleted = await asyncio.to_thread(store.delete, job_id, user.id)
        except Conflict as error:
            raise HTTPException(409, str(error)) from error
        if not deleted:
            raise HTTPException(404, "Generation job not found")
        return Response(status_code=204)

    @app.get("/metrics", dependencies=[Depends(require_admin)])
    async def prometheus_metrics():
        return Response(metrics.prometheus(), media_type="text/plain; version=0.0.4")

    @app.get("/", include_in_schema=False)
    async def studio():
        return FileResponse(Path(__file__).parent / "studio.html", media_type="text/html")

    return app
