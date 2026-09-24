import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from .alpha import AccessPolicy, AlphaUser
from .common import now
from .service import (
    FluxRenderer,
    GenerationWorker,
    JobStore,
    Metrics,
    MockRenderer,
    RetentionManager,
    VastServerlessRenderer,
    WorkerSettings,
    create_seeds,
)


class GenerationRequest(BaseModel):
    prompt: str | None = Field(default=None, min_length=1, max_length=500)
    prompts: list[str] | None = Field(default=None, min_length=1, max_length=16)
    variations: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def validate_mode(self):
        if (self.prompt is None) == (self.prompts is None):
            raise ValueError("Provide exactly one of prompt or prompts")
        if self.prompts is not None and self.variations != 1:
            raise ValueError("Pack requests use one deterministic image per prompt")
        if self.prompts is not None:
            cleaned = [prompt.strip() for prompt in self.prompts]
            if any(not prompt or len(prompt) > 500 for prompt in cleaned):
                raise ValueError("Every pack prompt must contain 1 to 500 characters")
            self.prompts = cleaned
        if self.prompt is not None:
            self.prompt = self.prompt.strip()
            if not self.prompt:
                raise ValueError("Prompt cannot be blank")
        return self

    def expanded_prompts(self):
        return self.prompts or [self.prompt] * self.variations


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    comment: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def clean_comment(self):
        self.comment = self.comment.strip()
        return self


def public_job(job):
    return {
        key: job.get(key)
        for key in [
            "id",
            "request_id",
            "status",
            "prompts",
            "seeds",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
            "results",
            "error",
        ]
        if job.get(key) is not None
    }


