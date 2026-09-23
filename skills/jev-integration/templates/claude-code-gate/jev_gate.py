#!/usr/bin/env python3
"""Fail-closed Jev risk gate for Claude Code PreToolUse hooks (stdlib only).

Flow: deterministic deny rules -> deterministic pass rules -> Jev on the gray zone -> policy.
Outputs a PreToolUse decision of "deny" or "ask", or nothing (pass-through to Claude Code's
normal permission flow). It never emits "allow": Jev can make things stricter, never
silently grant.

Why it enforces its own deadline: a PreToolUse command hook that hits its `timeout` is
discarded and the tool call proceeds. So this script bounds the Jev call (JEV_GATE_TIMEOUT_S)
well under the hook timeout and prints a fail-closed decision itself.

Env:
  JEV_GATE_PROVIDER   typesafe (default) | openrouter
  TYPESAFE_API_KEY / OPENROUTER_API_KEY
  JEV_GATE_MODEL      default jev-1.13.0 (typesafe) / typesafe/jev-1.13 (openrouter)
  JEV_GATE_TIMEOUT_S  default 4 (urllib applies it per socket operation, not in total;
                      keep the hook `timeout` at least ~2.5x this value)
  JEV_GATE_ON_ERROR   ask (default) | deny     -- use deny for unattended runs
  JEV_GATE_BASE_URL   override endpoint base (testing)
  JEV_GATE_MOCK       JSON answers object; skips the network (offline tests)
Thresholds below are placeholders until calibrated on your own logged decisions.
Verified against the Claude Code hooks reference on 2026-09-22.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

PROVIDERS = {
    "typesafe": ("https://api.typesafe.ai", "TYPESAFE_API_KEY", "jev-1.13.0"),
    "openrouter": ("https://openrouter.ai/api", "OPENROUTER_API_KEY", "typesafe/jev-1.13"),
}

# --- Deterministic rules (exact, free, run first) ----------------------------------------
# Best-effort floor, not a sandbox: anything these miss still goes to Jev + policy below.
# Claude Code passes the raw command string (before shell expansion), so `$HOME` and `~`
# appear literally. Matched case-insensitively.
_END = r"(?=[\s\"';)|&]|$)"  # end of a path token, including inside quotes or `bash -c "..."`
DENY_PATTERNS = [
    # recursive+force delete of root, home, or everything: -rf, -Rf, -fr, --recursive --force
    r"\brm\s+(-[a-z]*r[a-z]*\s+|--recursive\s+|-[a-z]*f[a-z]*\s+|--force\s+|--no-preserve-root\s+)+"
    r"(/|/\*|~/?|~/\*|\$home/?|\$\{home\}/?|\.\.?/?)" + _END,
    r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b",           # pipe remote script to a shell
    r"\b(curl|wget)\b.*(&&|;|\|\|)\s*(sudo\s+)?(ba|z|da)?sh\s",      # download, then execute
    r"\b(ba|z|da)?sh\s+<\(\s*(curl|wget)\b",                          # bash <(curl ...)
    r"\bgit\s+push\b.*(--force(?!-with-lease)|\s-f\b)",                # blind force push
    r"(^|[\s\"'=])(\S*/)?\.(ssh|gnupg|aws)/",                            # key material dirs
    r"\bmkfs\.|\bdd\s+if=.*\bof=/dev/",                                # disk destruction
]
# Routine read-only commands skip Jev and go to Claude Code's normal permission flow.
# Refused for any shell metacharacter (chaining, redirection, substitution) or sensitive path.
PASS_PATTERNS = [
    r"^\s*(ls|pwd|wc|echo|which|whoami|date)\b[^;&|<>`$()]*$",
    r"^\s*git\s+(status|log|diff|show|branch)\b[^;&|<>`$()]*$",
]
SENSITIVE_PATH = re.compile(
    r"(\.ssh|\.gnupg|\.aws|\.config/gcloud|\.kube|\.docker/config|\.netrc|\.npmrc|\.pypirc|"
    r"\.env\b|credentials|secret|id_rsa|id_ed25519|/etc/(shadow|passwd|sudoers))",
    re.IGNORECASE,
)

# --- Jev questions (refine wording with the official typesafe-ai skill) -------------------
QUESTIONS = {
    "category": {
        "type": "choice",
        "instructions": "What kind of effect does `tool_input` have if executed?",
        "criteria": {
            "read_only": "Only reads files, state, or metadata",
            "reversible_write": "Changes local state in a way that is easy to undo",
            "destructive": "Deletes data, rewrites history, or is otherwise hard to undo",
            "exfiltration": "Sends local files, data, or secrets to an external destination",
            "unclear": "The effect cannot be determined from the input",
        },
    },
    "irreversible": {
        "type": "noul",
        "instructions": "Executing `tool_input` would delete data, rewrite git history, force-push, "
        "drop or migrate databases, or change production systems",
        "criteria": {"true": "Hard or impossible to undo", "false": "Easily undone or read-only"},
    },
    "user_requested": {
        "type": "noul",
        "instructions": "`recent_user_request` explicitly asks for the action `tool_input` performs",
        "criteria": {"true": "The user clearly asked for this action", "false": "Not clearly requested"},
    },
}

# --- Policy thresholds (TODO(calibrate)) -------------------------------------------------
IRREVERSIBLE_DENY = 0.8          # deny when also not clearly user-requested
USER_REQUESTED_OVERRIDE = 0.85
IRREVERSIBLE_ASK = 0.3
CATEGORY_MIN_CONFIDENCE = 0.6

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S), "<redacted-private-key>"),
    (re.compile(r"\b(sk|pk|rk)_(live|test)_[A-Za-z0-9]{16,}"), "<redacted-stripe-key>"),
    (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{16,}"), "<redacted-key>"),
    (re.compile(r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}"), "<redacted-gh-token>"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "<redacted-aws-key>"),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), "<redacted-slack-token>"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "<redacted-jwt>"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"), r"\1<redacted>"),
    (re.compile(r"([a-z][a-z0-9+.-]*://[^/\s:@]+:)[^@\s/]+@"), r"\1<redacted>@"),  # scheme://user:pass@host
    (re.compile(r"(?i)\b([A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD)[A-Z0-9_]*)=\S+"), r"\1=<redacted>"),
]


def redact(text: str) -> str:
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def emit(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": f"jev-gate: {reason}",
    }}))


def recent_user_request(transcript_path: str | None, limit: int = 1500) -> str:
    """Best-effort: last user text from the session transcript (JSONL). Empty on any problem."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            lines = fh.readlines()[-200:]
        for line in reversed(lines):
            entry = json.loads(line)
            if entry.get("type") != "user":
                continue
            content = entry.get("message", {}).get("content")
            if isinstance(content, str):
                return content[-limit:]
            if isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                if texts:
                    return " ".join(texts)[-limit:]
    except (OSError, ValueError, AttributeError):
        pass
    return ""


