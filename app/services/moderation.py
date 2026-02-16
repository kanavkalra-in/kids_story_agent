"""
Shared moderation utilities used by guardrail nodes.

Provides:
- Regex-based PII detection (fast, no API cost)
- LLM-based text safety analysis
- Vision-based image safety analysis (via existing LLM or OpenAI omni-moderation fallback)
"""

import re
import asyncio
import logging
from typing import List

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.constants import PII_PATTERNS, SEVERITY_HARD, SEVERITY_SOFT

logger = logging.getLogger(__name__)


# ── Pydantic models for structured LLM output ──


class TextSafetyOutput(BaseModel):
    """LLM-analyzed safety flags for text content."""
    violence_detected: bool = False
    violence_severity: float = Field(default=0.0, ge=0, le=1)
    fear_intensity: float = Field(default=0.0, ge=0, le=1)
    political_content_detected: bool = False
    political_detail: str = ""
    brand_mentions_found: List[str] = []
    religious_references_detected: bool = False
    religious_detail: str = ""
    overall_explanation: str = ""


class ImageSafetyOutput(BaseModel):
    """Vision LLM output for image safety analysis."""
    nsfw_detected: bool = False
    nsfw_confidence: float = Field(default=0.0, ge=0, le=1)
    weapon_detected: bool = False
    weapon_confidence: float = Field(default=0.0, ge=0, le=1)
    realistic_human_child: bool = False
    realistic_child_confidence: float = Field(default=0.0, ge=0, le=1)
    horror_elements: bool = False
    horror_confidence: float = Field(default=0.0, ge=0, le=1)
    is_safe_for_children: bool = True
    explanation: str = ""


# ── System prompts ──

TEXT_SAFETY_SYSTEM_PROMPT = """You are a children's content safety moderator.
Analyze the text for the following safety concerns:

1. Violence: Any physical harm, fighting, weapons, threats (even fantasy violence)
2. Fear intensity: Scary elements, monsters, dark themes, abandonment, death
3. Political content: Political figures, parties, ideologies, propaganda
4. Brand mentions: Real company/product names (Disney, Nike, McDonald's, etc.)
5. Religious references: Specific religious figures, practices, texts, holidays

Score violence_severity and fear_intensity from 0.0 (none) to 1.0 (extreme).
Be thorough — this content is for children aged {age_group}.
If something is borderline, err on the side of caution and flag it."""


IMAGE_SAFETY_SYSTEM_PROMPT = """You are a children's content image safety moderator.
Analyze this image for the following safety concerns:

1. NSFW content: nudity, sexual content, graphic content of any kind
2. Weapons: guns, knives, swords, bombs, any type of weapon
3. Realistic human children: photorealistic depictions of real children (AI-generated realistic faces)
4. Horror elements: gore, blood, skeletons, genuinely scary monsters, dark/disturbing imagery

This image was generated for a children's story platform targeting ages {age_group}.
Be thorough and strict. Score confidence from 0.0 (definitely not present) to 1.0 (clearly present).
If the image is in a cartoon/illustration style and is generally wholesome, mark is_safe_for_children as true."""


# ── PII Detection (regex-based, fast) ──


def detect_pii_regex(text: str) -> List[dict]:
    """
    Fast regex-based PII detection. Returns a list of violation dicts.
    No API calls — pure string matching.
    """
    violations = []
    for pii_type, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            violations.append({
                "guardrail_name": "pii_detection",
                "media_type": "story",
                "media_index": None,
                "severity": SEVERITY_HARD,
                "confidence": 1.0,
                "detail": f"PII detected ({pii_type}): {len(matches)} occurrence(s)",
            })
    return violations


# ── Text Safety Analysis (via existing LLM) ──


def check_text_safety(text: str, age_group: str = "6-8") -> TextSafetyOutput:
    """
    Analyze text for safety concerns using the existing configured LLM.
    Synchronous — call from sync nodes or wrap in asyncio.to_thread.
    """
    from app.services.llm import get_llm

    llm = get_llm()
    structured_llm = llm.with_structured_output(TextSafetyOutput)
    output = structured_llm.invoke([
        SystemMessage(content=TEXT_SAFETY_SYSTEM_PROMPT.format(age_group=age_group)),
        HumanMessage(content=text),
    ])
    return output


async def check_text_safety_async(text: str, age_group: str = "6-8") -> TextSafetyOutput:
    """Async wrapper around check_text_safety."""
    return await asyncio.to_thread(check_text_safety, text, age_group)


# ── Image Safety Analysis (via existing Vision LLM or omni-moderation fallback) ──


def check_image_safety(image_url: str, age_group: str = "6-8") -> ImageSafetyOutput:
    """
    Check image safety using the existing LLM with vision support.
    Falls back to OpenAI omni-moderation if the LLM doesn't support vision (e.g., Ollama).
    """
    if settings.llm_provider in ("openai", "anthropic"):
        return _check_image_via_vision_llm(image_url, age_group)
    else:
        return _check_image_via_omni_moderation(image_url)


async def check_image_safety_async(image_url: str, age_group: str = "6-8") -> ImageSafetyOutput:
    """Async wrapper around check_image_safety."""
    return await asyncio.to_thread(check_image_safety, image_url, age_group)


def _check_image_via_vision_llm(image_url: str, age_group: str) -> ImageSafetyOutput:
    """Use the existing LLM (GPT-4o / Claude) with vision input."""
    from app.services.llm import get_llm

    llm = get_llm()
    structured_llm = llm.with_structured_output(ImageSafetyOutput)
    output = structured_llm.invoke([
        SystemMessage(content=IMAGE_SAFETY_SYSTEM_PROMPT.format(age_group=age_group)),
        HumanMessage(content=[
            {"type": "text", "text": "Analyze this image for children's content safety:"},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]),
    ])
    return output