def create_app(
    root=None,
    *,
    api_key=None,
    renderer=None,
    jobs_dir=None,
    hourly_cost_dollars=0.0,
    idle_unload_seconds=300.0,
    access_policy=None,
    retention_days=7,
    retention_interval_seconds=3600,
    trial_image_cap=100,
):
    root = Path(root or Path.cwd()).resolve()
    api_key = api_key if api_key is not None else os.environ.get("EMOJI_STUDIO_API_KEY", "")
    access_policy = access_policy or AccessPolicy.single_key(api_key)
    store = JobStore(jobs_dir or root / "var/jobs")
    metrics = Metrics()
    if renderer is None:
        renderer_name = os.environ.get("EMOJI_STUDIO_RENDERER", "flux")
        if renderer_name == "mock":
            renderer = MockRenderer()
        elif renderer_name == "flux":
            renderer = FluxRenderer(root, root / "configs/serving.json")
        elif renderer_name == "vast-serverless":
            renderer = VastServerlessRenderer()
        else:
            raise ValueError("EMOJI_STUDIO_RENDERER must be 'flux', 'vast-serverless', or 'mock'")
    worker = GenerationWorker(
        store,
        renderer,
        metrics,
        WorkerSettings(
            hourly_cost_dollars=hourly_cost_dollars,
            idle_unload_seconds=idle_unload_seconds,
        ),
    )
    retention = RetentionManager(store, retention_days, retention_interval_seconds)
    if not 1 <= trial_image_cap <= 100_000:
        raise ValueError("Trial image cap must be between 1 and 100000")

    @asynccontextmanager
    async def lifespan(app):
        await worker.start()
        await retention.start()
        yield
        await retention.stop()
        await worker.stop()

    app = FastAPI(
        title="Emoji Studio API",
        version="0.2.0",
        description="Queued, deterministic single-GPU emoji and sticker generation.",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.worker = worker
    app.state.metrics = metrics
    app.state.access_policy = access_policy
    app.state.retention = retention

    @app.middleware("http")
    async def request_ids(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied) else uuid.uuid4().hex
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    def require_user(authorization: str | None = Header(default=None)):
        user = access_policy.authenticate(authorization)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid bearer API key is required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    def require_admin(user: AlphaUser = Depends(require_user)):
        if not user.admin:
            raise HTTPException(status_code=403, detail="Administrator access is required")
        return user

    def owned_job(job_id, user):
        job = store.get(job_id)
        if job is None or job.get("owner_id", "default-admin") != user.id:
            raise HTTPException(status_code=404, detail="Generation job not found")
        return job

    def usage(user):
        midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        used = store.images_created_since(user.id, midnight.isoformat())
        return {
            "used": used,
            "limit": user.daily_image_quota,
            "remaining": max(0, user.daily_image_quota - used),
            "resets_at": (midnight + timedelta(days=1)).isoformat(),
        }

    def trial_usage():
        used = store.total_images_created()
        return {
            "used": used,
            "limit": trial_image_cap,
            "remaining": max(0, trial_image_cap - used),
        }

    @app.get("/healthz")
    async def health():
        return {
            "status": "ok",
            "renderer": type(renderer).__name__,
            "model_loaded": bool(renderer.loaded),
            "queue_depth": worker.queue.qsize(),
        }

    @app.get("/v1/me")
    async def me(user: AlphaUser = Depends(require_user)):
        return {
            "id": user.id,
            "admin": user.admin,
            "quota": usage(user),
            "trial": trial_usage(),
            "retention_days": retention.retention_days,
        }

    @app.post(
        "/v1/generations",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_generation(
        payload: GenerationRequest,
        request: Request,
        user: AlphaUser = Depends(require_user),
    ):
        prompts = payload.expanded_prompts()
        allowed, retry_after = access_policy.allow_request(user)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Generation request rate limit reached",
                headers={"Retry-After": str(retry_after)},
            )
        quota = usage(user)
        if len(prompts) > quota["remaining"]:
            retry_after = max(
                1,
                round(
                    (datetime.fromisoformat(quota["resets_at"]) - datetime.now(UTC)).total_seconds()
                ),
            )
            raise HTTPException(
                status_code=429,
                detail=f"Daily image quota reached; {quota['remaining']} remaining",
                headers={"Retry-After": str(retry_after)},
            )
        trial = trial_usage()
        if len(prompts) > trial["remaining"]:
            raise HTTPException(
                status_code=429,
                detail=f"Private-alpha image cap reached; {trial['remaining']} remaining",
            )
        seeds = create_seeds(len(prompts), payload.seed)
        job = store.create(prompts, seeds, request.state.request_id, owner_id=user.id)
        metrics.record_job("queued")
        await worker.enqueue(job["id"])
        return public_job(job)

    @app.get("/v1/generations")
    async def list_generations(
        limit: int = 20,
        user: AlphaUser = Depends(require_user),
    ):
        if not 1 <= limit <= 100:
            raise HTTPException(status_code=422, detail="Limit must be between 1 and 100")
        return {"jobs": [public_job(job) for job in store.list(user.id, limit)]}

    @app.get("/v1/generations/{job_id}")
    async def get_generation(job_id: str, user: AlphaUser = Depends(require_user)):
        return public_job(owned_job(job_id, user))

    @app.get(
        "/v1/generations/{job_id}/artifacts/{filename}",
    )
    async def get_artifact(
        job_id: str,
        filename: str,
        user: AlphaUser = Depends(require_user),
    ):
        owned_job(job_id, user)
        path = store.artifact(job_id, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        media_type = "image/png" if path.suffix == ".png" else "image/webp"
        return FileResponse(path, media_type=media_type, filename=filename)

    @app.post("/v1/generations/{job_id}/feedback", status_code=201)
    async def create_feedback(
        job_id: str,
        payload: FeedbackRequest,
        user: AlphaUser = Depends(require_user),
    ):
        job = owned_job(job_id, user)
        if job["status"] != "succeeded":
            raise HTTPException(status_code=409, detail="Feedback requires a succeeded job")
        feedback = {
            "job_id": job_id,
            "owner_id": user.id,
            "rating": payload.rating,
            "comment": payload.comment,
            "created_at": now(),
        }
        store.save_feedback(job_id, user.id, feedback)
        return feedback

    @app.delete("/v1/generations/{job_id}", status_code=204)
    async def delete_generation(job_id: str, user: AlphaUser = Depends(require_user)):
        owned_job(job_id, user)
        try:
            deleted = store.delete(job_id, user.id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not deleted:
            raise HTTPException(status_code=404, detail="Generation job not found")
        return Response(status_code=204)

    @app.get("/metrics", dependencies=[Depends(require_admin)])
    async def prometheus_metrics():
        return Response(metrics.prometheus(), media_type="text/plain; version=0.0.4")

    frontend = Path(__file__).parent / "studio.html"

    @app.get("/", include_in_schema=False)
    async def studio():
        return FileResponse(frontend, media_type="text/html")

    return app


def main():
    import uvicorn

    api_key = os.environ.get("EMOJI_STUDIO_API_KEY")
    users_file = os.environ.get("EMOJI_STUDIO_USERS_FILE")
    if not api_key and not users_file:
        raise SystemExit("Set EMOJI_STUDIO_API_KEY or EMOJI_STUDIO_USERS_FILE")
    root = Path(os.environ.get("EMOJI_STUDIO_ROOT", Path.cwd())).resolve()
    hourly_cost = float(os.environ.get("EMOJI_STUDIO_HOURLY_COST_DOLLARS", "0"))
    idle_seconds = float(os.environ.get("EMOJI_STUDIO_IDLE_UNLOAD_SECONDS", "300"))
    retention_days = int(os.environ.get("EMOJI_STUDIO_RETENTION_DAYS", "7"))
    trial_image_cap = int(os.environ.get("EMOJI_STUDIO_TRIAL_IMAGE_CAP", "100"))
    access_policy = AccessPolicy.from_file(users_file) if users_file else None
    app = create_app(
        root,
        api_key=api_key,
        hourly_cost_dollars=hourly_cost,
        idle_unload_seconds=idle_seconds,
        access_policy=access_policy,
        retention_days=retention_days,
        trial_image_cap=trial_image_cap,
    )
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), workers=1)


if __name__ == "__main__":
    main()
