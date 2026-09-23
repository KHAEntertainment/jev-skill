#!/usr/bin/env python3
"""Smoke-test a Jev access path (stdlib only).

Sends one tiny request and reports the HTTP status, resolved model id, request id,
latency, usage and cost. Exits 0 on success and 1 on failure. Costs a fraction of a cent.

  python3 jev_probe.py                                  # TypeSafe direct (TYPESAFE_API_KEY)
  python3 jev_probe.py --provider openrouter            # OpenRouter /api/v1/systemone (OPENROUTER_API_KEY)
  python3 jev_probe.py --provider openrouter-decisions  # OpenRouter /api/alpha/decisions
  python3 jev_probe.py --provider gateway               # Vercel AI Gateway TypeSafe-compatible (AI_GATEWAY_API_KEY)
  python3 jev_probe.py --dry-run                        # print the request, send nothing

Verified 2026-09-22. Endpoints and model ids are in references/access-paths.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

PROVIDERS = {
    "typesafe": ("https://api.typesafe.ai/v1/systemone", "TYPESAFE_API_KEY", "jev-1.13.0"),
    "openrouter": ("https://openrouter.ai/api/v1/systemone", "OPENROUTER_API_KEY", "typesafe/jev-1.13"),
    "openrouter-decisions": ("https://openrouter.ai/api/alpha/decisions", "OPENROUTER_API_KEY", "typesafe/jev-1.13"),
    "gateway": ("https://ai-gateway.vercel.sh/typesafe/v1/systemone", "AI_GATEWAY_API_KEY", "typesafe-ai/jev"),
}

STATE = "Hi, my payouts have failed for three days and I'm losing sales. Please help ASAP."
QUESTIONS = {
    "urgent": {"type": "noul", "instructions": "The message conveys urgency or time-sensitivity",
               "criteria": {"true": "Time-sensitive", "false": "Not time-sensitive"}},  # both sides: valid on Decisions too
    "team": {"type": "choice", "instructions": "Which team should handle this message?",
             "criteria": {"billing": "Payments and payouts", "technical": "Bugs and integrations", "other": "Anything else"}},
    "frustration": {"type": "score", "instructions": "How frustrated does the customer appear?",
                    "criteria": ["Calm, just stating facts", "Frustrated but civil", "Very angry"]},
}
EXPECT = {"urgent": "noul", "team": "choice", "frustration": "score"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", choices=PROVIDERS, default="typesafe")
    ap.add_argument("--model", help="override model id (e.g. ~typesafe/jev-latest)")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    url, key_env, default_model = PROVIDERS[args.provider]
    body = {"state": STATE, "model": args.model or default_model, "questions": QUESTIONS}
    if args.dry_run:
        print(f"POST {url}\nAuthorization: Bearer ${key_env}\n{json.dumps(body, indent=2)}")
        return 0
    key = os.environ.get(key_env)
    if not key:
        print(f"FAIL: {key_env} is not set", file=sys.stderr)
        return 1

    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            status, headers, raw = resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:500]
        hint = {401: "invalid key", 402: "out of credits (OpenRouter)", 403: "missing key or no permission",
                404: "wrong endpoint or model id", 422: "malformed question", 429: "rate limited",
                529: "overloaded"}.get(err.code, "")
        print(f"FAIL: HTTP {err.code} {hint}\n{detail}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"FAIL: {type(err).__name__}: {err}", file=sys.stderr)
        return 1
    ms = (time.perf_counter() - t0) * 1000

    data = json.loads(raw)
    answers = data.get("answers", {})
    problems = [f"{q}: expected {t}, got {answers.get(q, {}).get('type')}"
                for q, t in EXPECT.items() if answers.get(q, {}).get("type") != t]
    usage = data.get("usage", {})
    print(f"provider     {args.provider}  ({url})")
    print(f"status       {status}  latency {ms:.0f} ms")
    print(f"model        requested={body['model']}  resolved={data.get('model')}")
    print(f"request id   {headers.get('x-typesafe-request-id') or data.get('id') or '-'}")
    print(f"usage        {json.dumps(usage)}")
    for q, a in answers.items():
        print(f"answer       {q}: {json.dumps(a)}")
    if problems:
        print("FAIL: unexpected answer shape: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