def _check_image_via_omni_moderation(image_url: str) -> ImageSafetyOutput:
    """Fallback: OpenAI omni-moderation API for LLMs without vision support."""
    from app.services.openai_client import get_openai_client

    try:
        client = get_openai_client()
        moderation = client.moderations.create(
            model="omni-moderation-latest",
            input=[{"type": "image_url", "image_url": {"url": image_url}}],
        )
        result = moderation.results[0]
        cats = result.categories
        scores = result.category_scores

        return ImageSafetyOutput(
            nsfw_detected=getattr(cats, "sexual", False) or getattr(cats, "sexual/minors", False),
            nsfw_confidence=max(
                getattr(scores, "sexual", 0.0),
                getattr(scores, "sexual/minors", 0.0),
            ),
            weapon_detected=getattr(cats, "violence", False),
            weapon_confidence=getattr(scores, "violence", 0.0),
            realistic_human_child=False,
            realistic_child_confidence=0.0,
            horror_elements=getattr(cats, "violence/graphic", False),
            horror_confidence=getattr(scores, "violence/graphic", 0.0),
            is_safe_for_children=not any([
                getattr(cats, "sexual", False),
                getattr(cats, "violence", False),
                getattr(cats, "violence/graphic", False),
                getattr(cats, "sexual/minors", False),
            ]),
            explanation="Checked via OpenAI omni-moderation API",
        )
    except Exception as e:
        logger.error(f"Omni-moderation fallback failed: {e}")
        # If moderation API fails, flag as unsafe to be safe
        return ImageSafetyOutput(
            nsfw_detected=False,
            is_safe_for_children=True,
            explanation=f"Moderation API unavailable: {e}. Defaulting to safe.",
        )


def build_text_violations(
    output: TextSafetyOutput,
    media_type: str = "story",
    media_index: int = None,
) -> List[dict]:
    """Convert a TextSafetyOutput into a list of guardrail violation dicts."""
    violations = []

    if output.violence_detected:
        violations.append({
            "guardrail_name": "violence_detection",
            "media_type": media_type,
            "media_index": media_index,
            "severity": (
                SEVERITY_HARD
                if output.violence_severity > settings.guardrail_violence_hard_threshold
                else SEVERITY_SOFT
            ),
            "confidence": output.violence_severity,
            "detail": f"Violence detected (severity: {output.violence_severity:.2f}). {output.overall_explanation}",
        })

    if output.fear_intensity > settings.guardrail_fear_threshold:
        violations.append({
            "guardrail_name": "fear_intensity",
            "media_type": media_type,
            "media_index": media_index,
            "severity": SEVERITY_HARD if output.fear_intensity > 0.7 else SEVERITY_SOFT,
            "confidence": output.fear_intensity,
            "detail": (
                f"Fear intensity ({output.fear_intensity:.2f}) exceeds "
                f"threshold ({settings.guardrail_fear_threshold})"
            ),
        })

    if output.political_content_detected:
        violations.append({
            "guardrail_name": "political_content",
            "media_type": media_type,
            "media_index": media_index,
            "severity": SEVERITY_HARD,
            "confidence": 1.0,
            "detail": f"Political content: {output.political_detail}",
        })

    if output.brand_mentions_found:
        violations.append({
            "guardrail_name": "brand_mentions",
            "media_type": media_type,
            "media_index": media_index,
            "severity": SEVERITY_SOFT,
            "confidence": 0.9,
            "detail": f"Brand mentions found: {', '.join(output.brand_mentions_found)}",
        })

    if output.religious_references_detected:
        violations.append({
            "guardrail_name": "religious_references",
            "media_type": media_type,
            "media_index": media_index,
            "severity": SEVERITY_SOFT,
            "confidence": 0.9,
            "detail": f"Religious references: {output.religious_detail}",
        })

    return violations


def build_image_violations(
    output: ImageSafetyOutput,
    media_index: int = 0,
    media_type: str = "image",
) -> List[dict]:
    """Convert an ImageSafetyOutput into a list of guardrail violation dicts."""
    violations = []

    if output.nsfw_detected:
        violations.append({
            "guardrail_name": f"{media_type}_nsfw",
            "media_type": media_type,
            "media_index": media_index,
            "severity": SEVERITY_HARD,
            "confidence": output.nsfw_confidence,
            "detail": f"NSFW content detected in {media_type} {media_index}",
        })

    if output.weapon_detected and output.weapon_confidence > 0.5:
        violations.append({
            "guardrail_name": f"{media_type}_weapon",
            "media_type": media_type,
            "media_index": media_index,
            "severity": SEVERITY_HARD,
            "confidence": output.weapon_confidence,
            "detail": f"Weapon detected in {media_type} {media_index}",
        })

    if output.realistic_human_child:
        violations.append({
            "guardrail_name": f"{media_type}_realistic_child",
            "media_type": media_type,
            "media_index": media_index,
            "severity": SEVERITY_SOFT,
            "confidence": output.realistic_child_confidence,
            "detail": f"Realistic human child depiction in {media_type} {media_index}",
        })

    if output.horror_elements and output.horror_confidence > 0.4:
        violations.append({
            "guardrail_name": f"{media_type}_horror",
            "media_type": media_type,
            "media_index": media_index,
            "severity": SEVERITY_HARD,
            "confidence": output.horror_confidence,
            "detail": f"Horror elements in {media_type} {media_index}: {output.explanation}",
        })

    return violations
