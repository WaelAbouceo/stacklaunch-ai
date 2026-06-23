"""Deterministic PII / PHI detection and redaction.

A pure, stateless redaction layer used as an enforced guardrail (not a prompt
note). It works two ways:

1. **Pattern redaction** — regexes for structured identifiers (email, phone,
   payment card, IBAN, US SSN, Egyptian national ID). Order matters: the most
   specific/greedy patterns run before the broad phone matcher.
2. **Key-aware redaction** — when scrubbing structured objects, values under known
   PII field names (name, email, phone, ...) are masked regardless of their shape,
   catching things a regex would miss (e.g. a person's name).

Deterministic by design: the same input always yields the same redacted output and
the same finding counts, so it is safe to assert on in tests and audit logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Field names whose values are always PII when scrubbing structured objects.
PII_KEYS = {
    "name", "fullname", "full_name", "firstname", "first_name", "lastname",
    "last_name", "email", "emailaddress", "email_address", "phone", "phonenumber",
    "phone_number", "mobile", "msisdn", "ssn", "nationalid", "national_id",
    "passport", "iban", "cardnumber", "card_number", "address",
}

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Payment card: 13-16 digits, optionally grouped in 4s by space or dash.
_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
# Egyptian national ID: exactly 14 consecutive digits.
_NATIONAL_ID = re.compile(r"\b\d{14}\b")
# Broad phone candidate; validated by digit count in the callback below.
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d().\-\s]{7,}\d(?![\w.])")

_TOKENS = {
    "email": "[REDACTED_EMAIL]",
    "iban": "[REDACTED_IBAN]",
    "ssn": "[REDACTED_SSN]",
    "card": "[REDACTED_CARD]",
    "national_id": "[REDACTED_NATIONAL_ID]",
    "phone": "[REDACTED_PHONE]",
    "value": "[REDACTED]",
}


@dataclass
class Redaction:
    text: str
    count: int


def _sub_count(pattern: re.Pattern, token: str, text: str) -> tuple[str, int]:
    new, n = pattern.subn(token, text)
    return new, n


def _redact_phones(text: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        digits = re.sub(r"\D", "", m.group(0))
        # Real phone numbers are 9-15 digits; shorter spans are IDs/amounts.
        if 9 <= len(digits) <= 15:
            count += 1
            return _TOKENS["phone"]
        return m.group(0)

    return _PHONE.sub(repl, text), count


def redact_text(text: str) -> Redaction:
    """Redact structured PII from free text. Returns the clean text + finding count."""
    if not text:
        return Redaction(text=text or "", count=0)
    total = 0
    text, n = _sub_count(_EMAIL, _TOKENS["email"], text);          total += n
    text, n = _sub_count(_IBAN, _TOKENS["iban"], text);            total += n
    text, n = _sub_count(_SSN, _TOKENS["ssn"], text);              total += n
    # National ID (exactly 14 contiguous digits) before the broader card matcher,
    # which would otherwise swallow it as a 13-16 digit span.
    text, n = _sub_count(_NATIONAL_ID, _TOKENS["national_id"], text); total += n
    text, n = _sub_count(_CARD, _TOKENS["card"], text);            total += n
    text, n = _redact_phones(text);                                total += n
    return Redaction(text=text, count=total)


def redact_obj(obj: object) -> Redaction:
    """Recursively redact strings in a dict/list/scalar structure.

    Values under PII_KEYS are masked wholesale; all other strings go through
    pattern redaction. Returns a new structure plus the total finding count.
    """
    count = 0

    def walk(node: object, key_is_pii: bool = False) -> object:
        nonlocal count
        if isinstance(node, str):
            if key_is_pii and node.strip():
                count += 1
                return _TOKENS["value"]
            r = redact_text(node)
            count += r.count
            return r.text
        if isinstance(node, dict):
            return {
                k: walk(v, key_is_pii=str(k).lower() in PII_KEYS)
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, tuple):
            return tuple(walk(v) for v in node)
        return node

    clean = walk(obj)
    return Redaction(text=clean, count=count)  # type: ignore[arg-type]


def find_pii(text: str) -> bool:
    """Cheap predicate: does this text contain any detectable PII?"""
    return redact_text(text).count > 0
