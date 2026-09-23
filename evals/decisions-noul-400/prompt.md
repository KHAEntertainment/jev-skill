---
description: Debug case. OpenRouter Decisions requires both true and false when noul criteria is present.
tags: [trigger, debug]
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill]
---

This works against api.typesafe.ai but OpenRouter's /api/alpha/decisions rejects it with a 400. Why?

```json
{"model":"typesafe/jev-1.13","state":"Refund me now or I'm calling my lawyer",
 "questions":{"legal_threat":{"type":"noul","instructions":"The customer threatens legal action",
   "criteria":{"true":"Mentions lawyers, lawsuits, or legal action"}}}}
```
