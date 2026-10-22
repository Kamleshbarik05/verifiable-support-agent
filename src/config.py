"""
src/config.py
Centralized configuration, paths, intent taxonomy, and safety thresholds
for verifiable-support-agent.
"""

from pathlib import Path
from typing import Dict, List

# ==========================================
# 1. PATH RESOLUTION (Cross-Platform)
# ==========================================
# BASE_DIR dynamically resolves to the root folder (d:/SDE Assignment)
# regardless of whether the script is run from Windows, Mac, or Linux.
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
GOLDEN_DATA_DIR = DATA_DIR / "golden"

# Raw sampled dataset and reconstructed pairs
RAW_TWEETS_FILE = RAW_DATA_DIR / "apple_support_tweets.csv"
PAIRED_CONVERSATIONS_FILE = PROCESSED_DATA_DIR / "apple_conversations_paired.csv"

# Golden benchmark evaluation dataset (150-200 hand-labeled samples)
GOLDEN_EVAL_FILE = GOLDEN_DATA_DIR / "golden_evaluation_set.json"
CALIBRATION_FILE = GOLDEN_DATA_DIR / "human_judge_calibration.json"


# ==========================================
# 2. INTENT TAXONOMY (7-Class MECE)
# ==========================================
# Explicit definitions allow both the classifier prompt and evaluation judge
# to share the exact same ground-truth criteria.
INTENTS: Dict[str, str] = {
    "HARDWARE_BATTERY_PERFORMANCE": (
        "Battery drain, device overheating, charging faults, physical screen/speaker/mic defects."
    ),
    "SOFTWARE_OS_UPDATE": (
        "iOS/macOS update download or installation failure, post-update bugs, app crashes, reboot loops."
    ),
    "APPLE_ID_SECURITY_ACCESS": (
        "Locked Apple ID accounts, 2FA verification issues, forgotten passwords, suspicious login alerts."
    ),
    "BILLING_SUBSCRIPTION_REFUND": (
        "Unrecognized App Store charges, recurring subscription cancellations, refund disputes, payment errors."
    ),
    "ICLOUD_SYNC_BACKUP": (
        "iCloud storage full alerts, photo/drive syncing failures, device backup and restore issues."
    ),
    "USAGE_FEATURE_HOWTO": (
        "How-to guides, feature configuration, pairing AirPods/Apple Watch, Focus modes, data transfer."
    ),
    "OUT_OF_SCOPE_COMPLAINT": (
        "Brand rants/venting without a diagnostic issue, physical Apple Store retail queries, non-Apple products."
    )
}

INTENT_NAMES: List[str] = list(INTENTS.keys())


# ==========================================
# 3. RISK & ESCALATION THRESHOLDS
# ==========================================
# The Two-Tier Escalation Policy parameters:
# 1. If Intent Confidence is below this threshold, escalate due to ambiguity.
INTENT_CONFIDENCE_THRESHOLD: float = 0.70

# 2. If RAG historical resolution similarity is below this, escalate rather than hallucinating.
RAG_SIMILARITY_THRESHOLD: float = 0.50

# 3. Deterministic Hard-Guardrail Triggers (Immediate Human Escalation)
# Any query matching these safety-critical patterns MUST escalate regardless of confidence.
ESCALATION_HARD_KEYWORDS: List[str] = [
    "lawyer", "legal", "sue", "lawsuit", "court", "attorney",
    "swollen battery", "battery exploded", "smoke", "fire hazard",
    "hacked", "stolen", "unauthorized charge", "chargeback", "compromised"
]


# ==========================================
# 4. MODEL & RETRIEVAL CONFIGURATION
# ==========================================
# Lightweight local embedding model (runs in milliseconds on CPU)
EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"

# Top-K historical resolutions to retrieve for grounding
RAG_TOP_K: int = 3

# Temperature 0.0 guarantees deterministic, reproducible answers
LLM_TEMPERATURE: float = 0.0
