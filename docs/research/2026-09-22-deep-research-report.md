> **Archived source material (2026-09-22).** This is the original research report the skill was built from. It is kept for provenance and is **superseded wherever `skills/jev-integration/references/` disagrees**. Known corrections: OpenRouter also serves Jev at `/api/v1/systemone` (TypeSafe wire format); no primary source confirms Jev on Vertex AI or other clouds; the Vercel direct provider is `@ai-sdk/typesafe-ai`; `experimental_evaluate` first shipped in `ai` 7.0.103; context is 64k per request with 32k for state plus the longest question; LangChain.js has no Jev middleware.

# Deep Research Report: "Jev" by TypeSafe AI ([typesafe.ai](http://typesafe.ai))

## TL;DR

- **Jev is not an LLM and not a "router" in the model-routing sense** — it is TypeSafe AI's first "System One" model: a non-generative decision model that takes a *state* (text or JSON) plus typed *questions* (Choice, Score, Noul) and returns typed answers with calibrated probabilities in a single non-autoregressive forward pass, at $0.042 per 1M input tokens with free output. It is used *for* agent-routing decisions, which is why the explainx.ai piece frames it that way, but routing is one use case, not what the model is.
- **You use it three main ways**: TypeSafe's own HTTP API (`POST https://api.typesafe.ai/v1/systemone`) with official Python (`typesafe-sdk`) and JS (`@typesafe-ai/sdk`) clients; the Vercel AI SDK 7 `experimental_evaluate` function via AI Gateway (`typesafe-ai/jev`); or OpenRouter's alpha "Decisions" endpoint (`typesafe/jev-1.13`). Cloudflare Workers AI, LangChain (`TypeSafeClassifier`), Pydantic AI, TanStack AI, LiteLLM, Effect, and others also support it.
- **Laya (ConvAI Innovations) is a genuine open-source (Apache-2.0) alternative**: a 421M-param ModernBERT decision model with the same state+typed-questions I/O paradigm, self-hostable at \~32.8–39.5 ms/decision on a Tesla T4, but it is a *base to fine-tune*, not a drop-in zero-shot equivalent, and it does not natively plug into Jev's hosted harnesses without an adapter.

---

## Key Findings

1. **What it is.** Jev is a "System One Model" — a term TypeSafe coined from Kahneman's fast/intuitive "System 1" thinking. It evaluates typed questions against a shared state and returns `choice`/`score`/`noul` values plus probability distributions and (for Choice/Score) a confidence score. It does not generate text, cannot write prose or code, has no chat interface, is text-only (no image/audio/video), and has a 32,000-token state budget. It launched September 15, 2026; the current version is `jev-1.13.0` (alias `jev-latest`).
2. **Who makes it.** TypeSafe AI, a San Francisco lab that emerged from stealth on September 15–16, 2026 with a $40M seed round led by DCVC. Forbes (Ron Schmelzer, Sept 22 2026) reported, "citing a person familiar with the deal, that the round valued the company at $200 million — a figure TypeSafe has not confirmed." Founder/CEO Diogo Almeida is a former OpenAI researcher credited as a co-inventor of RLHF/InstructGPT/ChatGPT; co-founders are Erik Gafni and Sasha Sheng. The model is named after Jevons Paradox. Training used a proprietary method called RLCD (Reinforcement Learning for Calibrated Decisions) on exclusively synthetic data.
3. **How it differs from an LLM.** It returns typed decisions with native, calibrated probability distributions instead of generated (and possibly hallucinated) text; every question in a request is evaluated in parallel and in isolation against the same state, so adding questions barely changes latency and creates no "context rot"; output is constrained to your schema so it *cannot* emit an off-schema value (though it can return a schema-valid but semantically wrong value).
4. **Availability &amp; pricing.** $0.042 per 1M input tokens, output free (there is no autoregressive decoding to meter). 32K context. On OpenRouter, released Sept 18, 2026; on Vercel AI Gateway, Sept 16, 2026, where it supports Zero Data Retention and No Training per request. Rate limits for `jev-1.13`: 250,000 tokens/second and 1,200 requests/minute (both dynamic).
5. **Harness/SDK support is unusually broad for a two-week-old model.** Vercel called Jev "the fastest-adopted model in AI Gateway history": by hour 24 it was being used by nearly 13% of paid teams — "more than twice the share reached by any previous model launch, including the GPT-5.6 family." Official/first-party support spans TypeSafe SDKs, Vercel AI SDK + AI Gateway, Cloudflare Workers AI, OpenRouter, LangChain/LangChain.js, Pydantic AI, TanStack AI, LiteLLM, Effect, Composio, plus an official "agent skill" for Claude Code and other coding agents.
6. **The claims deserve skepticism.** TypeSafe's headline "20–200× faster, 40–400× cheaper" (peak 193.6×/444.6×) figures are vendor-run, best-case, and measured against agreement with other frontier models rather than ground truth. TypeSafe itself discloses a \~6-point aggregate accuracy gap (67.8% vs. 74.1% for the best comparator, GPT-5.6 Sol, over 711 cases across four tasks — widest on invoice processing, 61.8% vs 79.1%). Independent testing by Every corroborated the *direction*: Jev was "roughly 25x faster and 580x cheaper than Claude Fable 5.1 on extraction tasks: 0.35 seconds versus 8.83 seconds per passage."

