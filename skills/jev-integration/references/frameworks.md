# Framework and SDK integrations

Verified 2026-09-22. Every integration here is one to two weeks old, so pin versions and
re-check the linked page before relying on a signature. Snippets were taken from the linked
sources; recheck exact spelling against them before shipping.

Contents: [TypeSafe SDKs](#typesafe-sdks) · [Vercel AI SDK](#vercel-ai-sdk) ·
[OpenRouter SDKs](#openrouter-sdks) · [LangChain Python](#langchain-python) ·
[LangChain.js](#langchainjs) · [Pydantic AI](#pydantic-ai) · [TanStack AI](#tanstack-ai) ·
[Effect](#effect) · [LiteLLM](#litellm) · [Composio](#composio) · [BAML](#baml) ·
[LlamaIndex / DocJev](#llamaindex--docjev) · [No official support](#no-official-support) ·
[Choosing](#choosing)

## TypeSafe SDKs

### Python: `typesafe-sdk`

Version 0.7.1, Python ≥ 3.10. Docs: `https://docs.typesafe.ai/sdk/python/usage.md`.

```python
from typesafe_sdk import TypeSafeClient, AsyncTypeSafeClient, Choice, Score, Noul, NoulCriteria, RetryPolicy

client = TypeSafeClient(          # reads TYPESAFE_API_KEY, TYPESAFE_BASE_URL, TYPESAFE_DEFAULT_MODEL
    model="jev-1.13.0",
    timeout=5.0,                  # per HTTP operation; default 10.0
    retry=RetryPolicy(max_retries=2, timeout=8.0),  # timeout = total retry budget (default 30.0)
)
resp = client.system_one(state=ticket, questions={
    "team": Choice(instructions="Which team should handle this ticket?",
                   criteria={"billing": "Charges, invoices, refunds", "technical": "Bugs, integrations",
                             "other": "Anything else"}),
    "urgent": Noul(instructions="The customer needs a reply within the hour"),
})
resp.choices["team"].choice, resp.choices["team"].confidence, resp.nouls["urgent"].noul
resp.request_id, resp.usage
```

- **Constructor (keyword-only):** `api_key`, `model`, `retry`, `timeout`, `headers`,
  `transport`, `http_client`, `base_url`.
- **Call options:** `system_one` also takes `model`, `retry`, `timeout`, `extra_headers`,
  `extra_body`, and `response_model=` (a Pydantic model, since 0.7.0).
- **Retries:** `RetryPolicy` defaults are 2 retries, 0.5-5 s backoff with jitter, statuses
  408/429/5xx, `respect_retry_after=True`. `RetryPolicy(max_retries=0)` disables retries.
- **Exceptions:** `TypeSafeError` is the base, with `TypeSafeAPIError` subclasses
  (`…AuthenticationError` 401, `…PermissionDeniedError` 403,
  `…UnprocessableEntityError` 422, `…RateLimitError` 429 with `.retry_after_ms`,
  `…InternalServerError` 5xx), plus `TypeSafeAPIConnectionError` and
  `TypeSafeAPITimeoutError`.
- **Async:** `AsyncTypeSafeClient` has the same API; use `await client.system_one(...)`.
- **Alternate endpoints:** OpenRouter or Vercel Gateway via `base_url` (see
  `access-paths.md`).

### JavaScript/TypeScript: `@typesafe-ai/sdk`

Version 0.6.0, Node ≥ 20, ESM and CJS. Docs: `https://docs.typesafe.ai/sdk/javascript.md`.

```ts
import { TypeSafeClient, choice, noul, score } from "@typesafe-ai/sdk";
const client = new TypeSafeClient({ defaultModel: "jev-1.13.0", timeout: 5000, retry: { maxRetries: 2 } });
const res = await client.systemOne(
  { state: { message }, questions: {
      team: choice("Which team should handle this ticket?", { billing: "Charges, refunds", technical: "Bugs", other: null }),
      urgent: noul("The customer needs a reply within the hour"),
  } },
  { signal: AbortSignal.timeout(6000) },
);
res.answers.team.choice; res.answers.team.confidence; res.answers.urgent.noul;
```

- **Answer types** are inferred from the questions you pass.
- **Timeout:** `timeout` applies per attempt (default 10000 ms), with **no total budget**.
  Pass an `AbortSignal` for a hard deadline.
- **Errors:** `APIError` subclasses (`AuthenticationError`, `PermissionDeniedError`,
  `UnprocessableEntityError`, `RateLimitError`, `InternalServerError`), plus
  `APIConnectionError`, `APITimeoutError`, and `APIUserAbortError`.
- **Browsers:** blocked unless `dangerouslyAllowBrowser: true`. Don't set it; keep keys
  server-side.

## Vercel AI SDK

`ai` ≥ 7.0.105 with `experimental_evaluate`. Details are in `access-paths.md`, and a
template is at `templates/typescript/ai-sdk-evaluate.ts`.

```ts
import { experimental_evaluate as evaluate } from "ai";
const r = await evaluate({
  model: "typesafe-ai/jev",                         // Gateway; or typeSafeAi.evaluationModel('jev-1.13.0')
  state: { subject, message },
  questions: {
    team: { type: "choice", instructions: "Which team should handle this ticket?",
            criteria: { billing: "Charges, refunds", technical: "Bugs, outages", other: "Anything else" } },
    refund: { type: "boolean", instructions: "Is the customer asking for money back?" },
  },
  providerOptions: { gateway: { zeroDataRetention: true } },
});
r.answers.team.choice;                                  // 'billing' | 'technical' | 'other'
r.providerMetadata?.typesafe?.confidence?.team;         // choice/score only
r.answers.refund.probability;
```

## OpenRouter SDKs

- **TS `@openrouter/sdk`:** `openRouter.alpha.decisions.create({ decisionsRequest: {...} })`,
  or the standalone function `alphaDecisionsCreate` from
  `@openrouter/sdk/funcs/alphaDecisionsCreate.js`.
- **Python `openrouter`:** `open_router.alpha.decisions.create(model=…, questions=…, state=…)`.
- **AI SDK provider:** `@openrouter/ai-sdk-provider` ≥ 3.1.0,
  `evaluate({ model: openrouter.decisionModel('typesafe/jev-1.13'), … })`. Confidence is at
  `providerMetadata.openrouter.answers[id].confidence`.
- **Rules:** remember the Decisions criteria rules (both Noul sides, no `null` in Score).
  Templates: `templates/typescript/openrouter-decisions.ts` and
  `templates/python/openrouter_decisions.py`.

## LangChain Python

Package `langchain-typesafe` 0.0.1a3 (pre-release). Docs:
`https://docs.langchain.com/oss/python/integrations/providers/typesafe`. Blog:
`https://www.langchain.com/blog/building-a-harness-with-jev`.

```python
from langchain_typesafe import Choice, Noul, Score, TypeSafeClassifier
clf = TypeSafeClassifier()                      # TYPESAFE_API_KEY, optional TYPESAFE_BASE_URL
r = clf.invoke({"state": text, "questions": {
    "urgent": Noul(instructions="Does this need attention right now?"),
    "team": Choice(instructions="Which team should pick this up?",
                   criteria={"infra": "Deploys, availability, incidents", "billing": "Payments, invoices"}),
}})
r.nouls["urgent"].noul, r.choices["team"].choice, r.choices["team"].confidence
```

- **Classifier:** a Runnable (`@beta`), so it composes in LCEL, supports `ainvoke`, and is
  traced in LangSmith.
- **Middleware:** requires `pip install "langchain-typesafe[experimental]"` and imports
  from `langchain_typesafe.experimental.middleware`:
  - `ModelRouterMiddleware(choices={"fast": ModelChoice(model=…, criteria=…), "powerful": …}, instructions=…)`
    picks the model per turn.
  - `AutoModeMiddleware(tools=[…])` gates risky tool calls; tune it with
    `NoulCriteria(true=…, false=…)`.
  - Both plug into `create_agent(model, middleware=[…])`.
- **LangGraph:** use a Jev Choice as the conditional-edge function, or store answers in
  state from an `AgentMiddleware.before_agent`.

## LangChain.js

`npm i @langchain/typesafe @langchain/core` (0.0.1). Questions are passed to the
constructor, and `invoke` takes only the state.

```ts
import { TypeSafeClassifier } from "@langchain/typesafe";
const clf = new TypeSafeClassifier({ questions: { urgent: { type: "noul", instructions: "Does this need attention now?" } } });
const r = await clf.invoke("The deploy failed twice …");
r.nouls.urgent.noul;
```

- **Options:** `apiKey`, `baseUrl`, `timeout` (30000), `maxRetries` (2).
- **No middleware in JS** (confirmed in docs PR #6092). Build routing and gating yourself.

## Pydantic AI

`pip install "pydantic-ai-slim[typesafe]"`. Docs: `https://pydantic.dev/docs/ai/models/typesafe/`.
Each field of `output_type` becomes one question:

| Field type | Becomes |
|---|---|
| `bool` | Noul, true if p ≥ threshold |
| `Literal` / `Enum` | Choice |
| bounded `float` 0-1 | raw probability |
| `IntEnum` with member docstrings | Score |
| `list[Literal]` | multi-select |
| `Literal \| None` | Choice with a "none" option |
| nested model | dotted question ids |

Not supported: `str`, unbounded numbers, datetimes, unions of models, files.

```python
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.typesafe import TypeSafeModelSettings

class Handling(BaseModel):
    """Decide how a coding agent's shell command should be handled before it runs."""
    safe_to_run: bool = Field(description="Is this command safe to run without a human looking at it?")

agent = Agent("typesafe:jev-1.13.0", output_type=Handling,
              model_settings=TypeSafeModelSettings(typesafe_boolean_threshold=0.9))
res = agent.run_sync("pytest tests/test_agent.py")
res.output.safe_to_run; res.response.provider_details["confidence"]
```

- **Settings:** `typesafe_boolean_threshold` (default 0.5; raise it for safety decisions),
  `typesafe_tool_call_threshold` (0.6), `timeout`.
- **Documented patterns:**
  - `FallbackModel('typesafe:jev-latest', 'openai:…', fallback_on=[…])` for an LLM
    cascade.
  - `SelectModel` for per-step routing.
  - `Hooks(before_tool_execute=…)` with `SkipToolExecution` as a tool gate.
- **Caveat:** Pydantic warns that its defaults come from a small internal set. Validate
  them on your own data.

## TanStack AI

`@tanstack/ai` + `@tanstack/ai-typesafe` 0.1.0. Docs: `https://tanstack.com/ai/latest/docs/adapters/typesafe`.

```ts
import { decide, choice, score, boolean } from "@tanstack/ai";
import { typesafeDecider } from "@tanstack/ai-typesafe";
const r = await decide({ adapter: typesafeDecider("jev-1.13.0"), state: ticket, questions: {
  queue: choice({ instructions: "Which team should handle this ticket?", options: { billing: "Payments", tech: "Bugs" } }),
  urgency: score({ instructions: "How urgent is this ticket?", levels: ["low", "medium", "high"] }),
  refund: boolean({ instructions: "Is the customer asking for a refund?" }),
} });
```

- **Naming:** TanStack says `options` / `levels` rather than `criteria`.
- **Results:** each answer has `.value`, `.probability`, `.confidence`; usage is at
  `r.meta.usage`.
- **Other adapters:** `openRouterDecider`, `vercelGatewayDecider`, `cloudflareDecider`, and
  `createTypesafeDecider(model, key, {baseURL, timeout, …})`.

## Effect

`@effect/ai-typesafe` (4.0.0-rc) on `effect/unstable/ai`. Build definitions with
`Decision.make({ input, decisions })`, using `classify` (Choice), `rate` (Score), and
`probability` (Noul), then run `DecisionModel.decide(definition, { input })` to get
`{ answers, usage }`. The provider layer reads `TYPESAFE_API_KEY`. The API is unstable
(release-candidate line), so use it only in Effect codebases already on 4.0 RCs.

## LiteLLM

- **Pass-through:** `<proxy>/typesafe/v1/systemone`.
- **Auto-routing classifier** (`docs/proxy/auto_routing.md`): one Jev Choice over model
  tiers, with a circuit breaker and heuristic fallback. It logs
  `classifier_probabilities`, `classifier_confidence`, and `classifier_cost`.
  ```yaml
  classifier_type: jev
  jev_classifier_config: { model: jev-latest, timeout_ms: 3000, circuit_breaker_enabled: true }
  classifier_fallback: heuristic
  ```
- **Relevance guardrail** (`docs/proxy/guardrails/typesafe`): `guardrail: typesafe`,
  `mode: pre_call`, `relevance_threshold: 0.2`. It **fails open by default**; set
  `unreachable_fallback: fail_closed` if it guards anything safety-relevant.

## Composio

`@composio/typesafe`, `composio-typesafe`. `provider.decide(toolSet, task)` returns
`call` / `partial` / `abstain` with confidence. Helpers are `shortlistTools` and
`confidenceGate` (fails closed). It is merged on the `next` branch; check npm before
depending on it.

## BAML

Nightly toolchain only (`baml toolchain use nightly`). A function with
`client: "typesafeai/jev-latest"` maps its return type onto questions: `bool` becomes Noul,
enums and literal unions become Choice, and a class becomes one question per field. No
`string`, `int`, or array outputs. Unsupported types fail at runtime, not compile time.
Avoid it for production until it lands on stable.

## LlamaIndex / DocJev

`jerryjliu/docjev` is a personal repo (Apache-2.0), not the run-llama org. It does document
classification and splitting from YAML rules. Its README says its probability and
confidence are **not** claimed to be calibrated. The community `llama-index-jev` package
provides a reranker/selector.

## No official support

As of 2026-09-22, **Mastra** (feature request #24343 only), **CrewAI**, **Agno**, **AG2**
(feature request only), **OpenAI Agents SDK**, and **Claude Agent SDK** have no official Jev
integration. For these, call the TypeSafe SDK directly:

- from a tool function
- from a guardrail callback (OpenAI Agents SDK input/output guardrails; see community
  `typesafe-guardrails`)
- from a hook (Claude Agent SDK `PreToolUse` callback hooks, which, unlike Claude Code
  command hooks, *block* on timeout)
- from a router step before the LLM call

Community wrappers exist (for example `mastra-jev`). Treat them as unvetted.

## Choosing

1. Use the integration for the framework the project already runs. Don't add a framework
   just to call Jev; the raw SDK is three lines.
2. If the framework integration is experimental or nightly and the call is on a critical
   path, prefer the TypeSafe SDK inside your own thin wrapper. You get a stable wire
   contract and control over timeouts and retries.
3. For portability between TypeSafe and OpenRouter, use the TypeSafe SDK and switch
   `base_url` + key via config.
