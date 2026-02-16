"""
Story Guardrail Node — Multi-layer text safety checks.

Three layers:

Layer 0 — OpenAI Moderation API (fast ~50ms, no LLM cost)
    Catches: violence, sexual, self-harm, hate, harassment.

Layer 1 — PII Detection (regex)
    Catches: emails, phone numbers, SSNs, credit card numbers.

Layer 2 — LLM Deep Safety Analysis (custom prompts)
    Domain-specific kids content: fear intensity, brand mentions,
    political content, religious references, violence severity.

Produces a list of guardrail violation dicts appended to state via reducer.
"""

from app.agents.state import StoryState
from app.services.moderation import (
    check_openai_moderation,
    detect_pii,
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

    logger.info(
        f"Job {job_id}: Running story text guardrails (3-layer pipeline) "
        f"on story ({len(story_text)} chars, age_group={age_group}): "
        f"{story_text[:300]}..."
    )

    # ── Layer 0: OpenAI Moderation API (fast) ──
    openai_violations = check_openai_moderation(story_text)
    violations.extend(openai_violations)
    if openai_violations:
        logger.warning(
            f"Job {job_id}: [L0-OpenAI] FLAGGED — "
            f"{'; '.join(v['detail'] for v in openai_violations)}"
        )
    else:
        logger.info(f"Job {job_id}: [L0-OpenAI] Passed")

    # ── Layer 1: PII detection (regex) ──
    pii_violations = detect_pii(story_text)
    violations.extend(pii_violations)
    if pii_violations:
        logger.warning(
            f"Job {job_id}: [L1-PII] FLAGGED — "
            f"{'; '.join(v['detail'] for v in pii_violations)}"
        )
    else:
        logger.info(f"Job {job_id}: [L1-PII] Passed")

    # ── Layer 2: LLM deep safety analysis ──
    text_safety = check_text_safety(story_text, age_group)
    text_violations = build_text_violations(text_safety, media_type="story")
    violations.extend(text_violations)
    if text_violations:
        logger.warning(
            f"Job {job_id}: [L2-LLM] FLAGGED — "
            f"{'; '.join(v['detail'] for v in text_violations)}"
        )
    else:
        logger.info(f"Job {job_id}: [L2-LLM] Passed")
    
    # Explicitly clear the Pydantic model reference to prevent serialization issues
    # with LangGraph's checkpointer (similar to story_writer.py)
    del text_safety

    hard_count = sum(1 for v in violations if v["severity"] == "hard")
    soft_count = sum(1 for v in violations if v["severity"] == "soft")

    logger.info(
        f"Job {job_id}: Story guardrail complete — "
        f"{hard_count} hard, {soft_count} soft violation(s) "
        f"(L0:openai={len(openai_violations)}, "
        f"L1:pii={len(pii_violations)}, "
        f"L2:llm={len(text_violations)})"
    )

    return {
        "guardrail_violations": violations,
        "image_urls_final": [],
        "video_urls_final": [],
    }