---

## Details

### Section 1 — What Jev is

**The core paradigm.** Traditional LLMs produce text for humans to read. When your *code* needs a judgment, you're forced to coerce a text generator into emitting structured output and then parse it back. Jev removes that mismatch: you send a **state** and a set of **typed questions**, and get back **typed answers + probability distributions** your code can branch on, sort by, and route with — with no text generation and nothing to parse.

TypeSafe exposes **three AI primitives** (question types), all mixable in one call:


| Question type | Goal                                            | Returns                                                                                      | Limits                    |
| ------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------- |
| **Choice**    | Choose one option from a named set              | `choice` (winning key), `probabilities` (per option), `confidence`                           | Up to **255 options**     |
| **Score**     | Rate the state on an ordered rubric             | `score` (probability-weighted mean, indexed from 0), `probabilities`, `legend`, `confidence` | **2–10 levels**           |
| **Noul**      | Estimate probability a yes/no statement is true | `noul` (0–1)                                                                                 | none; no confidence field |


("Noul" is TypeSafe's coinage for the boolean/yes-no primitive. On Vercel AI SDK and Cloudflare it is surfaced as `boolean` with a `probability` field.)

**Key architectural properties:**

- **Parallel, isolated evaluation.** Every question is evaluated independently against the same state in one forward pass. The answer to question A never becomes hidden context for question B. Adding questions barely changes response time and costs only the extra input tokens.
- **Atomic questions, composed in code.** The documented design philosophy: ask one narrow, well-scoped thing per question ("a gut-check a knowledgeable person could make in seconds"); decompose complex judgments into multiple questions and combine them with your own logic/weights in code.
- **Calibration (RLCD).** Trained so that probabilities meaningfully represent uncertainty — across many predictions, the ones marked 0.8 should be right \~80% of the time. Calibration is a group property; it guarantees nothing about any single answer.
- **Confidence** (Choice/Score only) is a 0–1 statistic derived from the *shape* of the probability distribution (peaked = high, flat = low). It is distinct from the winning option's probability, and is *not* a probability of correctness. Noul has no confidence field because the probability itself is the answer (0.5 = undecided, not "medium").

**How it differs from a normal LLM or a "router":**

- Not a chat model, no text/code generation, no streaming (see §6), text-input only, 32K state budget.
- vs. structured-output/JSON-mode LLMs: a JSON-mode LLM still *samples* field values through text generation and any probability is a self-reported estimate; Jev's probabilities are native to the model and calibrated.
- The word "router" in the explainx.ai headline refers to a *use case* (using Jev to make the model-routing/tool-selection decision inside an agent loop), not to Jev being an LLM gateway/router. Jev decides; your code routes.

**Provenance / credibility notes.** TypeSafe trained Jev exclusively on synthetic data over two years in stealth. It "cannot hallucinate" only in the narrow sense that it cannot emit an off-schema value; the CEO acknowledged on Hacker News that it can still return a schema-valid but factually wrong answer.

### Section 2 — How to use it

**Access paths and authentication:**

1. **TypeSafe direct HTTP API** — `POST https://api.typesafe.ai/v1/systemone`, header `Authorization: Bearer $TYPESAFE_API_KEY`. Get keys at console.typesafe.ai. General availability with no waitlist and $5 free credit was announced after an initial waitlisted early-access period.
2. **Python SDK** — `pip install typesafe-sdk` (Python ≥ 3.10). Reads `TYPESAFE_API_KEY` from env; defaults to `jev-latest`.
3. **JavaScript/TypeScript SDK** — `@typesafe-ai/sdk`.
4. **Vercel AI SDK 7 + AI Gateway** — `npm i ai` (≥ 7.0.105 for `experimental_evaluate`); model id `typesafe-ai/jev`; auth via `vercel env pull` OIDC token (or `@ai-sdk/gateway` provider instance). OpenAI-compatible endpoints do **not** work — you must use `experimental_evaluate` from the `ai` package (or AI Gateway's native HTTP evaluation API).
5. **OpenRouter** — model `typesafe/jev-1.13` (or `~typesafe/jev-latest`), but **only** via the alpha Decisions endpoint `POST https://openrouter.ai/api/alpha/decisions` — the OpenAI-compatible `/v1/chat/completions` endpoint rejects it, and it does not appear in `GET /v1/models`. Requires prepaid credits.
6. **Cloudflare Workers AI** — `env.AI.run('typesafe/jev', {...})`.

**Python SDK example (from the quickstart):**

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

client = TypeSafeClient()  # reads TYPESAFE_API_KEY, defaults to jev-latest
ticket = "Hi, I've been trying to connect my Stripe account for 3 days and the integration keeps failing. I'm losing sales. Please help ASAP."

response = client.system_one(
    state=ticket,
    questions={
        "department": Choice(
            instructions="Which team should handle this",
            criteria={
                "billing": "Payment or subscription issues",
                "technical": "Bugs or integration problems",
                "sales": "Pricing or account questions",
            },
        ),
        "frustration": Score(
            instructions="How frustrated the customer appears",
            criteria=["Calm, just stating facts", "Frustrated but civil", "Very angry, strong language"],
        ),
        "is_urgent": Noul(instructions="The message conveys urgency or time-sensitivity"),
    },
)
print(response.answers["department"].choice)  # "technical"
print(response.answers["is_urgent"].noul)     # 1.0

```

**TypeScript / Vercel AI SDK example:**

```typescript
import { experimental_evaluate as evaluate } from 'ai';

const result = await evaluate({
  model: 'typesafe-ai/jev',
  state: { subject: ticket.subject, message: ticket.message, plan: ticket.plan },
  questions: {
    department: { type: 'choice', instructions: 'Which team should handle this ticket?',
      criteria: { billing: 'Charges, invoices, and refunds', technical: 'Bugs, outages, and integration failures',
                  account: 'Login, permissions, and profile changes', other: 'Anything that does not fit' } },
    severity: { type: 'score', instructions: 'How severe is the issue for the customer?',
      criteria: ['Cosmetic or informational', 'Degraded, but a workaround exists',
                 'Blocking with no workaround', 'Blocking and causing financial or data loss'] },
    requestsRefund: { type: 'boolean', instructions: 'Is the customer asking for money back?' },
  },
  providerOptions: { gateway: { zeroDataRetention: true } },
});
// result.answers.department.choice is typed as 'billing' | 'technical' | 'account' | 'other'
// confidence lives in result.providerMetadata.typesafe.confidence (keyed by question id)

```

**Pydantic AI example (typed outputs, boolean threshold):**

```python
from typing import Literal
from pydantic import BaseModel, Field
from pydantic_ai import Agent

class Ticket(BaseModel):
    urgent: bool = Field(description='Does this need a reply within the hour?')
    area: Literal['billing', 'bug', 'account', 'other'] = Field(description='Which team owns it?')

agent = Agent('typesafe:jev-latest', output_type=Ticket)
result = agent.run_sync('You have charged me twice and support is ignoring me')

```

**Configuration options.** State can be a string, JSON object, or JSON array (an array is still *one* state, not a batch). `criteria` descriptions can be strings, objects, or arrays. There is no temperature, no max\_tokens, no streaming flag. Version pinning matters: `jev-latest` currently resolves to `jev-1.13.0` and will move; the response `model` field reports the versioned id that answered, so log it. AI Gateway supports Zero Data Retention and No Training per request. TypeSafe SDKs retry with exponential backoff and honor `retry-after`.

### Section 3 — Example use cases

Concrete, documented patterns (from TypeSafe/Vercel/Cloudflare docs and the community "awesome-jev" lists):

- **Support-ticket triage/routing** (the canonical example): department Choice + severity Score + refund-intent Noul in one call.
- **Model routing / model selection** inside agent loops: Jev estimates task difficulty/intent, code picks the model id, then `generateText` runs it. (LangChain's `ModelRouterMiddleware`, and dozens of community routers for Claude Code, Codex, Pi.)
- **Tool-call risk gating / "Auto Mode"**: before an agent runs a shell command, Jev classifies it (read-only/reversible/destructive) and Nouls flag whether it deletes files or touches production; high-confidence safe actions auto-run, risky ones pause for approval. (LangChain `AutoModeMiddleware`, Vercel `eve` auto-approval, many `PreToolUse` gates.)
- **Content moderation / guardrails**: a "must this be blocked?" Noul + category Choice, aborting the turn above a threshold.
- **RAG reranking / relevance**: a Noul per retrieved chunk to rank/filter by relevance (e.g., `jev-reranker`, `Oko`, memory rerankers lifting recall).
- **Verification checkpoints / LLM-as-judge replacement**: typed verdicts at pipeline handoffs; LangChain benchmarked Jev as a cheaper, more consistent online-eval judge.
- **Escalation routing**: `auto_resolve` vs `escalate` with confidence-graduated human review.
- **Document classification &amp; splitting** (LlamaIndex "DocJev"), **form-submission routing**, **data labeling/curation**, **semantic grep**, **spam filtering**, **email triage at scale**.

### Section 4 — Usefulness for coding projects

- **Agentic coding harnesses**: fast, cheap permission/risk gating on tool calls (the pattern coding agents like Claude/Codex/Cursor previously hid in closed-source classifiers) — now replicable via Jev in any agent. Examples: `jev-axi`, `jev-guard`, Vercel `fx`'s `typesafe_permission_reviewer`, Pi's `pi-heed`/`pi-verdict`.
- **Multi-agent orchestration &amp; model routing**: pick the cheapest capable model / reasoning effort per request while preserving prompt-cache continuity (`Switchboard`, `Jevonian`, `duet-agent`, `pi-typesafe-router`).
- **Context management / compaction**: score transcript segments for "still needed?" to prune context verbatim instead of summarizing (`fast-jev-compaction`, `jev-pruner`, `jev-compaction`).
- **Typed/structured outputs**: Pydantic AI derives Jev questions directly from Pydantic output types; TanStack AI's `decide()`; Effect's classify/probability/rating ops. Good where you previously used JSON mode purely to get an enum/boolean/number.
- **CLI tools &amp; pre-commit hooks**: sub-second gates screening diffs for secrets/destructive commands, prose/"AI-slop" linters, semantic grep as CI lint rules (`jev-git`, `jev-commit`, `Sniff Test`, `taste-lint`, `nlgrep`, `jev.nvim`).
- **Edge/local inference workflows**: on Cloudflare Workers AI via `env.AI.run`; for truly local, see Laya (below).
- **Web apps**: Next.js route handlers that triage/route form and ticket submissions; `Experimental_EvaluationMockModelV4` in `ai/test` lets you unit-test the branching logic without network calls.

**Where it does *not* fit:** open-ended reasoning, planning, or any step that must *generate* content (prose, code). Use an LLM for those and Jev only for the bounded decision points. Keep classification separate from authorization — Jev tells you a command looks destructive or a refund was requested; your code decides whether to run/grant it.

### Section 5 — Harnesses / SDKs that currently support Jev

**Official / first-party (vendor-documented):**


| Harness / SDK                            | How Jev is exposed                                                                                                                            | Status                                      |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **TypeSafe Python SDK** (`typesafe-sdk`) | `TypeSafeClient.system_one(state, questions)`                                                                                                 | Official, stable                            |
| **TypeSafe JS SDK** (`@typesafe-ai/sdk`) | Equivalent JS client                                                                                                                          | Official                                    |
| **Vercel AI SDK 7**                      | `experimental_evaluate({model:'typesafe-ai/jev', state, questions})`                                                                          | Official, **experimental** (API can change) |
| **Vercel AI Gateway**                    | Model `typesafe-ai/jev`; native HTTP evaluation API; TypeSafe-compatible base URL                                                             | Official                                    |
| **Cloudflare Workers AI**                | `env.AI.run('typesafe/jev', {...})`                                                                                                           | Official third-party listing                |
| **OpenRouter**                           | `typesafe/jev-1.13` via `/api/alpha/decisions` only                                                                                           | Official, **alpha**                         |
| **LangChain (Python)**                   | `TypeSafeClassifier` Runnable + `ModelRouterMiddleware`, `AutoModeMiddleware`                                                                 | Official integration                        |
| **LangChain.js**                         | Classifier Runnable + routing/tool-gate middleware                                                                                            | Official                                    |
| **Pydantic AI**                          | `Agent('typesafe:jev-latest', output_type=...)`; derives questions from Pydantic types; `TypeSafeModelSettings(typesafe_boolean_threshold=…)` | Official provider                           |
| **TanStack AI**                          | `decide()` with an evaluation adapter (incl. Vercel Gateway, Cloudflare)                                                                      | Official                                    |
| **LiteLLM**                              | Jev-backed complexity routing + relevance guardrail                                                                                           | Source-level                                |
| **Effect**                               | `@effect/ai-typesafe` maps classify/probability/rating → Choice/Noul/Score                                                                    | Source-level                                |
| **Composio**                             | TypeSafe provider (tool shortlisting/selection, destructive-action gates); "Jev MCP"                                                          | Source-level                                |
| **Vercel** `eve` **/** `eve.dev`         | `auto({model})` defaults to `typesafe-ai/jev` for tool-approval decisions                                                                     | Official                                    |
| **BAML**                                 | v1 *nightly* maps typed return values → Jev questions                                                                                         | Pre-release                                 |
| **Ax, Rig**                              | Source-level integrations listed                                                                                                              | Verify per repo                             |


**Coding agents / IDEs.** There is an official **TypeSafe agent skill** installable into Claude Code (`claude plugin marketplace add typesafe-ai/skills`) and other agents (`npx skills add typesafe-ai/skills`). Beyond that, coding-agent support is overwhelmingly *community* plugins/hooks rather than built-in: Claude Code, Codex, and **Pi** (the largest community cluster) have many third-party Jev plugins; Cline has a plugins entry. Cursor/Windsurf/Zed/JetBrains and Factory Droid are reachable indirectly because they support agents that can call Jev (e.g., via the Agent Client Protocol, MCP, or a router proxy), **not** because they ship native Jev support. Distinguish carefully: only the vendors in the table above document first-party support.

**Note on OpenAI-compatible clients:** Because Jev returns *decisions*, not chat completions, standard OpenAI-compatible chat clients do **not** work against it — both OpenRouter and Vercel explicitly route it through dedicated decision/evaluation endpoints instead.

### Section 6 — Input and output shape

**Request (native TypeSafe API).** Exactly three top-level fields, all required: `state` (string | object | array), `model` (string), `questions` (map of question-id → Question). Per-question: `type` (`choice`|`score`|`noul`), `instructions` (string|object|array), and type-specific `criteria`. Choice `criteria` is a map of option→description (or `null`), max 255 options. Score `criteria` is an ordered array of 2–10 level descriptions (indexed from 0). Noul `criteria` is optional with `true`/`false` descriptions. There is no temperature, max\_tokens, or streaming flag.

```json
{
  "state": "Hi, I've been trying to connect my Stripe account for 3 days and the integration keeps failing. I'm losing sales. Please help ASAP.",
  "model": "jev-latest",
  "questions": {
    "department": { "type": "choice", "instructions": "Which team should handle this",
      "criteria": { "billing": "Payment or subscription issues", "technical": "Bugs or integration problems", "sales": "Pricing or account questions" } },
    "frustration": { "type": "score", "instructions": "How frustrated the customer appears",
      "criteria": ["Calm, just stating facts", "Frustrated but civil", "Very angry, strong language"] },
    "is_urgent": { "type": "noul", "instructions": "The message conveys urgency or time-sensitivity" }
  }
}

```

**Response.** Envelope: `{ model, answers, usage }`, where `model` is the resolved versioned id and `usage` is `{ input_tokens, output_tokens }`.

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "department": { "type": "choice", "choice": "technical", "confidence": 0.78,
      "probabilities": { "technical": 0.85, "sales": 0.0, "billing": 0.15 } },
    "frustration": { "type": "score", "score": 1.0, "confidence": 1.0,
      "legend": { "0": "Calm, just stating facts", "1": "Frustrated but civil", "2": "Very angry, strong language" },
      "probabilities": { "0": 0.0, "1": 1.0, "2": 0.0 } },
    "is_urgent": { "type": "noul", "noul": 1.0 }
  },
  "usage": { "input_tokens": 392, "output_tokens": 65 }
}

```

Field notes: **Choice** returns `choice` (highest-probability key), full `probabilities`, and `confidence`. **Score** returns `score` (probability-weighted mean, can land between levels), `legend`, `probabilities` (string level-index keys), and `confidence`. **Noul** returns only `noul` (0–1) — no confidence, no probabilities. Probabilities/scores are rounded to two decimals (so a distribution may sum to 0.99). Note: the `rounding` field and `typesafe_boolean_threshold` are **SDK-level constructs** (Vercel AI SDK / Pydantic AI respectively), not fields on the raw wire response; confidence in the AI SDK lives under `result.providerMetadata.typesafe.confidence`.

**Streaming.** None. Because Jev is non-autoregressive and returns one JSON document, there is nothing to stream — integrators (Pydantic AI, others) confirm the whole answer arrives as a single event. Pydantic AI's docs state it plainly: "Jev answers in one piece, so there is nothing to stream."

**Error shapes.** The official docs describe status codes (401 unauthorized, 422 validation, 429 rate-limited, 529 overloaded) but do not publish the literal error-body schema. Third-party probing shows a body of the form `{"detail":{"error_type":"authentication_error","message":"..."}}`, and some failures return a bare `{"error_type":"max_tokens_exceeded"}`. There are known doc-vs-actual discrepancies (a missing key returns 403 not 401; malformed questions have returned 400 not 422) — treat error handling defensively. **Rate limits:** 250,000 tokens/sec and 1,200 requests/min for `jev-1.13`, both dynamic; over either returns 429; retry with exponential backoff (SDKs do this and honor `retry-after` when present).

**OpenAI-compatible mapping.** Jev deliberately does *not* map onto `/v1/chat/completions`. On OpenRouter the wire contract is near-identical to the native API but served at `/api/alpha/decisions` with a `typesafe/` model prefix, and its response adds `id`, `provider`, and `usage.cost`. (One notable delta: OpenRouter's Noul criteria requires both `true` and `false` keys when criteria is present, whereas the native API treats them as optional.)

### Section 7 — Custom-built harnesses

There is a thriving cottage industry of custom Jev harnesses (the "awesome-jev" lists aggregate 300+ projects). Representative real examples:

- `jev-router` **/** `Switchboard` **/** `Jevonian` — proxies that put one Jev Choice in front of an LLM call to pick the model + reasoning effort per request, keeping the choice stable for prompt-cache continuity.
- `jev-axi`**,** `jev-guard`**,** `Reflex`**,** `pi-verdict` — PreToolUse gates that score each shell command for destructiveness/exfiltration/RCE; deterministic rules settle clear cases locally, Jev handles the gray zone, timeouts fail closed. (`jev-axi` reports scoring 44/44 on its labeled tool calls.)
- `fast-jev-compaction` **/** `jev-pruner` — Claude Code plugins that replace the compaction summary with per-tool-call "still needed?" Jev decisions.
- `DocJev` (LlamaIndex) — document classification/splitting library with a benchmark harness (a 40-document pilot classified 40/40 correctly at \~182 ms decision p50).
- `jev-harness`**,** `super-jev`**,** `JevLoop` — turn a raw Jev answer into a bounded action with thresholds and escalation.
- `jev-router` **(PyPI)** — a routing SDK with TypeSafe-direct and OpenRouter-Decisions adapters plus a verified cascade.

**Minimal custom harness sketch (Python, direct API):**

```python
import os, requests

def jev(state, questions, model="jev-latest"):
    r = requests.post(
        "https://api.typesafe.ai/v1/systemone",
        headers={"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}"},
        json={"state": state, "model": model, "questions": questions},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()

def gate_command(cmd):
    """Decide whether an agent's shell command can auto-run."""
    out = jev(
        state=cmd,
        questions={
            "destructive": {"type": "noul", "instructions": "Does this command delete data, rewrite git history, or touch production?"},
            "category": {"type": "choice", "instructions": "Classify the command",
                         "criteria": {"read_only": "Only reads state", "reversible": "Writes but easily undone", "destructive": "Hard to undo"}},
        },
    )
    a = out["answers"]
    if a["destructive"]["noul"] >= 0.2:          # threshold owned by your code
        return "human-approval"
    if a["category"]["choice"] == "read_only" and a["category"]["confidence"] >= 0.7:
        return "auto-run"
    return "human-approval"

```

The pattern in every harness is identical: an upstream step produces state → Jev makes typed judgments in one call → *your code* owns thresholds, authorization, and the action. Fail closed on errors/timeouts; log the response `model` id; run labeled data through your questions and fit thresholds before trusting probabilities.

---

## Open-Source Alternative: Laya (ConvAI Innovations)

**What it is.** Laya is a multilingual, non-autoregressive "System 1" decision model from ConvAI Innovations (author Nandakishor Mukkunnoth / NandhaKishorM), published on Hugging Face under **Apache-2.0**. It uses the same paradigm as Jev — give it a *state* (text/email/ticket/JSON) plus typed questions (`choice`, `score`, `noul`), get typed answers with calibrated probabilities in a single \~33 ms forward pass — and it never generates text. It is explicitly positioned as "the open counterpart to TypeSafe's Jev." It is trained with the same-named technique, RLCD (Reinforcement Learning for Calibrated Decisions). The founder describes the motivation as deciding "to…build a completely open, horizontal System 1 decision model family"; per jevmodel.org the GitHub repo was created 18 September 2026 and had about 7.9k stars and 667 forks by 21 September 2026.

**Model card details.** The repo holds three checkpoints:


| Checkpoint                               | Backbone         | Params | Context         | Best at                                       |
| ---------------------------------------- | ---------------- | ------ | --------------- | --------------------------------------------- |
| `convaiinnovations/laya` (root)          | ModernBERT-large | 421M   | 512             | English text, guardrails, email triage        |
| `convaiinnovations/laya-multilingual`    | mmBERT-base      | 322M   | 1024 (up to 8k) | 100+ languages, \~2.2× faster                 |
| `convaiinnovations/laya-typed-decisions` | ModernBERT-large | 421M   | 1024            | the four typed-decision workflows (0.766 acc) |


Install: `pip install laya`. Usage is either the built-in `Router` (auto-detects script/language and dispatches to the best checkpoint) or `laya.load(...)` for a single checkpoint. Weights are F32/F16 safetensors (\~808 MB English, \~647 MB multilingual). Live demo (HF Space), PyPI package, and GitHub (NandhaKishorM/laya) are public. Requires Python ≥ 3.10, torch, transformers.

**Latency.** Per the model card, single-question p50 is 32.8 ms for the 322M multilingual checkpoint and 39.5 ms for the 421M English checkpoint on a Tesla T4, versus Jev's third-party-measured 236–276 ms — roughly 7.8× faster on a single call. (Batched: down to \~6.8–7.2 ms/question.)

**Honest limits (from the card):** base checkpoints are near chance zero-shot on typed-decisions (0.362; 0.352 multilingual) — the 0.766 figure is the checkpoint *fine-tuned on that benchmark's own training split*; it ships over-confident (needs per-question-type temperature refitting to move ECE \~0.466→0.081); the ordinal `score` primitive is weakest; the English root collapses on non-Latin scripts; and it is weak on high-cardinality choice. On Banking77 the options "share the option budget: 77 labels get about 3 to 4 tokens each, and Banking77 accuracy falls to 0.425" (vs Jev 0.870) — fixable by raising `head_max_len` or shortlisting with `predict_shortlist`.

**Comparison table — Jev vs. Laya**


| Dimension                     | **TypeSafe Jev (1.13.0)**                         | **Laya (ConvAI, routed)**                                            |
| ----------------------------- | ------------------------------------------------- | -------------------------------------------------------------------- |
| License / weights             | Closed, hosted API only                           | **Apache-2.0, open weights**                                         |
| Cost                          | $0.042 / 1M input tokens, output free             | **$0 self-hosted** (your compute)                                    |
| Hosting                       | Hosted (TypeSafe/Vercel/Cloudflare/OpenRouter)    | **Self-host** (GPU/CPU/Apple Silicon via laya-mlx)                   |
| Params / architecture         | Undisclosed; proprietary parallel sampler         | 421M ModernBERT-large / 322M mmBERT-base                             |
| I/O paradigm                  | state + Choice/Score/Noul → typed answers + probs | **Identical** (choice/score/noul)                                    |
| Latency (p50, 1 question)     | 236–276 ms (third-party)                          | **32.8 ms (multilingual) / 39.5 ms (English)** on T4 — \~7.8× faster |
| Context                       | 32,000 tokens                                     | 512 (English) / 1024–8192 (multilingual)                             |
| Multilingual                  | No published benchmark                            | **45 of 51 languages** usable                                        |
| Zero-shot typed-decisions acc | 0.727 (published)                                 | 0.362 base; **0.766 fine-tuned** on that split                       |
| Calibration (ECE)             | 0.144 (published)                                 | 0.081 after temperature refit; ships worse (\~0.466)                 |
| High-cardinality choice       | Up to 255 options; strong (Banking77 0.870)       | Weak at defaults (0.425); needs tuning                               |
| Training                      | RLCD, synthetic data                              | RLCD (log+spherical+RPS rewards)                                     |
| Drops into Jev harnesses?     | —                                                 | **Not natively** (see below)                                         |


*Caveat on the table:* all Jev figures in Laya's card are third-party/published (ConvAI has no TypeSafe API access), with differing sample sizes and prompts — treat as indicative, not a controlled head-to-head. The \~7.8× speed and "beats Jev on accuracy" claims are the model author's own and the fine-tuned accuracy is on Laya's home-turf benchmark.

**Can it drop into the same harnesses?** Not directly. Laya's Python API (`laya.load()`, `router.predict(state, questions)`) returns a nested dict (`result["answers"]["department"]["choice"]`) that is *shape-similar* to Jev's but not wire-identical, and it is a self-hosted PyTorch model, not an HTTP endpoint. The hosted harnesses (Vercel `experimental_evaluate`, OpenRouter Decisions, Cloudflare `env.AI.run`, LangChain `TypeSafeClassifier`) target TypeSafe's API contract, so using Laya in them requires writing an adapter that serves Laya behind a compatible endpoint or maps its dict output into the framework's types. At least one community project (`Switchboard`) lists Laya as a planned/"coming soon" backend, and an Apple-Silicon port (`laya-mlx`) exists — but as of this writing Laya is a self-hosting alternative you wire in yourself, not a plug-compatible substitute.

---

## Recommendations

**Stage 1 — Decide if Jev fits at all (before writing any code).** For each candidate decision, ask: *"Given this state, tell me X"* where X is a Choice, Score, or yes/no probability from a **bounded, known-in-advance** answer set. If yes, it's a Jev candidate. If the step needs to generate prose/code or do open-ended reasoning, it is not — keep the LLM there. Pull last month's LLM calls and flag every one whose output became an enum, boolean, or number; those are your migration targets.

**Stage 2 — Prototype on your existing stack, one call at a time.** If you're on Vercel, use `experimental_evaluate` (pin `ai` ≥ 7.0.105 and a specific version — the API is experimental). If you're on OpenRouter already, use `/api/alpha/decisions`. If you want the lowest-level control, hit the TypeSafe API directly. Swap exactly one decision point (routing, tool-gate, triage), keep everything downstream unchanged, and measure latency, cost, and accuracy against your current setup on *your* data.

**Stage 3 — Calibrate before automating.** Run labeled examples through the same questions and compare predicted probabilities to observed outcomes. Set thresholds **per action, not per model**: read-only/low-stakes actions can act at \~0.7; destructive/high-stakes actions need \~0.9+ and a human-review path below the floor. Keep classification separate from authorization. Log the response `model` id and re-validate thresholds whenever `jev-latest` moves.

**Stage 4 — Choose hosted vs. self-hosted.** Use **Jev** if you want zero-ops, the 255-option/32K-context headroom, strong out-of-box calibration, and don't mind a closed API and per-token cost. Evaluate **Laya** if you need on-prem/air-gapped deployment, data residency, zero marginal cost at scale, multilingual coverage, or full control — but budget for **fine-tuning on your own workflow** (the base model is near-chance zero-shot) and temperature calibration. For high-cardinality (&gt;20-option) classification, Jev is currently the safer default.

**Benchmarks/thresholds that would change the recommendation:** If your own head-to-head shows Jev's accuracy gap (TypeSafe's own 67.8% vs 74.1%, widest on invoice processing at 61.8% vs 79.1%) is intolerable for a decision with real downstream cost, keep that specific decision on an LLM or add a low-confidence→LLM/human escalation tier. If your volume is high enough that per-token cost dominates and you can absorb fine-tuning effort, Laya's $0 marginal cost flips the calculus toward self-hosting.

## Caveats

- **Vendor claims are unverified and best-case.** The "20–200× faster / 40–400× cheaper" (peak 193.6×/444.6×) figures are TypeSafe's own, measured against *agreement with other frontier models* rather than ground truth. TypeSafe discloses a \~6-point aggregate accuracy gap (67.8% vs 74.1% for GPT-5.6 Sol, across 711 cases in four tasks). Independent corroboration is limited: Every's extraction test found Jev "roughly 25x faster and 580x cheaper" (directionally supportive), and one LangChain online-eval benchmark was favorable, while some community tests were mixed (e.g., a reranking run where Jev alone did not beat vector retrieval).
- **"Never hallucinates" is narrow.** Jev cannot emit an off-schema value, but it can return a schema-valid, semantically wrong answer — the CEO acknowledged this directly. Type safety ≠ correctness.
- **Everything is brand-new (launched Sept 15, 2026).** All integrations are days-to-weeks old; the Vercel `experimental_evaluate` API and OpenRouter Decisions endpoint are explicitly experimental/alpha and may change. No multi-month production track record exists. Pin versions.
- **Doc gaps and inconsistencies.** The official docs don't publish the error-body JSON schema; observed status codes differ from documented ones (403 vs 401, 400 vs 422). Rate limits are explicitly "adjusting dynamically."
- **The explainx.ai "agent routing" framing is a use case, not a definition.** Several of the richest sources (explainx.ai, firecrawl, dev.to, Jev Patterns, madewithjev, awesome-jev) are third-party and vary in independence; primary facts here are anchored to TypeSafe, Vercel, Cloudflare, OpenRouter, and LangChain's own docs where possible.
- **Laya comparison caveats** are the author's own, self-reported, home-benchmark numbers with no TypeSafe API access; treat the head-to-head as indicative only.

