"""Tests for deterministic PII redaction (pii.py)."""

from governance import pii


def test_redacts_email():
    r = pii.redact_text("Contact me at john.doe@example.com please")
    assert "john.doe@example.com" not in r.text
    assert "[REDACTED_EMAIL]" in r.text
    assert r.count == 1


def test_redacts_egyptian_phone():
    r = pii.redact_text("Call +20 100 1234567 or 01234567890")
    assert "[REDACTED_PHONE]" in r.text
    assert "+20" not in r.text
    assert r.count == 2


def test_redacts_payment_card_and_national_id():
    r = pii.redact_text("Card 4111 1111 1111 1111, ID 29801011234567")
    assert "4111" not in r.text
    assert "[REDACTED_CARD]" in r.text
    assert "[REDACTED_NATIONAL_ID]" in r.text


def test_does_not_redact_short_ids_or_money():
    # CUST-001 and an EGP amount must survive — they are not PII.
    r = pii.redact_text("Customer CUST-001 has lifetime value EGP 25,474")
    assert r.count == 0
    assert "CUST-001" in r.text
    assert "25,474" in r.text


def test_is_deterministic():
    text = "email a@b.com phone +201001234567"
    assert pii.redact_text(text).text == pii.redact_text(text).text


def test_key_aware_redaction_masks_names():
    record = {"customerId": "CUST-007", "name": "Jane Smith",
              "email": "jane@x.com", "segment": "Premium"}
    r = pii.redact_obj(record)
    assert r.text["customerId"] == "CUST-007"
    assert r.text["segment"] == "Premium"
    assert r.text["name"] == "[REDACTED]"
    assert r.text["email"] == "[REDACTED]"
    assert r.count == 2


def test_redact_obj_recurses_into_nested_text():
    obj = {"results": [{"snippet": "reach us at sales@acme.com"}]}
    r = pii.redact_obj(obj)
    assert "[REDACTED_EMAIL]" in r.text["results"][0]["snippet"]
    assert r.count == 1
