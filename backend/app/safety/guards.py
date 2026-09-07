import re

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior) instructions",
    r"disregard (the )?(system|above)",
    r"you are now",
    r"reveal (your )?(system )?prompt",
]

def sanitize_retrieved(text: str) -> str:
    """Defuse injection attempts hidden in retrieved filing text. We neutralize,
    not delete, so the real content is preserved for the model to read."""
    cleaned = text
    for pat in INJECTION_PATTERNS:
        cleaned = re.sub(pat, "[redacted-instruction]", cleaned, flags=re.I)
    return cleaned

def input_ok(query: str) -> tuple[bool, str]:
    if len(query) > 2000:
        return False, "Query too long (max 2000 chars)."
    if any(re.search(pat, query, flags=re.I) for pat in INJECTION_PATTERNS):
        return False, "Query looks like a prompt injection attempt."
    return True, ""

ADVICE_PATTERNS = [r"should i (buy|sell)", r"is .* a good (buy|investment)",
                   r"will .* (go up|crash|moon)"]

def output_ok(answer: str) -> tuple[bool, str]:
    """Structural check: an answer with zero citations is ungrounded -> block."""
    if "[cite:]" not in answer:
        return False, "Answer was not grounded in sources."
    return True, ""

def advice_disclaimer_needed(query: str) -> bool:
    return any(re.search(pat, query, flags=re.I) for pat in ADVICE_PATTERNS)
