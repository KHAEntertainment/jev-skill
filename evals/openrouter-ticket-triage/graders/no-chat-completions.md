---
type: regex
pattern: 'https?://[^\s"''`]*chat/completions|\.chat\.completions\.create|generateText\('
match: not_contains
---

Fails only when the reply's code actually calls a chat-completions API (full URL, OpenAI-style
client call, or AI SDK generateText). Prose warnings such as "Jev doesn't work through
`/v1/chat/completions`" must not trip it.
