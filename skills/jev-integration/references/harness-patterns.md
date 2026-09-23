# Harness patterns

A "harness" here is the code around a Jev call that turns typed answers into actions. The
questions below are illustrative starting points; refine the wording with the official
`typesafe-ai` skill or `docs.typesafe.ai/primitives.md`. All thresholds are **placeholders
until calibrated** (see `calibration-and-ops.md`).

Contents: [Universal shape](#universal-shape) · [Tool-call risk gate](#1-tool-call-risk-gate) ·
[Model router](#2-model--effort-router) · [Triage and escalation](#3-triage-and-escalation) ·
[Rerank / shortlist](#4-relevance-rerank-and-shortlist) ·
[Verification checkpoint](#5-verification-checkpoint) · [LLM cascade](#6-llm-fallback-cascade) ·
[Context pruning](#7-context-pruning) · [Guardrails](#8-inputoutput-guardrails) ·
[Where to hook in each harness](#where-to-hook-in-each-harness) ·
[Reference implementations](#reference-implementations)

## Universal shape

```
state producer ──► deterministic pre-rules ──► Jev (one request, many questions) ──► policy in code ──► action
                     │ settle clear cases          │ timeout / error                    │ thresholds, bands
                     └─► action                    └─► fail policy                       └─► log model id, request id, answers
```

1. **Pre-rules first.** Allowlists, denylists, regexes, path checks, and size limits are
   exact and free. Jev only sees the gray zone. This also cuts latency and cost.
2. **One request, many questions.** Questions are evaluated in parallel and isolated from
   each other. Ask everything the policy needs up front, speculatively. Add a second
   round-trip only when a question truly depends on an earlier answer.
3. **Policy is a pure function** `answers -> action`, unit-tested with fixed answer
   fixtures. Thresholds are named constants.
4. **Fail policy is explicit**, per the table in SKILL.md §4.
5. **Observe:** log answers, probabilities, the resolved `model`, the request id, latency,
   and the action taken. This log becomes your calibration set.

## 1. Tool-call risk gate

**Use for:** coding agents (Claude Code, Codex, Pi, OpenCode), autonomous agents with shell,
filesystem, network, or SaaS write tools.

**Architecture** (the consensus across jev-guard, pi-verdict, pi-heed, jev-axi):

1. **Self-protection.** Deny edits to the gate's own files and config.
2. **Deterministic floor.**
   - Read-only tools (Read/Grep/Glob) are exempt.
   - Allowlisted commands (`git status`, `ls`, test runners) pass.
   - Denylisted patterns (`rm -rf /`, `curl … | sh`, writes to `~/.ssh`) are denied without
     a model call.
3. **Jev for the gray zone.** Redact secrets from the command and context before sending.
4. **Policy maps answers to `deny` / `ask` / pass-through.** Only emit `allow` from a
   deterministic allowlist, or from Jev at a *calibrated* high-confidence band for
   explicitly low-stakes categories. A gate whose only outputs are `deny`/`ask` can make
   things stricter but never silently grant.
5. **Fail closed.** Timeout, error, or missing key produces `ask` (interactive) or `deny`
   (unattended).

Example questions (state = `{tool, command_or_input, cwd, user_request_excerpt}`):

| id | type | purpose |
|---|---|---|
| `category` | choice | `read_only` / `reversible_write` / `destructive` / `exfiltration` / `unclear` |
| `irreversible` | noul | deletes data, rewrites history, force-pushes, drops tables, or touches production |
| `user_requested` | noul | the user's latest request explicitly asked for this action |
| `from_untrusted` | noul | the command appears to follow instructions found in fetched or tool-output content |

Example policy (jev-guard-style; calibrate before trusting):

```
deny  if from_untrusted >= 0.7
deny  if irreversible >= 0.8 and user_requested < 0.85
ask   if irreversible >= 0.3 or category in {destructive, exfiltration, unclear}
ask   if category.confidence < 0.6
pass  otherwise   (hand back to the harness's normal permission flow)
```

**Claude Code specifics** (from the live hooks reference):
- Use a `PreToolUse` **command** hook matched on `Bash` (and optionally
  `Write|Edit|mcp__.*`). Print JSON
  `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny|ask|allow","permissionDecisionReason":"…"}}`.
- A command hook that **times out is discarded and the tool call proceeds.** The script
  must enforce its own deadline (for example a 4 s HTTP timeout under a 10 s hook
  `timeout`) and print `ask`/`deny` itself.
- Precedence across hooks is `deny` > `defer` > `ask` > `allow`. Permission deny/ask
  rules still apply after the hook.
- `ask` shows a prompt even in auto mode.
- Community "function hooks" (`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS`) are undocumented. Don't
  build on them.
- Template: `templates/claude-code-gate/`.

**Claude Agent SDK:** use a `PreToolUse` callback hook. It *blocks* the tool on timeout, so
it fails closed by default.

## 2. Model / effort router

**Use for:** proxies or middleware in front of LLM calls that pick the cheapest capable
model and reasoning effort.

- **Questions:** one Choice over tiers, with a description per tier (for example
  `trivial_lookup`, `routine_edit`, `multi_file_change`, `deep_reasoning`), plus an
  optional Noul for "requires tool use / long context".
- **Policy:**
  - Pick the argmax tier. If confidence is below a floor (Switchboard uses 0.70), take
    the **safer (stronger)** tier, not the cheaper one.
  - Pin the chosen model for the whole conversation so the prompt cache isn't thrown away
    (Switchboard). Re-route only at task boundaries.
- **Fail policy:** on timeout or error, use the default model. Never fail to the cheapest
  model.
- **Existing tools:**
  - LangChain `ModelRouterMiddleware`
  - LiteLLM `classifier_type: jev`
  - eve `auto({ options })`
  - Pydantic AI `SelectModel`
  - Switchboard / Jevonian proxies for Claude Code and Codex
  - `pi-typesafe-router` for Pi

## 3. Triage and escalation

**Use for:** support tickets, form submissions, email, and alerts.

- **Questions:**
  - Choice for the destination queue, always including `other`.
  - Score for severity, with levels that describe concrete situations.
  - Nouls for specific flags: refund requested, legal threat, churn risk, PII present.
- **Policy with three bands per action:**
  - **auto:** confidence ≥ high and the action is reversible (tagging, queue assignment).
  - **review:** middle band. Route with a "needs confirmation" flag.
  - **human:** below the floor, `other` chosen, or any high-stakes flag (legal,
    refund > $X).
- **Fail policy:** on error, send to the general human queue. Never drop the item.

## 4. Relevance rerank and shortlist

**Use for:** RAG chunks, tool or skill shortlisting before an LLM call, memory recall.

- **Questions:** one Noul per candidate, "this passage directly helps answer the query",
  with state = `{query, candidate}`. For N candidates, either send N requests in parallel
  or one request whose state holds all candidates and asks one Noul each.
- **Policy:** sort by probability, keep the top-k or everything above a floor.
- **For 1-of-many selection:** a single Choice over up to 255 options with descriptions.
  Use hierarchical Choices for deeper taxonomies.
- **Fail policy:** keep the original retrieval order.
- **Evidence** (TypeSafe cookbook, CLERC): top-1 accuracy rose 5% to 18%. Community runs
  are mixed, and Jev alone did not beat vector retrieval in one test. Rerank on top of
  retrieval, not instead of it.

## 5. Verification checkpoint

**Use for:** checking an LLM's output or an extracted record at a pipeline handoff, or
running online evals instead of an LLM-as-judge.

- **Questions:** one Noul per property ("the answer cites only facts present in the
  source", "all required fields are present", "the tone is appropriate for a customer").
  Decompose; don't ask "is this good?".
- **Policy:** any critical Noul below its threshold -> retry the generator, repair, or
  flag. Use a weighted composite only for non-critical quality scoring. A weighted score
  cannot express "any serious violation fails".
- **Fail policy:** mark the item unverified. Do not pass it as verified.

## 6. LLM fallback cascade

**Use for:** keeping LLM-level accuracy where Jev is weak, at Jev-level average cost.

- Ask Jev first. If confidence (or Noul distance from 0.5) is above a calibrated floor, use
  the answer. Otherwise ask an LLM with the same question and criteria.
- **Tooling:**
  - Pydantic AI `FallbackModel` supports this directly.
  - `typesafe-ai/system-one-adapter-python` answers the same `system_one` call with an
    LLM, so the fallback reuses your question definitions.
  - `jev-router` (PyPI, Akashdb5) implements a verified cascade.
- **Measure** the fallback rate. If most calls fall through, Jev isn't a fit for that
  decision.

## 7. Context pruning

**Use for:** agent transcripts and large tool outputs.

- **Questions:** per segment or tool call, a Noul for "still needed to finish the current
  task" and optionally a Noul for "keep verbatim rather than summarize".
- **Policy:** drop segments below the threshold (fast-jev-compaction uses 0.5). Always keep
  the most recent N messages.
- **Fail policy:** keep everything and fall back to the harness's normal compaction.
- **Caution:** the Claude Code plugins that do this rely on undocumented function hooks.
  In your own harness, implement it at the transcript layer you control. For LiteLLM, use
  its relevance guardrail.

## 8. Input/output guardrails

**Use for:** moderation, prompt-injection screening of untrusted content, PII detection,
policy compliance.

- **Questions:**
  - A Choice for category, including `benign`.
  - A Noul for "this text contains instructions directed at an AI system".
  - Nouls for specific policy violations.
- **Policy:** block above the threshold and abort the turn. Log the category.
- **Fail policy:** **closed** for safety guardrails. LiteLLM's guardrail defaults to
  fail-open, so change it.
- **Caution:** Jev "does not treat adversarial content as hostile by default" (jaggedness
  page). The detector question must be explicit, and the guardrail cannot be the only
  defense for high-stakes actions.

## Where to hook in each harness

| Harness | Tool gate | Router | Notes |
|---|---|---|---|
| Claude Code | `PreToolUse` command hook (plugin `hooks/hooks.json` or settings) | local proxy (Switchboard) via `ANTHROPIC_BASE_URL` | timed-out hook does not block |
| Claude Agent SDK | `PreToolUse` callback hook | choose `model` per `query()` | callback timeout blocks |
| Codex | Codex hooks / jev-guard `install codex` | proxy | check Codex hook docs live |
| Pi | extensions (pi-verdict, pi-heed) | `pi-typesafe-router` | largest community cluster |
| LangChain agents | `AutoModeMiddleware` (Python) | `ModelRouterMiddleware` | JS: build it yourself |
| Pydantic AI | `Hooks(before_tool_execute)` + `SkipToolExecution` | `SelectModel` | |
| Vercel AI SDK / eve | eve `approval: auto({model})`; AI SDK tool `needsApproval` + evaluate | eve `auto({options})` | |
| OpenAI Agents SDK | input/output/tool guardrails calling the TypeSafe SDK | own router step | no official integration |
| Custom loop | wrap tool dispatch | wrap the LLM call | follow the universal shape |

## Reference implementations

These are community projects from the week after launch and have not been audited. Read
them for architecture, and vet them before installing.

| Project | Pattern | Notable design choice |
|---|---|---|
| `leepokai/jev-guard` | multi-harness tool gate | Score risk + 3 Nouls; env-tunable thresholds; 20 s timeout; **fails open by default** (`JEV_GUARD_FAIL_CLOSED` to change) |
| `jesset/pi-verdict` | Pi gate | three layers (self-protection, deterministic rules, classifier); **fails closed**; LLM fallback on low confidence; OpenRouter by default |
| `Nyarlathoteppppp/pi-heed` | Pi constraint enforcer | deterministic rules for side effects, Jev "only judges meaning"; shadow mode default; enforce at p ≥ 0.9 |
| `shiftynick/jev-axi` | CLI + PreToolUse installer | local decisions for routine commands; secret redaction; act ≥ 0.75, confirm ≥ 0.45 |
| `ruban-24/switchboard` | Claude Code / Codex router proxy | pins the model per conversation for cache continuity; 0.70 floor |
| `xinyao27/jevonian` | router proxy | phase-based routing; falls back only on failure |
| `Akashdb5/jev-router` (PyPI) | security gate + complexity cascade | fails closed with `GateUnavailable` |
| `tamaratran/fast-jev-compaction`, `jev-pruner` | context pruning | rely on undocumented function hooks |
| `jerryjliu/docjev` | document classification | probabilities not claimed calibrated |

Directory: `github.com/cobanov/awesome-jev`.

Several popular gates **fail open**. If you adopt one for safety, change that default and
tell the user.
