"""
Pytest configuration and shared fixtures for verifiable-support-agent.
"""

import sys
from pathlib import Path

import pytest

# Ensure repo root and app/v1 are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
V1_DIR = REPO_ROOT / "app" / "v1"

for p in [str(REPO_ROOT), str(V1_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(scope="session")
def sample_queries():
    return {
        "battery_issue": "My iPhone 13 battery drains from 100% to 20% in 3 hours. Battery health is 84%.",
        "battery_hazard": "Battery on my iPhone expanded, cracked the screen, and there is smoke!",
        "pii_query": "Please help me set up my iPhone. My phone number is 555-019-2834.",
        "refund_issue": "Was charged $49.99 for a subscription I canceled. I want a refund.",
        "howto_issue": "How do I set up Personal Hotspot on my iPhone to share data with Mac?",
    }
