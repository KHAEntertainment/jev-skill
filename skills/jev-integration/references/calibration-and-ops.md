# Calibration and production ops

Contents: [Calibration procedure](#calibration-procedure) · [Threshold bands](#threshold-bands) ·
[Version pinning](#version-pinning) · [Timeouts, retries, errors](#timeouts-retries-errors) ·
[Fail-open vs fail-closed](#fail-open-vs-fail-closed) · [Rate limits and cost](#rate-limits-and-cost) ·
[Observability](#observability) · [Comparing against an LLM](#comparing-against-an-llm) ·
[Known weaknesses checklist](#known-weaknesses-checklist) · [Security](#security)

## Calibration procedure

Calibration is a property of groups of predictions: of the answers marked 0.8, about 80%
should be right. It says nothing about any single answer. TypeSafe's published ECE
(expected calibration error) is 0.144, which is good but not perfect, and it was measured
on TypeSafe's tasks, not yours. So:

1. **Collect a labeled set** from real traffic for each decision. Start with 50-200
   examples; stakes set the size. Include the hard and ambiguous cases, not just the
   easy ones. If an LLM or human already makes this decision, its logged outputs are a
   starting label set, but spot-check them.
2. **Freeze the questions.** Calibration applies to an exact set of question wording,
   criteria, state shape, and model version. Change any of them and you recalibrate.
3. **Run the set** through the pinned model. Store every probability, not just the argmax.
4. **Plot reliability:** bucket by confidence (Choice/Score) or by probability (Noul) into
   about 5-10 bins and chart observed accuracy per bin. Also compute accuracy at each
   candidate threshold and the fraction of traffic above it (coverage).
5. **Choose thresholds per action** from the accuracy/coverage curve, given the cost of a
   wrong action vs the cost of escalating. TypeSafe's docs say to plot confidence
   against accuracy on your data and to start conservative.
6. **Hold out** 20-30% of the set to confirm the chosen thresholds weren't overfit.
7. **Re-run** on every model version change, question edit, or noticeable input-distribution
   shift. Keep the set and the script in the repo, for example `evals/jev/`.

Minimal analysis sketch:

```python
# rows: [{"p": 0.91, "correct": True}, ...]  p = confidence (choice/score) or noul prob
def curve(rows, thresholds=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95)):
    for t in thresholds:
        kept = [r for r in rows if r["p"] >= t]
        acc = sum(r["correct"] for r in kept) / len(kept) if kept else float("nan")
        print(f"t={t:.2f} coverage={len(kept)/len(rows):.0%} accuracy={acc:.1%}")
```

For Nouls, evaluate both tails: `p >= hi` means act-yes and `p <= lo` means act-no. The
band between is "undecided". 0.5 is maximal uncertainty, not "medium".

## Threshold bands

TypeSafe's confidence guidance uses three bands: act, proceed with caution, don't act.
Thresholds scale with risk. Starting points to *test*, not to ship:

| Action class | Act (auto) | Review / caution | Don't act |
|---|---|---|---|
| Reversible, low-stakes (tagging, queue assignment, rerank order) | ≥ 0.7 | 0.5-0.7 | < 0.5 |
| Customer-visible or costly-to-undo (auto-reply, refund < limit) | ≥ 0.85 | 0.6-0.85 | < 0.6 |
| Destructive / security / financial (run shell, delete, transfer) | ≥ 0.9-0.95 **and** a deterministic precondition | everything else asks a human | error, timeout |

Rules:
- **Thresholds belong to actions, not to the model.** The same answer can auto-tag at 0.7
  and still need a human before issuing a refund.
- **Confidence is not correctness.** Choice/Score `confidence` measures how peaked the
  distribution is. You may compute your own measure from `probabilities`, such as the
  margin between the top two options.
- **Don't threshold when you only need the argmax** (for example a harmless default
  choice). Low confidence between two acceptable options is fine.
- **Ignore uncertainty on unused branches** of speculative fan-out questions.

## Version pinning

- The aliases `jev-latest` and `jev-preview` move. TypeSafe: "If you have tuned confidence
  thresholds against a specific version, pin that version's ID instead of the alias."
- **Pinned ids:**
  - TypeSafe: `jev-1.13.0`
  - OpenRouter: `typesafe/jev-1.13` or the dated `typesafe/jev-1.13-20260917`
  - Vercel/Cloudflare: check the provider's catalog for a versioned id; their docs show
    unversioned ids only.
- **Always log the response `model` field.** It reports the resolved version even when
  you sent an alias. Alert when it changes unexpectedly.
- **Upgrading:** re-run the calibration set on the new version, compare the curves, adjust
  thresholds, and only then switch the pin. Check
  `https://docs.typesafe.ai/model-jaggedness/<version>.md` for changed weak spots.
- **Pin SDK versions too.** `ai` (experimental API), `langchain-typesafe` (alpha), and the
  OpenRouter Decisions SDK methods (alpha) can change between minor releases.

## Timeouts, retries, errors

Typical latency is about 100 ms, with 70-500 ms end to end; third parties measured a
236-276 ms p50. Size timeouts to the caller:

| Caller | Suggested client timeout | Retries |
|---|---|---|
| Interactive hook / gate (e.g. Claude Code PreToolUse) | 3-5 s total, well under the hook `timeout` | 0-1 |
| Web request path | 1-2 s | 0-1, then fall back |
| Background job / batch | 10-30 s | SDK default (2) |

**SDK retry defaults:**
- Python `typesafe-sdk`: `RetryPolicy(max_retries=2, backoff 0.5-5 s, statuses 408/429/5xx, respect_retry_after=True, timeout=30.0)`,
  where `timeout` is the *total* retry budget and the per-operation timeout defaults to
  10 s. `RetryPolicy(max_retries=0)` disables retries.
- JS `@typesafe-ai/sdk`: `retry: {maxRetries: 2, backoffInitialMs: 500, backoffMaxMs: 5000, maxRetryAfterMs: 60000}`.
  The `timeout` is per attempt with **no total budget**, so pass an `AbortSignal` for a
  hard deadline.
- AI SDK `experimental_evaluate`: `maxRetries` defaults to 2; retries 429/529;
  `InvalidResponseDataError` is not retried. Use `abortSignal` for a deadline.
- LangChain.js: `maxRetries` 2, `timeout` 30000.

**Error handling map (native API):**

| Status | Meaning | Do |
|---|---|---|
| 401 | invalid key | fail per policy; alert; don't retry |
| 403 | **missing** key (documented as 401) or permission | same as 401 |
| 400 / 422 | malformed request (422 body names the field in `detail[].loc`) | bug: don't retry; log the body |
| 402 (OpenRouter) | out of credits | fail per policy; alert |
| 429 | rate limited | back off, honor `retry-after` / `retry-after-ms` |
| 5xx, 529 | server error / overloaded | back off; bounded retries |
| timeout / connection | network | fail per policy |

Also observed: a bare `{"error_type":"max_tokens_exceeded"}` when state is too large. Trim
state rather than retrying.

## Fail-open vs fail-closed

Decide per integration and write the choice in code comments:

| If Jev is unavailable, the safe outcome is… | Policy | Examples |
|---|---|---|
| the action does not happen | **fail closed** (deny / ask / human queue) | tool gates, guardrails, auto-approval, fraud/abuse flags |
| the system behaves as it did before Jev | **fail open** (bypass Jev) | model routing (to the default model), reranking (original order), pruning (keep all), tagging (untagged) |

A circuit breaker (LiteLLM has one built in) prevents a Jev outage from adding timeout
latency to every request. After N failures, skip Jev for a cooldown and apply the fail
policy directly.

## Rate limits and cost

- **Limits** (jev-1.13.0): 1,200 requests/min and 250,000 tokens/s, "adjusting
  dynamically". High-volume pipelines should use a client-side token bucket; ask
  sales@typesafe.ai for more.
- **Cost:** only input tokens are billed. `cost ≈ (state_tokens + Σ question_tokens) × $0.042 / 1M`.
  - Example: a 400-token request costs about $0.0000168; 1M such calls cost about $16.80.
  - OpenRouter returns `usage.cost` per call; Vercel returns `providerMetadata.gateway.cost`.
- **Batching:** put questions for the same state in one request. TypeSafe's cookbook
  reports 12.2x cheaper and 10x faster than one request per question, with no change in
  answers. Separate states need separate requests; send them concurrently within rate
  limits.
- **Context:** 64k per request, and 32k for state plus the longest question. Only send the
  state the questions need. Irrelevant state hurts accuracy ("context rot") as well as
  cost.

## Observability

Log per call:
- decision name
- resolved `model`
- request id (`x-typesafe-request-id`, SDK `.request_id`, OpenRouter `id`)
- latency
- `usage`
- every answer with its probabilities/confidence
- the action taken and the band that triggered it
- on error: status and error body

Sample these logs into the calibration set, and label outcomes when they become known
(ticket reassigned, command later reverted).

## Comparing against an LLM

`typesafe-ai/system-one-adapter-python` is a drop-in `system_one` replacement backed by
OpenAI, Anthropic, or Gemini. Run the same questions and labeled set through Jev and an LLM
to compare accuracy, latency, and cost on *your* decisions. If the gap is intolerable for a
specific decision, keep an LLM there or use the cascade pattern.

## Known weaknesses checklist

From `https://docs.typesafe.ai/model-jaggedness/jev-1.13.md` (reviewed 2026-09-17). Check
each decision against it:

| Weakness | Mitigation |
|---|---|
| Literal reading | Spell out intent and edge cases in criteria |
| Math and counting | Compute in code, put the result in state |
| Date/time comparison | Compute deltas in code (`days_since_order: 34`) |
| Indirection ("the option mentioned in field X") | Resolve references in code before sending |
| Large irrelevant state (context rot) | Send only relevant fields |
| Adversarial content / prompt injection | Explicit detector question; never let such content alone authorize an action |
| Contradictory instructions vs criteria | Review questions for internal consistency |
| No structural invariants (P(yes) + P(not yes) may exceed 1) | Ask one polarity; don't derive complements by subtraction across questions |
| Generation | Use an LLM |
| Non-English | Validate per language; English is primary |

## Security

- Keep API keys in server-side env or secret stores, never in client bundles, repos, or
  logs.
- Redact secrets, tokens, and credentials from state before sending (tool-gate state often
  contains them).
- Data handling: TypeSafe doesn't train on customer data. ZDR is enterprise-only on
  TypeSafe direct, available per request on Vercel Gateway, and available via
  `provider.zdr` on OpenRouter.
- Treat third-party Jev plugins, MCP servers, and hooks as untrusted code. Several popular
  gates fail open by default.
