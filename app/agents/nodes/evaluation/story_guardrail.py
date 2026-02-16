"""
Story Guardrail Node — Text safety checks.

Runs two layers of detection:
1. Fast regex-based PII scanning (emails, phones, SSNs, credit cards)
2. LLM-based deep analysis (violence, fear, political, brand, religious)

Produces a list of guardrail violation dicts appended to state via reducer.
"""

from app.agents.state import StoryState
from app.services.moderation import (
    detect_pii_regex,
    check_text_safety,
    build_text_violations,
)
import logging

logger = logging.getLogger(__name__)


def story_guardrail_node(state: StoryState) -> dict:
    """
    Run all text-based guardrails on the story content.

    Invoked via LangGraph ``Send`` — runs in parallel with evaluator
    and media guardrail nodes.
    """
    job_id = state.get("job_id", "unknown")
    story_text = state.get("story_text", "")
    age_group = state.get("age_group", "6-8")
    violations = []

    logger.info(f"Job {job_id}: Running story text guardrails")

    # ── Layer 1: Fast regex PII detection ──
    pii_violations = detect_pii_regex(story_text)
    violations.extend(pii_violations)
    if pii_violations:
        logger.warning(f"Job {job_id}: PII detected — {len(pii_violations)} violation(s)")

    # ── Layer 2: LLM deep safety analysis ──
    text_safety = check_text_safety(story_text, age_group)
    text_violations = build_text_violations(text_safety, media_type="story")
    violations.extend(text_violations)

    hard_count = sum(1 for v in violations if v["severity"] == "hard")
    soft_count = sum(1 for v in violations if v["severity"] == "soft")

    logger.info(
        f"Job {job_id}: Story guardrail complete — "
        f"{hard_count} hard, {soft_count} soft violation(s)"
    )

    return {
        "guardrail_violations": violations,
        # Story guardrail doesn't produce media URL finals
        "image_urls_final": [],
        "video_urls_final": [],
    }
