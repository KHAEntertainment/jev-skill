---
name: jev-integration
description: >-
  Decide whether and how to integrate TypeSafe's Jev (a non-generative "System One"
  decision model: state + typed Choice/Score/Noul questions -> calibrated typed answers)
  into a project. Covers the fit test (Jev vs LLM vs plain code), access-path choice
  (TypeSafe API, OpenRouter systemone or Decisions endpoints, Vercel AI SDK/Gateway,
  Cloudflare), framework choice (AI SDK, LangChain, Pydantic AI, TanStack, Effect, BAML),
  harness patterns (tool-call risk gates, model routers, triage and escalation, reranking,
  context pruning, LLM fallback cascades), calibration, and production ops (pinning,
  retries, fail-closed). Use when adding Jev or TypeSafe to code, replacing an LLM
  prompt-and-parse step whose output is an enum, boolean or number, choosing between
  OpenRouter and TypeSafe for Jev, building a Claude Code/Codex/Pi hook gate or router on
  Jev, or debugging a Jev integration (403/422 errors, wrong endpoint, missing confidence).
license: MIT
metadata:
  verified: "2026-09-22"
  jev-version: "jev-1.13.0"
  complements: "typesafe-ai/skills (official question-design skill)"
---

# Jev integration

Jev is TypeSafe AI's first "System One" model. You send a **state** (string, JSON object or
array) and a map of **typed questions**; one non-autoregressive forward pass returns typed
answers with calibrated probabilities. It never generates text. $0.042 per 1M input tokens,
output free, typically ~100-500 ms per call regardless of how many questions you batch.

This skill is about **integration architecture**: whether Jev fits, which access path and
framework to use, what harness to build around it, and how to run it safely. It does not
re-teach how to word questions.

## 0. Before you write anything

**Division of labor.** For question design (choosing Choice vs Score vs Noul, atomic
questions, state structure, criteria wording, no-match options), use TypeSafe's official
skill if it is installed (`typesafe-ai`, from `typesafe-ai/skills`). Otherwise read
`https://docs.typesafe.ai/llms.txt` and the primitive pages (`/primitives/choice.md`,
`/primitives/score.md`, `/primitives/noul.md`). Every docs page is available as Markdown by
appending `.md` to its path.

**Freshness.** Everything below was verified on 2026-09-22 against primary sources, one
week after Jev launched. The alpha/experimental surfaces (OpenRouter Decisions, AI SDK
`experimental_evaluate`, LangChain middleware, BAML nightly) move fast. Before writing
integration code, re-read the one live page for the path you chose (URLs are in
`references/access-paths.md`). If the live page disagrees with this skill, the live page
wins; tell the user this skill is stale. Never invent request or response fields.

