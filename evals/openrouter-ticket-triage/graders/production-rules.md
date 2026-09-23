---
type: llm
weight: 2
---

PASS if the reply's code does all of the following:
1. Calls Jev through an OpenRouter decision endpoint (`/api/v1/systemone` with a TypeSafe-compatible client, or `/api/alpha/decisions` / `@openrouter/sdk` `alpha.decisions` / `openrouter.decisionModel`), not a chat-completions API.
2. Uses a pinned model id such as `typesafe/jev-1.13`, or explicitly explains why it uses the `~typesafe/jev-latest` alias and recommends pinning after calibration.
3. Uses the choice answer's confidence (or probabilities) to decide between automatic routing and human review, rather than trusting the argmax unconditionally.
4. Handles errors or timeouts by falling back to a safe outcome, such as a human queue, instead of crashing or dropping the ticket.

FAIL if any of the four is missing, or if the code invents request/response fields that contradict the OpenRouter Decisions or TypeSafe systemone format (for example a `messages` array or a `temperature` parameter).
