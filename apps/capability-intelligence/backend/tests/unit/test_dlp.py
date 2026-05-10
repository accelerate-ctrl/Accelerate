from app.services.dlp_service import redact


def test_redacts_ssn_email_phone():
    text = "Contact jane@x.com or call 415-555-0123. SSN 123-45-6789."
    r = redact(text)
    assert "[REDACTED:EMAIL]" in r.text
    assert "[REDACTED:PHONE_US]" in r.text
    assert "[REDACTED:SSN]" in r.text
    assert r.redaction_summary["EMAIL"] == 1
    assert r.redaction_summary["SSN"] == 1
    assert r.redaction_method == "regex"


def test_credit_card_only_redacts_luhn_valid():
    valid = "4111 1111 1111 1111"  # Luhn-valid Visa test number
    invalid = "1234 5678 9012 3456"  # not Luhn-valid
    r1 = redact(valid)
    r2 = redact(invalid)
    assert "[REDACTED:CREDIT_CARD]" in r1.text
    assert "[REDACTED:CREDIT_CARD]" not in r2.text


def test_no_pii_no_change():
    text = "This is a normal sentence."
    r = redact(text)
    assert r.text == text
    assert r.redaction_summary == {}
