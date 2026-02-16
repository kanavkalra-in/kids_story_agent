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
    
    # Validate count matches expected number of illustrations
    expected_count = state.get("num_illustrations")
    if expected_count is not None:
        if len(image_finals) > expected_count:
            logger.warning(
                f"Job {job_id}: Guardrail aggregator found {len(image_finals)} image(s) "
                f"but expected {expected_count}. Truncating to {expected_count}."
            )
            image_finals = image_finals[:expected_count]
        elif len(image_finals) < expected_count:
            logger.warning(
                f"Job {job_id}: Guardrail aggregator found {len(image_finals)} image(s) "
                f"but expected {expected_count}. This may indicate missing guardrail outputs."
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

    # CRITICAL FIX: image_urls and video_urls are reducer fields.
    # When we return them, LangGraph will ADD them to existing state (not replace).
    # This causes duplicates - e.g., if state has [url1] and we return [url1],
    # it becomes [url1, url1].
    #
    # The solution: Don't return reducer fields from the aggregator.
    # The final URLs are already in image_urls_final/video_urls_final (reducer fields
    # populated by guardrail nodes). For database persistence, we'll read from
    # image_urls_final instead of image_urls.
    #
    # However, we need the final URLs for later nodes. The proper solution is to
    # use non-reducer fields, but that would require changing the state schema.
    # For now, we'll NOT return them and let the persistence layer read from
    # image_urls_final instead.
    
    logger.info(
        f"Job {job_id}: [Aggregator] Final URLs - {len(image_finals)} images, {len(video_finals)} videos. "
        f"These are in image_urls_final/video_urls_final. NOT returning image_urls/video_urls "
        f"to avoid reducer field duplication."
    )
    
    return {
        "guardrail_passed": passed,
        "guardrail_summary": "\n".join(summary_parts),
        # Do NOT return image_urls/video_urls - they are reducer fields and would be added
        # instead of replaced, causing duplicates. The final URLs are in image_urls_final.
    }
