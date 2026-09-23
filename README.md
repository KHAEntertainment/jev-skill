# jev-integration

An agent skill that decides **whether** and **how** to integrate
[Jev](https://docs.typesafe.ai/models.md), TypeSafe AI's non-generative "System One" decision
model, into a project. It covers access paths, framework and SDK choice, harness design,
calibration, and production operations.

It works with Claude Code (as a plugin) and with any agent supported by the
[`skills` CLI](https://github.com/vercel-labs/skills), including Codex, Cursor, OpenCode,
Gemini CLI, GitHub Copilot, and Pi.

> Verified against primary sources on **2026-09-22**, one week after Jev launched. The
> Jev ecosystem is moving fast. The skill tells agents to re-check the live page for their
> chosen path before writing code, and to trust the live page over the skill when they
> disagree.

---

## What Jev is (in one paragraph)

Jev is a decision model, not an LLM. You send a **state** (text or JSON) and a set of typed
**questions**:
- **Choice:** pick one of up to 255 options.
- **Score:** a position on a 2-10 level rubric.
- **Noul:** the probability that a yes/no statement is true.

One non-autoregressive forward pass returns typed answers with calibrated probabilities.
It cannot generate prose or code. It costs $0.042 per 1M input tokens with free output and
typically answers in ~100-500 ms, however many questions you batch. It fits the bounded
decisions inside software and agent loops: routing, triage, tool-call gating, reranking,
verification. It is not a replacement for an LLM.

## How this relates to TypeSafe's official skill

TypeSafe publishes an official skill,
[`typesafe-ai/skills`](https://github.com/typesafe-ai/skills). It is excellent at **question
design**: choosing primitives, writing atomic questions, structuring state, and wording
criteria. This skill **does not repeat that**. It defers to the official skill (or to
`docs.typesafe.ai`) for question wording and adds the integration layer the official skill
leaves out:

| Topic | Official `typesafe-ai` skill | `jev-integration` (this) |
|---|---|---|
| Question design, primitives, state structure | ✅ | defers to official |
| Jev vs LLM vs plain code (fit test, anti-fits) | brief | ✅ |
| Access paths: TypeSafe, OpenRouter (both endpoints), Vercel AI SDK/Gateway, Cloudflare, LiteLLM | ❌ | ✅ |
| Framework choice: AI SDK, LangChain (py/js), Pydantic AI, TanStack, Effect, Composio, BAML | ❌ | ✅ |
| Harness patterns: tool gates, routers, triage, rerank, cascades, pruning, guardrails | ❌ | ✅ |
| Calibration procedure, version pinning, retries/timeouts, fail-open vs fail-closed | brief | ✅ |
| Tested code templates and a smoke-test script | ❌ | ✅ |

**Install both** for the best results.

## What's inside

```
jev-skill/
├── .claude-plugin/plugin.json          # Claude Code plugin manifest ("jev")
├── skills/jev-integration/
│   ├── SKILL.md                        # the workflow: fit test → access path → framework
│   │                                   #   → harness pattern → non-negotiables → calibration
│   ├── references/
│   │   ├── access-paths.md             # endpoints, auth, model ids, wire differences, errors
│   │   ├── frameworks.md               # per-framework install + minimal code + maturity
│   │   ├── harness-patterns.md         # 8 patterns with architecture, policy, fail mode
│   │   └── calibration-and-ops.md      # thresholds, pinning, retries, cost, weak spots
│   ├── templates/
│   │   ├── python/jev_client.py        # TypeSafe SDK; TypeSafe direct or OpenRouter systemone
│   │   ├── python/openrouter_decisions.py  # raw Decisions API with request validation
│   │   ├── typescript/ai-sdk-evaluate.ts   # AI SDK experimental_evaluate + policy
│   │   ├── typescript/ai-sdk-evaluate.test.ts  # offline vitest with the mock model
│   │   ├── typescript/openrouter-decisions.ts  # @openrouter/sdk tool-call gate
│   │   └── claude-code-gate/           # fail-closed PreToolUse hook, settings snippet, unit tests
│   └── scripts/jev_probe.py            # smoke-test any access path (stdlib only)
├── evals/                              # claude plugin eval cases
└── docs/research/                      # archived source research (superseded by references/)
```

## Install

### Claude Code (plugin marketplace)

```bash
claude plugin marketplace add KHAEntertainment/kha-marketplace
claude plugin install jev@kha-marketplace
```

Or inside a session:

```
/plugin marketplace add KHAEntertainment/kha-marketplace
/plugin install jev@kha-marketplace
```

The skill loads automatically when a task calls for it. You can also invoke it explicitly
with `/jev:jev-integration`.

Recommended companion:

```bash
claude plugin marketplace add typesafe-ai/skills
claude plugin install typesafe@typesafe-ai
```

### Any agent (`npx skills`)

```bash
npx skills add KHAEntertainment/jev-skill                  # interactive: pick agents
npx skills add KHAEntertainment/jev-skill -a codex -a cursor
npx skills add KHAEntertainment/jev-skill -g               # global install
npx skills add typesafe-ai/skills --skill typesafe-ai      # recommended companion
```

The CLI discovers `skills/jev-integration/SKILL.md` and links it into each selected agent's
skills directory (for example `.claude/skills/`, `.agents/skills/`, `~/.codex/skills/`).
Update with `npx skills update`.

### Manual

Copy `skills/jev-integration/` into your agent's skills directory, for example
`~/.claude/skills/jev-integration/`.

## Using it

Ask naturally; there's no special syntax. Prompts that should trigger it:

- "Can we replace the LLM call that classifies tickets with Jev? We use OpenRouter."
- "Add a Claude Code hook that uses Jev to stop dangerous Bash commands."
- "Which is better for Jev in our Next.js app: the AI SDK or the TypeSafe SDK?"
- "Build a model router that sends easy requests to a cheap model, using Jev."
- "My OpenRouter decisions request returns 400 but works on api.typesafe.ai."
- "Should we use Jev for this?" (the skill will also tell you when the answer is no)

When the skill is active, the agent will:

1. Run the fit test (Jev vs LLM vs plain code) and say plainly when Jev is the wrong tool.
2. Pick an access path, with OpenRouter and TypeSafe direct as the defaults, and flag the
   path-specific gotchas: different model ids, where confidence lives, and the stricter
   criteria rules on OpenRouter Decisions.
3. Pick the integration layer the project already uses.
4. Choose a harness pattern with an explicit fail policy.
5. Deliver one reviewable module: questions, named threshold constants, a policy function,
   a timeout-bounded client, offline tests, and a smoke check. It will also list the
   thresholds that still need calibrating on your data.

### Smoke-test your credentials

```bash
python3 skills/jev-integration/scripts/jev_probe.py                       # TYPESAFE_API_KEY
python3 skills/jev-integration/scripts/jev_probe.py --provider openrouter  # OPENROUTER_API_KEY
python3 skills/jev-integration/scripts/jev_probe.py --provider openrouter-decisions
python3 skills/jev-integration/scripts/jev_probe.py --dry-run             # no network
```

It prints the resolved model id, request id, latency, usage/cost, and answers. Each probe
costs a fraction of a cent.

## Key facts the skill gets right (and common sources get wrong)

As of 2026-09-22:

- **OpenRouter serves Jev on two endpoints.** `/api/v1/systemone` speaks TypeSafe's wire
  format, so TypeSafe's SDKs work with `base_url=https://openrouter.ai/api`.
  `/api/alpha/decisions` adds `usage.cost` and tracing. Neither is reachable through
  `/v1/chat/completions`.
- **No primary source shows Jev on Google Vertex AI, AWS Bedrock, Azure AI Foundry, Together,
  or Fireworks.** The verified hosts are TypeSafe, OpenRouter, Vercel AI Gateway, Cloudflare
  Workers AI, and the LiteLLM pass-through.
- **The Vercel direct provider is `@ai-sdk/typesafe-ai`**, and its env var is
  `TYPESAFE_AI_API_KEY`.
- **A Claude Code PreToolUse command hook that times out does not block the tool call.**
  Jev gates must enforce their own deadline.
- **Several popular community Jev gates fail open by default.**
- **Accuracy is not free.** Third-party reports cite a ~6-point gap to the best frontier LLM
  on TypeSafe's workflow evals, but we could not find that figure on TypeSafe's primary
  pages, so it is unverified. Either way, Jev is a fast, cheap, calibrated decider to
  validate on your data, not a free accuracy upgrade.
- **"No key" returns 403, not the documented 401** (checked live; a bad key returns 401).

## Keeping it current

Every reference file carries a verification date, and `SKILL.md` records it in
`metadata.verified`. To refresh:

1. Re-read the live pages listed at the top of each reference file. Start from
   `https://docs.typesafe.ai/llms.txt` and the OpenRouter and Vercel Jev guides.
2. Update the facts, the date, and `CHANGELOG.md`.
3. Re-run the template checks and evals (below).

Areas most likely to drift: the OpenRouter Decisions endpoint (alpha), AI SDK
`experimental_evaluate` (experimental), LangChain middleware (experimental), BAML (nightly),
model versions and aliases, and rate limits ("adjusting dynamically").

## Development

```bash
# manifest + layout
claude plugin validate . --strict

# load for one session
claude --plugin-dir .

# behavior evals vs a no-plugin baseline (uses your Claude credentials)
claude plugin eval .

# npx-skills discovery
npx skills add . --list

# templates
python3 -m py_compile skills/jev-integration/templates/python/*.py \
  skills/jev-integration/templates/claude-code-gate/jev_gate.py skills/jev-integration/scripts/jev_probe.py
# TypeScript: copy templates/typescript into a project with
#   ai @ai-sdk/typesafe-ai @openrouter/sdk vitest typescript
# then run: npx tsc --noEmit && npx vitest run
```

The Claude Code gate has offline unit tests (deterministic rules, redaction, never-allow,
fail-closed):

```bash
cd skills/jev-integration/templates/claude-code-gate && python3 -m unittest test_jev_gate.py
```

## Disclaimer

This project is not affiliated with TypeSafe AI, OpenRouter, Vercel, or Cloudflare. The
performance and cost figures it quotes are the vendors' own unless marked otherwise.
Community projects listed in the references are unaudited; vet them before installing.

## License

MIT. See [LICENSE](LICENSE).
