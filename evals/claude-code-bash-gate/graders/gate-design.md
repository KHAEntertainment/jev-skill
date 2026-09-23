---
type: llm
weight: 2
---

PASS if the reply provides a Claude Code PreToolUse hook (matcher on Bash) whose script:
1. Outputs the decision via `hookSpecificOutput.permissionDecision` (values such as `deny` / `ask`), or exits 2 to block.
2. Fails closed: on Jev errors, timeouts, or a missing API key it denies or asks for confirmation rather than letting the command run silently.
3. Bounds its own Jev call with a client-side timeout shorter than the hook's `timeout`, OR explicitly explains that a timed-out hook does not block the tool call.
4. Does not auto-approve commands purely because Jev said they look safe without a calibrated threshold or deterministic rule (returning no decision and deferring to the normal permission flow is fine).

FAIL if the gate fails open on errors without saying so, if it uses a chat-completions API for Jev, or if the settings.json structure is not a valid Claude Code hooks entry.
