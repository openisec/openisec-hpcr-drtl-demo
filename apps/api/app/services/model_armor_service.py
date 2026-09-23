"""
Model Armor (GCP) integration for input safety screening.

This adds a second, ML-based layer of defense on top of the existing
regex-based `validate_input()` in app/core/security.py (LLM01: Prompt
Injection). It calls the `sanitizeUserPrompt` REST endpoint of a
pre-created Model Armor template (hpcr-drtl-pi-guard) using Application
Default Credentials (the same service account already used for Vertex
AI / Cloud SQL, no new secrets required).

The template has four filters enabled: prompt injection / jailbreak,
malicious URLs, sensitive data (SDP basic config), and Responsible AI
(dangerous / hate speech / harassment / sexually explicit content). A
MATCH_FOUND on any of them blocks the request — all four represent
clearly-concerning input, not borderline cases needing separate
handling, so a single all-or-nothing decision is appropriate here.

Fail-open by design: if the Model Armor API call itself fails (network,
auth, quota, etc.), we log a warning and allow the request through rather
than degrading availability. We only block when Model Armor explicitly
reports a match.
"""

import logging
from typing import Optional

import google.auth
import google.auth.transport.requests
import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_credentials: Optional[google.auth.credentials.Credentials] = None
_auth_request: Optional[google.auth.transport.requests.Request] = None


def _get_access_token() -> str:
    """Fetch (and cache/refresh) an access token via Application Default
    Credentials. Reuses the same ADC chain as Vertex AI calls."""
    global _credentials, _auth_request
    if _credentials is None:
        _credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        _auth_request = google.auth.transport.requests.Request()
    if not _credentials.valid:
        _credentials.refresh(_auth_request)
    return _credentials.token


class PromptBlockedError(Exception):
    """Raised when Model Armor explicitly flags the input on any of the
    template's filters (prompt injection/jailbreak, malicious URL,
    sensitive data, or Responsible AI)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _triggered_filter_names(filter_results: dict) -> list[str]:
    """Best-effort extraction of which filter(s) reported MATCH_FOUND,
    for logging only. filter_results is sanitizationResult.filterResults,
    a map of filter key -> {result_key: {matchState, ...}}. Never raises;
    an unexpected shape just yields an empty/partial list."""
    triggered = []
    for filter_key, wrapper in (filter_results or {}).items():
        if not isinstance(wrapper, dict):
            continue
        for result in wrapper.values():
            if isinstance(result, dict) and result.get("matchState") == "MATCH_FOUND":
                triggered.append(filter_key)
                break
    return triggered


async def check_prompt_injection(text: str) -> None:
    """Sanitizes user input through the Model Armor template.

    Raises PromptBlockedError if Model Armor reports a MATCH_FOUND on
    any enabled filter (prompt injection/jailbreak, malicious URL,
    sensitive data, or Responsible AI content). Any other outcome
    (NO_MATCH_FOUND, or an error calling the API) allows the request
    to proceed.
    """
    if not settings.MODEL_ARMOR_ENABLED:
        return

    url = (
        f"https://modelarmor.{settings.MODEL_ARMOR_LOCATION}.rep.googleapis.com/v1/"
        f"projects/{settings.VERTEX_PROJECT}/locations/{settings.MODEL_ARMOR_LOCATION}/"
        f"templates/{settings.MODEL_ARMOR_TEMPLATE}:sanitizeUserPrompt"
    )

    try:
        token = _get_access_token()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"userPromptData": {"text": text}},
            )
        response.raise_for_status()
        result = response.json()
    except Exception as e:  # noqa: BLE001 - fail-open on any API/network error
        logger.warning("Model Armor check failed, allowing request through: %s", e)
        return

    sanitization_result = result.get("sanitizationResult", {})
    if sanitization_result.get("filterMatchState") == "MATCH_FOUND":
        triggered = _triggered_filter_names(sanitization_result.get("filterResults", {}))
        logger.info("Model Armor blocked a prompt (filters: %s)", ", ".join(triggered) or "unknown")
        raise PromptBlockedError(
            f"Input blocked by content safety filters ({', '.join(triggered) or 'unspecified'})"
        )
