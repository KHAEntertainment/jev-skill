# Jev access paths

Verified 2026-09-22 against the primary sources linked in each section. If a live page
disagrees, the live page wins.

Contents: [Comparison](#comparison) · [TypeSafe direct](#typesafe-direct) ·
[OpenRouter](#openrouter) · [Vercel AI SDK and AI Gateway](#vercel-ai-sdk-and-ai-gateway) ·
[Cloudflare Workers AI](#cloudflare-workers-ai) · [LiteLLM proxy](#litellm-proxy) ·
[Not available](#not-available) · [Self-hosted alternative: Laya](#self-hosted-alternative-laya)

## Comparison

| | TypeSafe direct | OpenRouter systemone | OpenRouter Decisions | Vercel AI Gateway | Cloudflare |
|---|---|---|---|---|---|
| Endpoint | `POST https://api.typesafe.ai/v1/systemone` | `POST https://openrouter.ai/api/v1/systemone` | `POST https://openrouter.ai/api/alpha/decisions` | `POST https://ai-gateway.vercel.sh/v1/evaluate`, or TypeSafe-compatible `…/typesafe/v1/systemone` | `env.AI.run` or `POST …/accounts/{id}/ai/run` |
| Auth env | `TYPESAFE_API_KEY` | `OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` | `AI_GATEWAY_API_KEY` or OIDC (`VERCEL_OIDC_TOKEN`) | Worker binding / `CLOUDFLARE_API_TOKEN` |
| Model id | `jev-latest`, `jev-preview`, `jev-1.13.0` | `~typesafe/jev-latest`, `typesafe/jev-1.13` | same (`typesafe/jev-1.13` pinned; `~typesafe/jev-latest` moves) | `typesafe-ai/jev` (also `typesafe-ai/jev-latest`) | `typesafe/jev` |
| Wire format | native | native (TypeSafe SDK works) | native + `id`, `provider`, `usage.cost`; stricter criteria | camelCase (`/v1/evaluate`) or native (`/typesafe`) | native |
| Stability | GA | documented | **alpha** | experimental SDK surface | GA listing |
| Extra | request id header | one bill for all models | trace/session fields, `provider` routing | ZDR / no-training per request, BYOK | edge runtime |

Price is $0.042 per 1M input tokens with output free on every path. Vercel Gateway was free
through 2026-09-25. Cloudflare's price is shown only in its dashboard.

## TypeSafe direct

Docs: `https://docs.typesafe.ai/api.md`, `https://docs.typesafe.ai/models.md`, OpenAPI at
`https://api.typesafe.ai/openapi.json`. Keys at `https://console.typesafe.ai/keys`.
Playground at `https://console.typesafe.ai/playground`.

- **Endpoints:** `POST /v1/systemone` and `GET /v1/models`. The models endpoint lists
  aliases only; versioned ids are accepted anyway. There is **no batch endpoint**. Batch by
  putting many questions in one request. A JSON array as `state` is still *one* state.
- **Request:** `{state, model, questions}`, all required. `questions` maps your ids to
  `{type, instructions, criteria}`. **Ids are not sent to the model**, so put the whole
  question in `instructions`.
  - `choice`: `criteria` maps option name to description or `null`; up to 255 options.
  - `score`: `criteria` is an ordered array of 2-10 level descriptions, indexed from 0.
  - `noul`: optional `criteria` `{true, false}`, either side optional.
- **Response:** `{model, answers, usage:{input_tokens, output_tokens}}`. `model` is the
  resolved version (log it). Header `x-typesafe-request-id` (observed live on success and
  error responses; not in the OpenAPI spec).
  - choice: `{type, choice, probabilities, confidence}`
  - score: `{type, score, legend, probabilities, confidence}`. `score` is the
    probability-weighted mean and can land between levels.
  - noul: `{type, noul}`, with no confidence.

  Probabilities are rounded to 2 decimals, so a distribution may sum to 0.99.
- **Context:** 64k tokens per request; 32k for `state` plus the longest single question.
- **Rate limits (jev-1.13.0):** 250,000 tokens/s and 1,200 requests/min, both "adjusting
  dynamically". Higher limits via sales@typesafe.ai.
- **Errors observed live:**
  - no key -> **403** `{"detail":{"error_type":"authentication_error","message":"Must supply an API key!…"}}`.
    Re-checked live on 2026-09-22; `api.md` documents 401 for this case, and the live API
    disagrees.
  - bad key -> **401**, same shape
  - validation -> **422** `{"detail":[{"loc":["body","questions","x","score","criteria"],"msg":"Field required","type":"missing"}]}`
  - 429 rate-limited, 529 overloaded: back off, and honor `retry-after` / `retry-after-ms`

  Some SDK exceptions (400, 403) are not in the HTTP docs; handle them defensively.
- **Aliases:** `jev-latest` is the latest stable, the SDK default, and currently 1.13.0.
  `jev-preview` is the latest release, stable or not, and also 1.13.0 now. Pin
  `jev-1.13.0` once thresholds are tuned. Short forms like `jev` or `jev-1.13` appear in
  some examples but are not on the models page, so avoid them for TypeSafe direct.
- **Data:** "Jev is not trained on customer requests or responses." ZDR is for enterprise
  customers via privacy@typesafe.ai. There is no fine-tuning; everyone shares the same
  weights.
- **Free credit:** third parties report $5 on signup; no primary source confirms it.

```bash
curl -sS https://api.typesafe.ai/v1/systemone \
  -H "Authorization: Bearer $TYPESAFE_API_KEY" -H "Content-Type: application/json" \
  -d '{"state":"Payouts failing for 3 days, losing sales","model":"jev-1.13.0",
       "questions":{"urgent":{"type":"noul","instructions":"The message conveys urgency"}}}'
```

SDKs: see `frameworks.md` (TypeSafe SDKs section).

## OpenRouter

Docs: guide `https://openrouter.ai/docs/guides/community/jev`, tutorial
`…/community/jev-tutorial`, TypeSafe SDK guide `…/community/typesafe-sdk`, API reference
`https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request`,
recipes at `https://openrouter.ai/labs/jev`. Keys at `https://openrouter.ai/settings/keys`.

Jev is **not** in `/v1/chat/completions` and is not usable through OpenAI-compatible clients.
Both Jev endpoints below were confirmed to exist on 2026-09-22 (they return 401 for a missing
key, where an unknown route returns 404).
The only upstream provider is TypeSafe. Endpoint metadata:
`GET https://openrouter.ai/api/v1/models/typesafe/jev-1.13/endpoints` reports modality
`text->decisions`, context 32000, prompt price 0.000000042, completion 0, and no
supported parameters. Model ids are `typesafe/jev-1.13` (dated snapshot
`typesafe/jev-1.13-20260917`) and the alias `~typesafe/jev-latest`.

### Option A: `/api/v1/systemone` (TypeSafe wire format)

Use this when you want the TypeSafe SDKs, or code that can switch between TypeSafe direct
and OpenRouter by changing only the base URL and key.

```python
from typesafe_sdk import TypeSafeClient
client = TypeSafeClient(api_key=os.environ["OPENROUTER_API_KEY"],
                        base_url="https://openrouter.ai/api",
                        model="typesafe/jev-1.13")
```
```ts
const client = new TypeSafeClient({ apiKey: process.env.OPENROUTER_API_KEY, baseURL: "https://openrouter.ai/api" });
```

The same works with `TYPESAFE_BASE_URL=https://openrouter.ai/api`. Only `POST /v1/systemone`
works through OpenRouter; the SDK's `models.list()` fails. Bare model names like `jev-1.13`
are rewritten to `typesafe/jev-1.13`.

### Option B: `/api/alpha/decisions` (Decisions API, alpha)

Use this when you are on `@openrouter/sdk`, the Python `openrouter` SDK, or
`@openrouter/ai-sdk-provider`, or you want OpenRouter's `usage.cost`, tracing, and provider
routing fields.

- **Request:** `model`, `state`, `questions` (required); optional `provider`, `session_id`
  (≤256 chars), `user` (≤256), and `trace` (`trace_id`, `trace_name`, `span_name`,
  `generation_name`, `parent_span_id`, plus custom keys).
- **Stricter criteria than native:**
  - A `noul` question with `criteria` must include **both** `true` and `false`. Either
    omit `criteria` entirely or give both sides.
  - `score` criteria cannot contain `null`.
- **Response:** the native response plus `id`, `provider` (`"TypeSafe"`), and `usage.cost`
  (USD):
  ```json
  {"id":"gen-dec-…","model":"typesafe/jev-1.13-20260917","provider":"TypeSafe",
   "answers":{"is_bug":{"type":"noul","noul":0.96},
              "team":{"type":"choice","choice":"payments","confidence":0.75,"probabilities":{…}}},
   "usage":{"input_tokens":476,"output_tokens":70,"cost":0.000019992}}
  ```
- **Provider object:** `allow_fallbacks`, `data_collection` (`allow`/`deny`), `order`, `only`,
  `ignore`, `max_price`, `sort`, `zdr`, and more. `provider: {zdr: true}` routes, because
  the Jev endpoint is on OpenRouter's ZDR list. Fallbacks have nowhere to go while
  TypeSafe is the sole provider.
- **Errors:** 400, 401, **402 (insufficient credits: prepaid balance required)**, 403, 404,
  413, 429, 500, 502, 503, 524, 529. Body:
  `{"error":{"code":int,"message":str,"metadata":obj|null}}`.
- **Rate limits:** OpenRouter documents no Jev-specific limit; TypeSafe's upstream limits
  apply.
- **SDKs:**
  - TS `@openrouter/sdk`: `openRouter.alpha.decisions.create({ decisionsRequest: {model, questions, state} })`
  - Python `openrouter`: `open_router.alpha.decisions.create(model=…, questions=…, state=…)`,
    with typed errors up to `ProviderOverloadedResponseError` (529)
  - AI SDK: `@openrouter/ai-sdk-provider` ≥ 3.1.0 with `openrouter.decisionModel('typesafe/jev-1.13')`
    (alias `evaluationModel`), requiring `ai` ≥ 7.0.103. Confidence is at
    `providerMetadata.openrouter.answers[id].confidence`. It validates criteria before
    sending and throws `InvalidArgumentError`. `providerOptions.openrouter` accepts `user`,
    `provider`, `session_id`, `trace`.
- **Docs quirk:** the API reference renders the URL as `…/api/v1/api/alpha/decisions`. The
  real path is `https://openrouter.ai/api/alpha/decisions`.
- **Not verified:** BYOK for TypeSafe on OpenRouter; first SDK versions shipping
  `alpha.decisions`.

## Vercel AI SDK and AI Gateway

Docs: `https://vercel.com/kb/guide/typesafe-jev-and-ai-sdk`,
`https://vercel.com/docs/ai-gateway/modalities/evaluation`,
`https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe`,
`https://ai-sdk.dev/providers/ai-sdk-providers/typesafe-ai`, reference
`vercel/ai/content/docs/07-reference/01-ai-sdk-core/14-evaluate.mdx`.

- **Function:** `experimental_evaluate` from `ai`. It appeared in 7.0.103; 7.0.105+ resolves
  plain-string ids such as `'typesafe-ai/jev'` through the Gateway (latest was 7.0.111 on
  2026-09-22). The `experimental_` prefix means the signature can change in minor
  releases, so pin the `ai` version.
- **Inputs:** `model`, `state`, `questions` (required, non-empty); optional `maxRetries`
  (default 2), `abortSignal`, `headers`, `providerOptions`, `telemetry`, `runtimeContext`,
  `onStart`, `onEnd`. There is no temperature and no streaming.
- **Question types:** `choice`, `score`, `boolean`. Answers:
  - boolean -> `{type:'boolean', probability}`
  - choice -> `{choice, probabilities?}`
  - score -> `{score, probabilities?}`

  Choice results are typed as a union of your option keys.
- **Confidence:** at `result.providerMetadata?.typesafe?.confidence[questionId]` (choice and
  score only). `result.rounding` reports decimal places. It is unconfirmed whether Gateway
  responses populate `typesafe.confidence`, so code defensively.
- **Errors:** `Experimental_EvaluationUnsupportedQuestionTypeError`, `InvalidArgumentError`,
  and `InvalidResponseDataError` (not retried).
- **Providers:**
  - Gateway: the string `'typesafe-ai/jev'`, or `gateway.evaluationModel('typesafe-ai/jev')`
    from `@ai-sdk/gateway` ≥ 4.0.85. Auth is `AI_GATEWAY_API_KEY`, or OIDC via
    `vercel link && vercel env pull`. The local OIDC token lasts about 12 h; re-pull on a 401.
  - Direct, no Gateway: **`@ai-sdk/typesafe-ai`**,
    `createTypeSafeAi({apiKey, baseURL}).evaluationModel('jev-latest')`, env
    `TYPESAFE_AI_API_KEY` (note: *not* `TYPESAFE_API_KEY`).
  - OpenRouter: `@openrouter/ai-sdk-provider` (see above).
- **Gateway options:** `providerOptions: { gateway: { zeroDataRetention: true, only: ['typesafe-ai'] } }`.
  There is also a "no training" option.
- **Gateway raw HTTP:** `POST https://ai-gateway.vercel.sh/v1/evaluate`, with a camelCase
  response and `providerMetadata.gateway.cost`. BYOK is supported.
- **TypeSafe-compatible base URL:** `https://ai-gateway.vercel.sh/typesafe`. Point the
  TypeSafe SDK at it with `AI_GATEWAY_API_KEY` and model `typesafe-ai/jev`. Errors there
  look like `{"message", "error_type"}`, not nested under `detail`.
- **Testing:** `Experimental_EvaluationMockModelV4` from `ai/test` returns canned answers
  with no network (see `templates/typescript/ai-sdk-evaluate.test.ts`). The SDK validates
  mock answers like real ones: a choice's `probabilities` must cover every option and sum to
  1, or it throws `InvalidResponseDataError`. Build complete distributions or omit
  `probabilities`.

## Cloudflare Workers AI

Docs: `https://developers.cloudflare.com/ai/models/typesafe/jev/`.

```ts
const out = await env.AI.run('typesafe/jev', { state, questions }); // native types: noul/choice/score
```

The REST form is `POST https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/ai/run`
with `{"model":"typesafe/jev","input":{state,questions}}`. Output is the native TypeSafe
shape. Context is 32k. Use this when the decision runs at the edge next to a Worker.

## LiteLLM proxy

- **Pass-through:** replace `https://api.typesafe.ai` with `<proxy>/typesafe`. It still uses
  your `TYPESAFE_API_KEY`, and LiteLLM tracks cost. Docs:
  `https://docs.litellm.ai/docs/pass_through/typesafe`.
- LiteLLM's Jev auto-router and relevance guardrail are covered in `frameworks.md`.

## Not available

As of 2026-09-22, no primary source shows Jev on **Google Vertex AI, AWS Bedrock, Azure AI
Foundry, Together, or Fireworks**. TypeSafe's docs name no cloud hosts, OpenRouter lists
TypeSafe as the only provider, and Vercel's own integration roundup lists only TypeSafe,
AI Gateway, Cloudflare, and OpenRouter. Snippets claiming wider availability cite nothing.
If a user asks for one of these, say it is unverified and check the provider's model
catalog live before planning around it.

There is **no official MCP server or CLI**. Community MCP servers exist (for example several
`typesafe-mcp` repos); vet them like any third-party code before use.

## Self-hosted alternative: Laya

Laya (ConvAI Innovations, Apache-2.0, `pip install laya`, HF `convaiinnovations/laya*`) is an
open-weights decision model with the same state + choice/score/noul paradigm. It uses
ModernBERT-large (421M, 512 context) and mmBERT-base (322M, 1024 context, multilingual)
backbones, and runs at about 33-40 ms per decision on a T4.

Consider it only for air-gapped or on-prem deployments, data residency, or zero marginal
cost at very high volume, and budget for **fine-tuning** it. Its base checkpoints are near
chance zero-shot on typed decisions (0.36), ship over-confident (temperature refit
needed), and are weak on high-cardinality Choice.

It is **not wire-compatible** with Jev harnesses: its output dict is similar in shape but
differs, and there is no hosted HTTP endpoint. You need an adapter that serves it behind a
TypeSafe-shaped `/v1/systemone`. Figures come from its own model card, benchmarked on its
own data.
