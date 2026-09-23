"""Raw OpenRouter Decisions API client for Jev (alpha endpoint).

Use when you want OpenRouter-specific fields (usage.cost, trace, session_id, provider
routing) without an SDK. For TypeSafe-SDK portability, prefer jev_client.py with
JEV_PROVIDER=openrouter (the /api/v1/systemone endpoint) instead.

Requires: pip install httpx. Env: OPENROUTER_API_KEY.
Verified against https://openrouter.ai/docs/guides/community/jev on 2026-09-22.
The endpoint is alpha: re-check the API reference before relying on new fields.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"  # pinned; "~typesafe/jev-latest" moves


class DecisionsRequestError(ValueError):
    """Request would be rejected by the Decisions API; raised before any network call."""


def validate_questions(questions: dict[str, dict[str, Any]]) -> None:
    """Enforce the Decisions API's stricter-than-native criteria rules and TypeSafe limits."""
    if not questions:
        raise DecisionsRequestError("questions must not be empty")
    for qid, q in questions.items():
        kind, criteria = q.get("type"), q.get("criteria")
        if kind == "noul":
            if criteria is not None and not {"true", "false"} <= set(criteria):
                raise DecisionsRequestError(f"{qid}: noul criteria must define both 'true' and 'false' (or be omitted)")
        elif kind == "choice":
            # 255 mirrors TypeSafe's native limit (the upstream model); OpenRouter's schema sets no max.
            if not isinstance(criteria, dict) or not 1 <= len(criteria) <= 255:
                raise DecisionsRequestError(f"{qid}: choice criteria must map 1-255 options")
        elif kind == "score":
            if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
                raise DecisionsRequestError(f"{qid}: score criteria must list 2-10 levels")
            if any(level is None for level in criteria):
                raise DecisionsRequestError(f"{qid}: score criteria cannot contain null on OpenRouter")
        else:
            raise DecisionsRequestError(f"{qid}: unknown question type {kind!r}")


def decide(
    state: str | dict | list,
    questions: dict[str, dict[str, Any]],
    *,
    model: str = MODEL,
    timeout_s: float = 5.0,
    session_id: str | None = None,
    zdr: bool = False,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """POST one Decisions request. Returns the parsed body: {id, model, provider, answers, usage{cost}}.

    Raises httpx.HTTPStatusError on non-2xx (402 = out of credits; 429/529 = back off),
    httpx.TimeoutException on deadline. The caller applies its fail policy.
    """
    validate_questions(questions)
    body: dict[str, Any] = {"model": model, "state": state, "questions": questions}
    if session_id:
        body["session_id"] = session_id[:256]
    if zdr:
        body["provider"] = {"zdr": True}
    http = client or httpx.Client(timeout=timeout_s)
    try:
        r = http.post(
            DECISIONS_URL,
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json=body,
        )
        r.raise_for_status()
        return r.json()
    finally:
        if client is None:
            http.close()


if __name__ == "__main__":
    out = decide(
        "The checkout button throws a 500 for every EU customer since this morning's deploy.",
        {
            "is_bug": {"type": "noul", "instructions": "The message reports a software defect"},
            "team": {
                "type": "choice",
                "instructions": "Which team should own this report?",
                "criteria": {"payments": "Checkout, billing, payouts", "frontend": "UI rendering", "other": None},
            },
        },
    )
    print(out["model"], out["answers"], out["usage"])
