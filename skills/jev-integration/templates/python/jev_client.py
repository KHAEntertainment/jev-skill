"""Jev decision module template (TypeSafe SDK, direct or via OpenRouter systemone).

Copy into your project and adapt. Keeps questions, thresholds, and policy in one
reviewable place. Requires: pip install "typesafe-sdk>=0.7.1"

Provider selection (env):
  JEV_PROVIDER=typesafe    -> TYPESAFE_API_KEY, https://api.typesafe.ai, model jev-1.13.0
  JEV_PROVIDER=openrouter  -> OPENROUTER_API_KEY, https://openrouter.ai/api, model typesafe/jev-1.13
Verified against typesafe-sdk 0.7.1 on 2026-09-22.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum

from typesafe_sdk import (
    Choice,
    Noul,
    RetryPolicy,
    Score,
    SystemOneResponse,
    TypeSafeClient,
    TypeSafeError,
)

log = logging.getLogger("jev")

# --- Provider config --------------------------------------------------------------------

_PROVIDERS = {
    # Pin a version once thresholds are tuned; aliases (jev-latest) move.
    "typesafe": {"key_env": "TYPESAFE_API_KEY", "base_url": "https://api.typesafe.ai", "model": "jev-1.13.0"},
    # OpenRouter's /api/v1/systemone speaks the TypeSafe wire format.
    "openrouter": {"key_env": "OPENROUTER_API_KEY", "base_url": "https://openrouter.ai/api", "model": "typesafe/jev-1.13"},
}


def make_client(provider: str | None = None, *, timeout_s: float = 5.0, total_budget_s: float = 8.0) -> TypeSafeClient:
    """Build a client with an explicit deadline. Retries only transient failures (SDK default statuses)."""
    cfg = _PROVIDERS[provider or os.environ.get("JEV_PROVIDER", "typesafe")]
    return TypeSafeClient(
        api_key=os.environ[cfg["key_env"]],
        base_url=cfg["base_url"],
        model=os.environ.get("JEV_MODEL", cfg["model"]),
        timeout=timeout_s,  # per HTTP operation
        retry=RetryPolicy(max_retries=1, timeout=total_budget_s),  # total retry budget
    )


# --- Questions (refine wording with the official typesafe-ai skill / docs) ---------------

QUESTIONS = {
    "team": Choice(
        instructions="Which team should handle this support ticket?",
        criteria={
            "billing": "Charges, invoices, refunds, subscription changes",
            "technical": "Bugs, outages, integration failures",
            "account": "Login, permissions, profile changes",
            "other": "Anything that does not clearly fit the teams above",
        },
    ),
    "severity": Score(
        instructions="How severe is the issue for the customer?",
        criteria=[
            "Cosmetic or informational question",
            "Degraded, but a workaround exists",
            "Blocking, no workaround",
            "Blocking and causing financial or data loss",
        ],
    ),
    "refund_requested": Noul(instructions="The customer is asking for money back"),
}

# --- Thresholds: placeholders until calibrated on labeled data (see calibration-and-ops.md)

TEAM_AUTO_ROUTE_MIN_CONFIDENCE = 0.80  # TODO(calibrate): reversible action, act band
REFUND_FLAG_MIN_PROB = 0.70            # TODO(calibrate): flags for human refund review
SEVERITY_PAGE_MIN_SCORE = 2.5          # TODO(calibrate): between "blocking" and "loss"


class Route(str, Enum):
    AUTO = "auto"
    REVIEW = "review"
    HUMAN = "human"


@dataclass(frozen=True)
class Decision:
    route: Route
    team: str | None
    page_on_call: bool
    refund_review: bool
    reason: str
    model: str | None = None
    request_id: str | None = None


def decide(resp: SystemOneResponse) -> Decision:
    """Pure policy: answers -> action. Unit-test this with fixed answer fixtures."""
    team = resp.choices["team"]
    severity = resp.scores["severity"]
    refund = resp.nouls["refund_requested"]

    refund_review = refund.noul >= REFUND_FLAG_MIN_PROB
    page = severity.score >= SEVERITY_PAGE_MIN_SCORE
    if team.choice == "other":
        route, reason = Route.HUMAN, "no team fits"
    elif team.confidence >= TEAM_AUTO_ROUTE_MIN_CONFIDENCE and not refund_review:
        route, reason = Route.AUTO, f"team={team.choice} conf={team.confidence:.2f}"
    else:
        route, reason = Route.REVIEW, f"team={team.choice} conf={team.confidence:.2f} refund={refund.noul:.2f}"
    return Decision(route, team.choice, page, refund_review, reason, resp.model, resp.request_id)


def triage(ticket: dict, client: TypeSafeClient) -> Decision:
    """Call Jev and apply policy. Fails to the human queue (never drops the ticket)."""
    try:
        resp = client.system_one(state=ticket, questions=QUESTIONS)
    except TypeSafeError as err:  # auth, validation, rate limit after retries, timeout, connection
        log.warning("jev unavailable, failing to human queue: %r", err)
        return Decision(Route.HUMAN, None, False, False, f"jev error: {type(err).__name__}")
    decision = decide(resp)
    log.info(
        "jev decision=%s model=%s request_id=%s usage=%s answers=%s",
        decision.route.value, resp.model, resp.request_id, resp.usage.model_dump(),
        {k: v.model_dump() for k, v in resp.answers.items()},
    )
    return decision


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo = {"subject": "Stripe sync broken", "message": "Integration failing for 3 days, losing sales. Help ASAP."}
    print(triage(demo, make_client()))
