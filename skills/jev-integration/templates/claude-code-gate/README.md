# Claude Code Jev gate (template)

A fail-closed `PreToolUse` hook that screens Bash commands with Jev. Standard library only.

## What it does

1. **Deterministic deny rules.** Recursive force-deletes of `/`, `~`, or `$HOME` (in any flag
   spelling), `curl | sh` and download-then-execute, blind force-push, key-material
   directories, and disk writes are denied without a model call. Matching is
   case-insensitive. These rules are a best-effort floor, not a sandbox: anything they miss
   still goes to Jev.
2. **Deterministic pass rules.** A few routine commands (`ls`, `git status`, `echo`, …) skip
   Jev and go through Claude Code's normal permission flow. Only a bare command qualifies:
   no chaining, redirection, or command substitution, and no sensitive path (`.env`,
   `credentials`, `/etc/shadow`, …). File reads such as `cat` always go to Jev.
3. **Jev for everything else.** One request with three questions: effect category,
   irreversible, and whether the user asked for it. The command is redacted and the last
   user message is attached as context.
4. **Policy.** Returns `deny`, `ask`, or nothing (pass-through). It **never returns
   `allow`**, so it can only make Claude Code stricter.
5. **Fails closed.** On timeout, network error, missing key, or unexpected response it
   returns `ask` (or `deny` with `JEV_GATE_ON_ERROR=deny` for unattended runs).

A command hook that hits its own `timeout` is discarded, and **the tool call then goes
ahead**. So the script caps the Jev call at `JEV_GATE_TIMEOUT_S` (4 s), well under the hook's
`timeout` (10 s), and prints its fail-closed decision itself.

## Install (project)

```bash
mkdir -p .claude/hooks && cp jev_gate.py .claude/hooks/
# merge settings.snippet.json into .claude/settings.json
export TYPESAFE_API_KEY=...        # or JEV_GATE_PROVIDER=openrouter + OPENROUTER_API_KEY
```

To gate file edits or MCP tools as well, widen the `matcher` (for example
`Bash|Write|Edit|mcp__.*`). Non-Bash tool inputs are sent to Jev as JSON.

## Test offline before wiring it in

```bash
python3 -m unittest test_jev_gate.py   # 8 tests: rules, redaction, never-allow, fail-closed
```

Or try individual payloads:

```bash
# deterministic deny
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf ~"}}' | python3 jev_gate.py
# deterministic pass (no output)
echo '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | python3 jev_gate.py
# policy with mocked answers -> ask
echo '{"tool_name":"Bash","tool_input":{"command":"npm run db:reset"}}' | \
  JEV_GATE_MOCK='{"category":{"choice":"destructive","confidence":0.9},"irreversible":{"noul":0.6},"user_requested":{"noul":0.2}}' \
  python3 jev_gate.py
# Jev unreachable -> fail closed (ask)
echo '{"tool_name":"Bash","tool_input":{"command":"make deploy"}}' | \
  JEV_GATE_BASE_URL=http://127.0.0.1:9 TYPESAFE_API_KEY=x python3 jev_gate.py
```

## Before trusting it

- Thresholds are placeholders. Log decisions (stderr carries a one-line summary), label a
  sample, and calibrate them (`references/calibration-and-ops.md`).
- Deny and ask rules in Claude Code permissions still apply after the hook. Keep hard
  rules there, since hooks are a second layer.
- Precedence across hooks is `deny` > `defer` > `ask` > `allow`, so this gate combines
  safely with other hooks.
