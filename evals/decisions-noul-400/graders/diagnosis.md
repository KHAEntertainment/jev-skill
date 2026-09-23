---
type: llm
---

PASS if the reply identifies that OpenRouter's Decisions API requires a noul question's `criteria` to define BOTH `true` and `false` when criteria is present (unlike the native TypeSafe API where each side is optional), and fixes it by adding a `false` description or removing `criteria`.

FAIL if the reply blames something else (auth, model id, state format) as the primary cause.