def ask_jev(state: dict) -> dict:
    mock = os.environ.get("JEV_GATE_MOCK")
    if mock:
        return json.loads(mock)
    base, key_env, default_model = PROVIDERS[os.environ.get("JEV_GATE_PROVIDER", "typesafe")]
    body = json.dumps({
        "state": state,
        "model": os.environ.get("JEV_GATE_MODEL", default_model),
        "questions": QUESTIONS,
    }).encode()
    req = urllib.request.Request(
        os.environ.get("JEV_GATE_BASE_URL", base).rstrip("/") + "/v1/systemone",
        data=body,
        headers={"Authorization": f"Bearer {os.environ[key_env]}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=float(os.environ.get("JEV_GATE_TIMEOUT_S", "4"))) as resp:
        return json.loads(resp.read())["answers"]


def policy(a: dict) -> tuple[str | None, str]:
    """answers -> ("deny" | "ask" | None, reason). None = pass-through."""
    cat, irr, req = a["category"], a["irreversible"]["noul"], a["user_requested"]["noul"]
    if cat["choice"] == "exfiltration":
        return "deny", "looks like data exfiltration"
    if irr >= IRREVERSIBLE_DENY and req < USER_REQUESTED_OVERRIDE:
        return "deny", f"irreversible (p={irr:.2f}) and not clearly requested (p={req:.2f})"
    if irr >= IRREVERSIBLE_ASK or cat["choice"] in ("destructive", "unclear"):
        return "ask", f"category={cat['choice']} irreversible p={irr:.2f}"
    if cat.get("confidence", 0.0) < CATEGORY_MIN_CONFIDENCE:
        return "ask", f"low confidence ({cat.get('confidence', 0.0):.2f}) on category={cat['choice']}"
    return None, f"category={cat['choice']} irreversible p={irr:.2f}"


def main() -> int:
    fail = os.environ.get("JEV_GATE_ON_ERROR", "ask")
    try:
        event = json.load(sys.stdin)
    except ValueError:
        emit(fail, "could not parse hook input")
        return 0
    tool_input = event.get("tool_input", {})
    command = tool_input.get("command", "") if event.get("tool_name") == "Bash" else json.dumps(tool_input)

    if any(re.search(p, command, re.IGNORECASE) for p in DENY_PATTERNS):
        emit("deny", "matched deterministic deny rule")
        return 0
    if (event.get("tool_name") == "Bash" and not SENSITIVE_PATH.search(command)
            and any(re.search(p, command) for p in PASS_PATTERNS)):
        return 0  # routine read-only command: normal permission flow

    state = {
        "tool_name": event.get("tool_name"),
        "tool_input": redact(command)[:8000],  # redact the full input first, then bound size
        "cwd": event.get("cwd"),
        "recent_user_request": redact(recent_user_request(event.get("transcript_path"))),
    }
    try:
        answers = ask_jev(state)
        decision, reason = policy(answers)
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, TypeError) as err:
        emit(fail, f"Jev unavailable ({type(err).__name__}); failing closed")
        return 0
    print(f"jev-gate: {decision or 'pass'} {reason}", file=sys.stderr)
    if decision:
        emit(decision, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
