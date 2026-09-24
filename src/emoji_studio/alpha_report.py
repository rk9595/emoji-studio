from collections import Counter, defaultdict
from pathlib import Path

from .common import read_json


def summarize_alpha(jobs_root, criteria):
    jobs_root = Path(jobs_root)
    statuses = Counter()
    users = defaultdict(lambda: {"jobs": 0, "images_requested": 0, "images_succeeded": 0})
    feedback = Counter()
    generated = 0
    requested = 0
    total_seconds = 0.0
    total_cost = 0.0

    for path in jobs_root.glob("*/job.json"):
        job = read_json(path)
        status = job.get("status", "unknown")
        owner = job.get("owner_id", "default-admin")
        statuses[status] += 1
        image_count = len(job.get("seeds", []))
        requested += image_count
        users[owner]["jobs"] += 1
        users[owner]["images_requested"] += image_count
        for result in job.get("results", []):
            generated += 1
            users[owner]["images_succeeded"] += 1
            metrics = result.get("metrics", {})
            total_seconds += float(metrics.get("generation_seconds", 0.0))
            total_cost += float(metrics.get("estimated_cost_dollars", 0.0))
        feedback_path = path.parent / "feedback.json"
        if feedback_path.is_file():
            rating = read_json(feedback_path).get("rating", "invalid")
            feedback[rating] += 1

    terminal_jobs = statuses["succeeded"] + statuses["failed"]
    rated_jobs = feedback["up"] + feedback["down"]
    usable_fraction = feedback["up"] / rated_jobs if rated_jobs else None
    failure_fraction = statuses["failed"] / terminal_jobs if terminal_jobs else None
    cost_per_image = total_cost / generated if generated else None
    thresholds = criteria["success_criteria"]
    checks = {
        "usable_fraction": (
            usable_fraction is not None and usable_fraction >= thresholds["minimum_usable_fraction"]
        ),
        "failure_fraction": (
            failure_fraction is not None
            and failure_fraction <= thresholds["maximum_failure_fraction"]
        ),
        "warm_cost_per_image": (
            cost_per_image is not None
            and cost_per_image <= thresholds["maximum_warm_cost_per_image_dollars"]
        ),
        "trial_cap": requested <= criteria["trial_generation_cap"],
    }
    return {
        "schema_version": 1,
        "status": "ready_for_decision" if rated_jobs else "awaiting_feedback",
        "jobs": {"total": sum(statuses.values()), **dict(sorted(statuses.items()))},
        "images": {
            "requested": requested,
            "succeeded": generated,
            "generation_seconds": round(total_seconds, 6),
            "estimated_cost_dollars": round(total_cost, 8),
            "estimated_cost_per_image_dollars": (
                round(cost_per_image, 8) if cost_per_image is not None else None
            ),
        },
        "feedback": {
            "rated_jobs": rated_jobs,
            "up": feedback["up"],
            "down": feedback["down"],
            "usable_fraction": round(usable_fraction, 6) if usable_fraction is not None else None,
        },
        "failure_fraction": (round(failure_fraction, 6) if failure_fraction is not None else None),
        "participants": dict(sorted(users.items())),
        "criteria": thresholds,
        "checks": checks,
        "all_measured_checks_pass": bool(rated_jobs) and all(checks.values()),
    }


def markdown_report(report):
    images = report["images"]
    feedback = report["feedback"]
    lines = [
        "# Emoji Studio private-alpha results",
        "",
        f"Status: **{report['status']}**",
        "",
        f"- Participants: {len(report['participants'])}",
        f"- Jobs: {report['jobs']['total']}",
        f"- Images requested / succeeded: {images['requested']} / {images['succeeded']}",
        f"- Rated jobs: {feedback['rated_jobs']}",
        f"- Positive / negative feedback: {feedback['up']} / {feedback['down']}",
        f"- Usable fraction: {_percentage(feedback['usable_fraction'])}",
        f"- Failure fraction: {_percentage(report['failure_fraction'])}",
        "- Estimated warm generation cost per image: "
        f"{_money(images['estimated_cost_per_image_dollars'])}",
        "",
        "## Decision checks",
        "",
    ]
    for name, passed in report["checks"].items():
        lines.append(f"- {'PASS' if passed else 'NOT YET'} — {name.replace('_', ' ')}")
    lines.extend(
        [
            "",
            "The usable fraction only includes jobs with explicit thumbs-up/down feedback. "
            "Treat low feedback coverage as incomplete evidence, even if the measured checks pass.",
            "",
        ]
    )
    return "\n".join(lines)


def _percentage(value):
    return "not measured" if value is None else f"{value:.1%}"


def _money(value):
    return "not measured" if value is None else f"${value:.4f}"
