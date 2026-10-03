# Changelog

## 0.1.1 — 2026-10-03

Documentation only.

- README now points at `KHAEntertainment/marketplace`. It previously used the
  pre-rename `KHAEntertainment/kha-marketplace` path, which still redirects but
  is the wrong URL. Released as 0.1.1 because the plugin catalog pins
  `v0.1.0`, whose bundled copy of the README still carried the stale URL.

## 0.1.0 — 2026-09-22

Initial release. Facts verified against primary sources on 2026-09-22 (Jev `jev-1.13.0`).

- `jev-integration` skill with this workflow: fit test, access path, integration layer,
  harness pattern, non-negotiables, calibration, deliverables.
- References: access paths (TypeSafe, OpenRouter systemone and Decisions, Vercel AI
  SDK/Gateway, Cloudflare, LiteLLM, Laya), frameworks, harness patterns, calibration and
  ops.
- Templates:
  - Python TypeSafe-SDK client for TypeSafe direct or OpenRouter.
  - Raw OpenRouter Decisions client with criteria validation.
  - AI SDK `experimental_evaluate` module with offline mock-model tests.
  - `@openrouter/sdk` gate.
  - Fail-closed Claude Code PreToolUse gate.
- `scripts/jev_probe.py` smoke test for every access path.
- Six `claude plugin eval` cases: trigger, harness, fit test, honesty, debug, non-trigger.
- Claude Code plugin manifest; the same layout is also discoverable by `npx skills`.
- Independent review (MiniMax M3 via Traycer) addressed before release:
  - Gate deny rules made case-insensitive, with long-flag, quoted, and
    download-then-execute variants.
  - Pass rules no longer skip Jev for file reads, compound commands, or sensitive paths.
  - Redaction extended to private-key blocks, URL credentials, Stripe keys, AWS session
    keys, Slack tokens, and JWTs.
  - Added `test_jev_gate.py`.
  - The unverified ~6-point accuracy-gap figure is now labelled as such.
