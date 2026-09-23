---
description: Harness case. Should produce a PreToolUse gate that fails closed and bounds its own latency.
tags: [trigger, harness, code]
max_turns: 12
allowed_tools: [Read, Glob, Grep, Skill]
---

I want Claude Code to check every Bash command with Jev before it runs and stop the dangerous ones. Give me the hook script and the settings.json entry in your reply (don't write files). Keep it simple.
