"""
Guardrail Aggregator Node — Consolidates all guardrail results.

Fan-in point for all parallel guardrail checks (story evaluator, story guardrail,
image guardrails ×N, video guardrails ×M). This node:
1. Collects all violations from the reducer field
2. Rebuilds sorted image/video URL lists from guardrail outputs
3. Computes overall pass/fail
4. Builds a human-readable summary for the reviewer
"""

from app.agents.state import StoryState
from app.constants import SEVERITY_HARD, SEVERITY_SOFT
import logging

logger = logging.getLogger(__name__)


def guardrail_aggregator_node(state: StoryState) -> dict:
    """
    Consolidate all guardrail violations and compute pass/fail.

    After fan-in, the state's ``guardrail_violations`` list contains
    violations from all parallel guardrail nodes. This node analyzes
    them and sets ``guardrail_passed`` + ``guardrail_summary``.
    """
    job_id = state.get("job_id", "unknown")
    violations = state.get("guardrail_violations", [])

    hard_violations = [v for v in violations if v.get("severity") == SEVERITY_HARD]
    soft_violations = [v for v in violations if v.get("severity") == SEVERITY_SOFT]

    # Rebuild sorted image/video URL lists from per-item guardrail outputs
    image_finals = sorted(
        state.get("image_urls_final", []),
        key=lambda x: x.get("index", 0),
    )
    video_finals = sorted(
        state.get("video_urls_final", []),
        key=lambda x: x.get("index", 0),
    )

    # Build human-readable summary
    summary_parts = []

    # Include evaluation scores if available
    eval_scores = state.get("evaluation_scores")
    if eval_scores:
        overall = eval_scores.get("overall_score", "N/A")
        summary_parts.append(f"Overall Quality Score: {overall}/10")
        eval_summary = eval_scores.get("evaluation_summary", "")
        if eval_summary:
            summary_parts.append(f"   {eval_summary}")
        summary_parts.append("")

    if hard_violations:
        summary_parts.append(f"{len(hard_violations)} HARD violation(s) — will trigger auto-reject:")
        for v in hard_violations:
            media_label = v.get("media_type", "unknown")
            if v.get("media_index") is not None:
                media_label += f" #{v['media_index']}"
            summary_parts.append(
                f"  - [{v.get('guardrail_name', '?')}] ({media_label}) "
                f"confidence={v.get('confidence', 0):.2f}: {v.get('detail', '')}"
            )

    if soft_violations:
        summary_parts.append(f"\n{len(soft_violations)} SOFT warning(s) — for reviewer awareness:")
        for v in soft_violations:
            media_label = v.get("media_type", "unknown")
            if v.get("media_index") is not None:
                media_label += f" #{v['media_index']}"
            summary_parts.append(
                f"  - [{v.get('guardrail_name', '?')}] ({media_label}): {v.get('detail', '')}"
            )

    if not violations:
        summary_parts.append("All guardrails passed — no violations detected.")

    passed = len(hard_violations) == 0

    logger.info(
        f"Job {job_id}: Guardrail aggregation complete — "
        f"passed={passed}, {len(hard_violations)} hard, {len(soft_violations)} soft, "
        f"{len(image_finals)} images, {len(video_finals)} videos"
    )

    if hard_violations:
        for v in hard_violations:
            logger.warning(
                f"Job {job_id}: [Aggregator] HARD violation — "
                f"[{v.get('guardrail_name', '?')}] "
                f"({v.get('media_type', '?')}#{v.get('media_index', '?')}) "
                f"confidence={v.get('confidence', 0):.2f}: {v.get('detail', '')}"
            )

    if soft_violations:
        for v in soft_violations:
            logger.info(
                f"Job {job_id}: [Aggregator] SOFT warning — "
                f"[{v.get('guardrail_name', '?')}] "
                f"({v.get('media_type', '?')}#{v.get('media_index', '?')}): "
                f"{v.get('detail', '')}"
            )

    logger.info(f"Job {job_id}: [Aggregator] Full summary:\n{chr(10).join(summary_parts)}")

    return {
        "guardrail_passed": passed,
        "guardrail_summary": "\n".join(summary_parts),
        # Overwrite image/video URLs with post-guardrail final URLs
        # (these may differ from originals if images were regenerated)
        "image_urls": [item["url"] for item in image_finals],
        "video_urls": [item["url"] for item in video_finals],
    }
