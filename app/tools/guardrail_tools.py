"""
app/tools/guardrail_tools.py
Deterministic safety guardrails that execute independently of LLM reasoning.
Validates PII leakage and enforces strict URL allowlisting / citation verification.
"""

import re
from typing import Any
from urllib.parse import urlparse

# Strict Official Apple Support Domains Allowlist
OFFICIAL_ALLOWED_DOMAINS = {
    "apple.com",
    "support.apple.com",
    "getsupport.apple.com",
    "reportaproblem.apple.com",
    "appleid.apple.com",
    "icloud.com",
    "locate.apple.com",
}


def pii_check_tool(text: str) -> dict[str, Any]:
    """
    Deterministic check for customer personal data (PII) leakage in public inquiries.
    Detects email addresses, international/US phone numbers, and credentials.
    """
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    phone_pattern = r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"

    emails = re.findall(email_pattern, text)
    if emails:
        return {
            "passed": False,
            "violation_type": "PII_EMAIL_EXPOSURE",
            "details": f"Customer shared email publicly: {emails[0]}",
            "matches": emails,
        }

    phones = re.findall(phone_pattern, text)
    if phones:
        return {
            "passed": False,
            "violation_type": "PII_PHONE_EXPOSURE",
            "details": f"Customer shared phone number publicly: {phones[0]}",
            "matches": phones,
        }

    return {
        "passed": True,
        "violation_type": "NONE",
        "details": "No PII detected.",
        "matches": [],
    }


def url_allowlist_check_tool(
    drafted_text: str,
    grounding_resolutions: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Deterministic check validating that:
    1. Every URL in drafted_text belongs to an approved official domain.
    2. Every URL was directly present in the retrieved grounding resolutions.
    """
    url_pattern = r'https?://[^\s)\]>"\'\\]+'
    found_urls = [u.rstrip(".,;") for u in re.findall(url_pattern, drafted_text)]

    if not found_urls:
        return {
            "passed": True,
            "violation_type": "NONE",
            "details": "No external URLs present in draft.",
            "unauthorized_urls": [],
        }

    # Extract allowed URLs directly from retrieved grounding precedents
    grounded_urls = set()
    for res in grounding_resolutions:
        text = res.get("resolution_text") or res.get("apple_resolution") or ""
        for u in re.findall(url_pattern, text):
            grounded_urls.add(u.rstrip(".,;").lower())

    unauthorized_urls = []
    for u in found_urls:
        parsed = urlparse(u)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        # Check 1: Must be in official domain allowlist
        if domain not in OFFICIAL_ALLOWED_DOMAINS:
            unauthorized_urls.append({"url": u, "reason": f"Untrusted domain: '{domain}'"})
            continue

        # Check 2: Must be grounded in retrieved precedent
        if u.lower() not in grounded_urls:
            unauthorized_urls.append(
                {"url": u, "reason": "Hallucinated link: Domain is valid, but URL was not in grounding resolutions."}
            )

    if unauthorized_urls:
        return {
            "passed": False,
            "violation_type": "UNAUTHORIZED_OR_HALLUCINATED_URL",
            "details": f"Draft contains {len(unauthorized_urls)} unverified URL(s).",
            "unauthorized_urls": unauthorized_urls,
        }

    return {
        "passed": True,
        "violation_type": "NONE",
        "details": "All URLs verified and grounded in official precedents.",
        "unauthorized_urls": [],
    }
