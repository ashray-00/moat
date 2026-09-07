import re

def extract_numbers(text: str) -> list[float]:
    """Parse $383.29B / 383,285 million / 383285000000 into absolute magnitudes.
    Pattern REQUIRES a leading digit (the fix for the comma-matching bug)."""
    out = []
    for m in re.finditer(r'\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(billion|b|million|m|trillion|t)?\b',
                         text, re.I):
        num = float(m.group(1).replace(",", ""))
        mult = {"b": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6,
                "t": 1e12, "trillion": 1e12}.get((m.group(2) or "").lower(), 1)
        out.append(num * mult)
    return out

def numerical_match(expected: float, answer: str, rel_tol: float = 0.01) -> bool:
    """True if the answer contains a number within rel_tol of expected."""
    for n in extract_numbers(answer):
        if expected == 0 and n == 0:
            return True
        if expected and abs(n - expected) / abs(expected) <= rel_tol:
            return True
    return False

def citation_grounded(answer: str, retrieved_ids: set[str]) -> tuple[bool, set, set]:
    """Every [cite:ID] must reference a chunk we actually retrieved.
    An answer with NO citations fails the gate (ungrounded)."""
    cited = set(re.findall(r'\[cite:([^\]]+)\]', answer))
    if not cited:
        return False, cited, set()
    hallucinated = cited - retrieved_ids
    return len(hallucinated) == 0, cited, hallucinated