**Honesty about vendor claims.** TypeSafe's "40x-200x faster" launch figures are vendor-run
(the launch post itself says they may be biased toward TypeSafe's setup). Third-party
reports cite an aggregate accuracy gap of about 6 points to the best frontier LLM on
TypeSafe's workflow evals, but that figure was not found on TypeSafe's primary pages as of
2026-09-22, so treat it as unverified. Present Jev as a cheap, fast, calibrated decider that
must be validated on the user's data, not as a free accuracy upgrade.

## 1. Fit test: Jev, an LLM, or plain code?

Ask of each candidate decision: *"Given this state, tell me X"*, where X is a Choice, a
Score, or a yes/no probability over a **bounded answer set known in advance**.

| Situation | Use |
|---|---|
| Deterministic rule exists (regex, allowlist, schema check, threshold on a number) | **Plain code.** Cheaper, exact, testable. Put these rules *in front of* Jev. |
| Judgment over natural-language or messy state, output is an enum / bool / 0-1 / ordinal | **Jev** |
| Many independent judgments over the same state (tags, flags, checks) | **Jev**, all in one request; they are evaluated in parallel and in isolation |
| You need calibrated uncertainty to route (act / review / escalate) | **Jev**; probabilities are native, not self-reported |
| Output must be generated: prose, code, summaries, extracted free-text values | **LLM** |
| Open-ended multi-step reasoning, planning, tool-use loops | **LLM** (Jev can make the bounded decisions *inside* that loop) |
| Arithmetic, counting, date/time comparison, following indirection | **Plain code** computes it, then pass the result into state. These are documented Jev weak spots |
| State > 32k tokens, or mostly irrelevant state | Trim or chunk first. Large irrelevant state degrades Jev |
| Non-English-critical decisions | Validate carefully. English is primary; other languages are less accurate |
| Wrong answers are costly and your own eval shows Jev trailing an LLM by more than you can accept | LLM, or Jev with a low-confidence -> LLM/human escalation tier |

Migration heuristic for an existing codebase: find LLM calls whose parsed output becomes an
enum, boolean, or number (JSON mode used only to get a label). Those are the targets. Keep
everything downstream unchanged and swap one decision point at a time.

## 2. Pick the access path

All paths serve the same TypeSafe-hosted model. TypeSafe is the only upstream provider,
including on OpenRouter. As of 2026-09-22 there is **no primary-source evidence of Jev on
Google Vertex AI, AWS Bedrock, Azure AI Foundry, Together, or Fireworks**. Say so if asked.

```
Already bill through OpenRouter, or want one key for many models?
  yes -> OpenRouter
         Want TypeSafe's SDKs / portable wire format?  -> POST https://openrouter.ai/api/v1/systemone
                                                          (TypeSafe SDK with base_url=https://openrouter.ai/api)
         Using @openrouter/sdk or @openrouter/ai-sdk-provider? -> POST https://openrouter.ai/api/alpha/decisions
  no  -> On Vercel / already using the AI SDK?        -> AI SDK experimental_evaluate (Gateway or @ai-sdk/typesafe-ai)
         Running in a Cloudflare Worker?              -> env.AI.run('typesafe/jev', ...)
         Otherwise (default)                          -> TypeSafe direct: POST https://api.typesafe.ai/v1/systemone
```

Gotchas that break integrations (details and the rest in `references/access-paths.md`):

| Gotcha | Consequence |
|---|---|
| Sending Jev to `/v1/chat/completions` or any OpenAI-compatible client | Rejected. Jev is only served on systemone / decisions / evaluate endpoints |
| Model id differs per path: `jev-latest` (TypeSafe), `typesafe/jev-1.13` or `~typesafe/jev-latest` (OpenRouter), `typesafe-ai/jev` (Vercel Gateway), `typesafe/jev` (Cloudflare) | 404 / unknown-model errors |
| OpenRouter **Decisions**: a Noul with `criteria` must give **both** `true` and `false`; Score criteria cannot contain `null` | 400, or `InvalidArgumentError` in the AI SDK provider |
| Where confidence lives: raw API `answers[id].confidence`; AI SDK + TypeSafe/Gateway `providerMetadata.typesafe.confidence[id]`; AI SDK + OpenRouter `providerMetadata.openrouter.answers[id].confidence` | Code silently reads `undefined` and never gates |
| Noul is called `boolean` in AI SDK / TanStack / Pydantic types; its value is `probability`, not `noul` | Field-name bugs |
| Noul answers have **no** confidence. The probability *is* the answer; 0.5 means undecided | Don't gate Nouls on confidence |
| Missing key -> **403** (not 401); bad key -> 401; malformed question -> 422 with FastAPI `detail[].loc` | Mis-classified auth errors |
| Vercel package is `@ai-sdk/typesafe-ai` (not `@ai-sdk/typesafe`); string Gateway ids need `ai` >= 7.0.105 per the vercel/ai CHANGELOG (Vercel's docs just say "AI SDK 7") | Install failures |

## 3. Pick the integration layer

Prefer the layer the project already uses. Read `references/frameworks.md` for install
lines, minimal code, and maturity notes.

| Project already uses | Integrate via | Maturity (2026-09-22) |
|---|---|---|
| Nothing / plain Python or Node | TypeSafe SDK (`typesafe-sdk`, `@typesafe-ai/sdk`) | Official, pre-1.0 |
| Vercel AI SDK | `experimental_evaluate` | Official, experimental |
| OpenRouter SDKs | `openRouter.alpha.decisions.create` / `openrouter.decisionModel()` | Official, alpha |
| LangChain (Python) | `langchain-typesafe` `TypeSafeClassifier`; `ModelRouterMiddleware`, `AutoModeMiddleware` | Beta / experimental |
| LangChain.js | `@langchain/typesafe` `TypeSafeClassifier` (no middleware) | 0.0.x |
| Pydantic AI | `Agent('typesafe:jev-latest', output_type=...)` | Official |
| TanStack AI | `decide()` + `@tanstack/ai-typesafe` | Official |
| Effect | `@effect/ai-typesafe` (`effect/unstable/ai`) | RC / unstable |
| LiteLLM proxy | pass-through, Jev auto-router, relevance guardrail | Official feature |
| BAML | `client: "typesafeai/jev-latest"` | Nightly only |
| Mastra, CrewAI, Agno, OpenAI Agents SDK, Claude Agent SDK | **No official support.** Call the TypeSafe SDK from a tool, hook, or guardrail | n/a |

## 4. Pick the harness pattern

Every Jev harness has the same shape: **upstream step produces state -> deterministic rules
settle the clear cases -> one Jev call makes typed judgments on the gray zone -> your code
owns thresholds, authorization, and the action.** Read `references/harness-patterns.md`
for the pattern you need.

| Goal | Pattern | Fail policy |
|---|---|---|
| Stop an agent running risky shell/tool calls | Tool-call risk gate (PreToolUse hook, middleware) | **Fail closed** (ask/deny) |
| Send each request to the cheapest capable model | Model/effort router | Fail open to a safe default model |
| Route tickets, forms, emails | Triage + confidence-banded escalation | Fail to human queue |
| Filter or order retrieved chunks, tools, skills | Relevance rerank / shortlist | Fail open (keep original order) |
| Check a pipeline handoff (LLM output, extracted record) | Verification checkpoint (LLM-as-judge replacement) | Fail to "unverified" |
| Keep accuracy where Jev is weak | Cascade: Jev first, LLM on low confidence | Fall through to LLM |
| Shrink agent context | Relevance pruning ("still needed?" per segment) | Fail open (keep content) |
| Block unsafe inputs/outputs | Guardrail (moderation, injection, PII) | Fail closed |

For a Claude Code gate, start from `templates/claude-code-gate/`.

## 5. Non-negotiables

Apply these in every integration, and tell the user when a requirement forces a tradeoff.

1. **Your code owns thresholds.** Keep questions and thresholds together in one reviewable
   module. Name the threshold constants and comment them with where their values came from.
2. **Classification is not authorization.** Jev says a command looks destructive or a refund
   was requested; code decides whether to run or grant it.
3. **Fail-closed for safety, fail-open for optimization.** Gates and guardrails deny or ask
   on error, timeout, or low confidence. Routers, rerankers, and pruners fall back to the
   non-Jev behavior.
4. **Explicit deadline.** Set a client timeout well under the caller's budget. A Claude Code
   PreToolUse command hook that *times out does not block the tool call*, so the hook must
   enforce its own deadline and still print a decision.
5. **Pin the version once thresholds are tuned.** Use `jev-1.13.0` (TypeSafe) or
   `typesafe/jev-1.13` (OpenRouter), not `jev-latest`. Log the response `model` field and the
   request id (`x-typesafe-request-id` / OpenRouter `id`). Re-validate when you move versions.
6. **Keys stay server-side.** Never ship a key to a browser (the JS SDK blocks this unless
   `dangerouslyAllowBrowser`). Redact secrets from state before sending.
7. **Untrusted content is injection-prone.** Jev does not treat adversarial text as hostile
   by default. When state contains fetched web content, tool output, or user uploads, add a
   question that detects instructions aimed at the model, and never let that content alone
   authorize an action.
8. **Typed is not true.** Jev cannot emit an off-schema value, but it can be schema-valid and
   wrong. Include an explicit "other / none / insufficient evidence" option wherever the
   answer might not exist.

## 6. Calibrate before automating

Do not ship auto-actions on default thresholds. Follow `references/calibration-and-ops.md`:
build a labeled set (start at 50-200 examples from real traffic), run it through the exact
questions, plot confidence (or Noul probability) against accuracy, then set **per-action**
bands: act, review, don't act. Low-stakes reversible actions can act around 0.7;
destructive or financial actions need 0.9+ and a human path below the floor. To compare
against an LLM on the same questions, use TypeSafe's `system-one-adapter-python`.

## 7. What to deliver when you integrate Jev

- One module holding the questions, the threshold constants, and the decision function that
  maps answers to actions.
- A thin client wrapper with a timeout, retries on 429/529/5xx only, a pinned model, and
  logging of `model`, request id, and usage.
- Offline tests with mocked answers covering each band, including the error/timeout path
  (AI SDK: `Experimental_EvaluationMockModelV4` from `ai/test`; Python: mock the client or
  the HTTP layer).
- A live smoke check. `scripts/jev_probe.py` verifies the key, endpoint, resolved model id,
  latency, and cost for TypeSafe or OpenRouter.
- A short note to the user listing thresholds still needing calibration on their data.

## Reference files (relative to this skill's directory)

| File | Read when |
|---|---|
| `references/access-paths.md` | Choosing or wiring an endpoint; auth, model ids, wire deltas, errors, rate limits, the self-hosted Laya alternative |
| `references/frameworks.md` | Using a framework integration; install lines, code, maturity, unsupported frameworks |
| `references/harness-patterns.md` | Designing a gate, router, triage flow, reranker, cascade, pruner or guardrail; reference implementations |
| `references/calibration-and-ops.md` | Setting thresholds, pinning, retries/timeouts per SDK, cost estimates, the known-weakness checklist |
| `templates/python/jev_client.py` | Python wrapper for TypeSafe direct or OpenRouter systemone |
| `templates/python/openrouter_decisions.py` | Raw OpenRouter Decisions API client with request validation |
| `templates/typescript/ai-sdk-evaluate.ts` | AI SDK `experimental_evaluate` with bands, plus a mock-model test |
| `templates/typescript/openrouter-decisions.ts` | `@openrouter/sdk` Decisions client |
| `templates/claude-code-gate/` | Fail-closed PreToolUse gate for Claude Code with settings snippet |
| `scripts/jev_probe.py` | Smoke-test credentials and endpoint (stdlib only) |
