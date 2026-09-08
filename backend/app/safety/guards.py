"""Input/output safety for Ask, Agent, memory, and retrieved filing text.

Attack surfaces:
- User queries (Ask / Agent) → ``input_ok`` (reject)
- Filing excerpts in prompts/tools → ``sanitize_retrieved`` (neutralize)
- Session memory / prior turns re-fed to the model → ``sanitize_memory_*``
- Agent drafts that look like investment advice → ``is_advice_like`` (HITL)
- Ask queries that solicit advice → ``advice_disclaimer_needed``
"""

from __future__ import annotations

import re

MAX_QUERY_LEN = 2000

# Reject on user-facing input. Keep these specific — false positives block research.
INPUT_INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior|above) (instructions|rules|guidelines)",
    r"disregard (the )?(system|above|previous|prior)( (instructions|rules|prompt|message))?",
    r"forget (all )?(your |the )?(previous |prior )?(instructions|rules|guidelines)",
    r"override (the )?(system|safety|guardrails|rules)",
    r"do not follow (your |the )?(rules|instructions|guidelines|system)",
    r"reveal (your )?(system )?prompt",
    r"show (me )?(your )?(system |hidden )?prompt",
    r"\bjailbreak\b",
    r"(enable|enter|activate) (developer|dev|dan) mode",
    r"you are now (a |an )?(dan|jailbroken|unrestricted)\b",
    r"pretend (you |that you )?(are|have) no (restrictions|rules|limits)",
    r"new (system )?instructions?\s*:",
    r"system prompt\s*:",
]

# Also neutralized inside retrieved filings / memory (includes looser jailbreak phrasing).
RETRIEVED_INJECTION_PATTERNS = INPUT_INJECTION_PATTERNS + [
    r"you are now",
    r"ignore (all )?(previous|prior) instructions",
]

# Chat/role markup that should never appear as "instructions" inside untrusted text.
DELIMITER_PATTERNS = [
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"<\|system\|>",
    r"<<\s*SYS\s*>>",
    r"\[/?INST\]",
    r"</?system>",
    r"</?assistant>",
    r"(?m)^\s*system\s*:\s*",
]

# Output-side phrases → agent HITL. Avoid bare "this is a buy" (matches "buyback").
ADVICE_OUTPUT_PHRASES = (
    "you should buy",
    "you should sell",
    "you should hold",
    "i recommend buying",
    "i recommend selling",
    "i recommend hold",
    "i recommend you buy",
    "i recommend you sell",
    "recommend you buy",
    "recommend you sell",
)

ADVICE_QUERY_PATTERNS = [
    r"should i (buy|sell|hold)",
    r"is .* a good (buy|investment|stock)",
    r"will .* (go up|crash|moon|rally)",
    r"(buy|sell) (recommendation|advice)",
]

# Back-compat for older imports/tests
INJECTION_PATTERNS = INPUT_INJECTION_PATTERNS
ADVICE_PATTERNS = ADVICE_QUERY_PATTERNS


def looks_like_injection(text: str | None) -> bool:
    content = text or ""
    if not content.strip():
        return False
    return any(re.search(pat, content, flags=re.I) for pat in INPUT_INJECTION_PATTERNS)


def sanitize_retrieved(text: str) -> str:
    """Neutralize injection / role-spoof attempts in untrusted text (do not delete)."""
    cleaned = text or ""
    for pat in RETRIEVED_INJECTION_PATTERNS:
        cleaned = re.sub(pat, "[redacted-instruction]", cleaned, flags=re.I)
    for pat in DELIMITER_PATTERNS:
        cleaned = re.sub(pat, "[redacted-delimiter]", cleaned, flags=re.I)
    return cleaned


def sanitize_memory_text(text: str | None) -> str:
    """Sanitize summary or turn content before feeding it back to the model."""
    return sanitize_retrieved(text or "")


def sanitize_memory_turns(turns: list[dict] | None) -> list[dict]:
    """Sanitize user/assistant turns; drop malformed entries."""
    out: list[dict] = []
    for turn in turns or []:
        if not isinstance(turn, dict):
            continue
        role, content = turn.get("role"), turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content:
            out.append({"role": role, "content": sanitize_memory_text(content)})
    return out


def sanitize_chat_messages(messages: list[dict] | None) -> list[dict]:
    """Sanitize string content on chat/tool transcripts without dropping tool calls."""
    out: list[dict] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str) and content:
            out.append({**m, "content": sanitize_memory_text(content)})
        else:
            out.append(m)
    return out


def input_ok(query: str) -> tuple[bool, str]:
    if len(query) > MAX_QUERY_LEN:
        return False, f"Query too long (max {MAX_QUERY_LEN} chars)."
    if looks_like_injection(query):
        return False, "Query looks like a prompt injection attempt."
    return True, ""


def output_ok(answer: str) -> tuple[bool, str]:
    """Structural check: an answer with zero citations is ungrounded -> flag."""
    if "[cite:" not in answer:
        return False, "Answer was not grounded in sources."
    return True, ""


def is_advice_like(text: str | None) -> bool:
    """True when model output reads like buy/sell/hold advice (agent HITL)."""
    content = (text or "").lower()
    return any(p in content for p in ADVICE_OUTPUT_PHRASES)


def advice_disclaimer_needed(query: str) -> bool:
    return any(re.search(pat, query, flags=re.I) for pat in ADVICE_QUERY_PATTERNS)
