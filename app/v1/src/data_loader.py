"""
src/data_loader.py
Dataset ingestion, Twitter text normalization, and conversation thread
reconstruction (Customer Inbound -> Apple Official Outbound).
"""

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from src.config import (
    GOLDEN_EVAL_FILE,
    PAIRED_CONVERSATIONS_FILE,
    PROCESSED_DATA_DIR,
    RAW_TWEETS_FILE,
)


def clean_tweet_text(text: str) -> str:
    """
    Normalizes messy Twitter text while preserving diagnostic signals.

    Transformations:
    1. Unescapes HTML entities (&amp; -> &, &lt; -> <).
    2. Removes Twitter @handle mentions (@AppleSupport, @115858).
    3. Normalizes shortened t.co URLs to a clean [URL] token.
    4. Collapses multiple whitespace characters and trims ends.
    """
    if not isinstance(text, str):
        return ""

    # 1. Decode HTML entities
    cleaned = html.unescape(text)

    # 2. Normalize URLs (e.g., https://t.co/abc123xyz -> [URL])
    cleaned = re.sub(r"https?://\S+", "[URL]", cleaned)

    # 3. Strip @mentions (e.g., @AppleSupport, @user123)
    cleaned = re.sub(r"@\w+", "", cleaned)

    # 4. Collapse repeated whitespaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def reconstruct_conversation_pairs(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Joins customer inbound queries with Apple's official resolution tweets.

    Logic:
    - Filters inbound customer tweets (inbound == True).
    - Filters outbound Apple replies (inbound == False and author_id == 'AppleSupport').
    - Joins on: customer.tweet_id == apple_reply.in_reply_to_tweet_id.
    """
    # Standardize column types
    raw_df["tweet_id"] = raw_df["tweet_id"].astype(str)
    raw_df["in_reply_to_tweet_id"] = raw_df["in_reply_to_tweet_id"].fillna("").astype(str)

    # Separate customer inbound queries and Apple outbound replies
    inbound_df = raw_df[raw_df["inbound"] == True].copy()
    outbound_df = raw_df[
        (raw_df["inbound"] == False) & (raw_df["author_id"] == "AppleSupport")
    ].copy()

    # Join customer query with the first official response
    paired = pd.merge(
        inbound_df[["tweet_id", "text", "created_at"]],
        outbound_df[["in_reply_to_tweet_id", "text", "tweet_id"]],
        left_on="tweet_id",
        right_on="in_reply_to_tweet_id",
        suffixes=("_customer", "_apple"),
    )

    # Clean text columns
    paired["customer_query"] = paired["text_customer"].apply(clean_tweet_text)
    paired["apple_resolution"] = paired["text_apple"].apply(clean_tweet_text)

    # Filter out empty or trivially short tweets (< 15 characters)
    paired = paired[
        (paired["customer_query"].str.len() >= 15)
        & (paired["apple_resolution"].str.len() >= 15)
    ].copy()

    # Select and rename final clean columns
    result = paired[
        [
            "tweet_id_customer",
            "customer_query",
            "tweet_id_apple",
            "apple_resolution",
            "created_at",
        ]
    ].rename(
        columns={
            "tweet_id_customer": "customer_tweet_id",
            "tweet_id_apple": "apple_tweet_id",
        }
    )

    return result.drop_duplicates(subset=["customer_tweet_id"])


def load_or_process_paired_data(
    raw_path: Optional[Path] = None, force_recompute: bool = False
) -> pd.DataFrame:
    """
    Loads pre-processed paired conversations if available;
    otherwise reconstructs them from raw CSV and saves to disk.
    """
    if PAIRED_CONVERSATIONS_FILE.exists() and not force_recompute:
        return pd.read_csv(PAIRED_CONVERSATIONS_FILE)

    target_raw = raw_path or RAW_TWEETS_FILE
    if not target_raw.exists():
        raise FileNotFoundError(
            f"Raw dataset not found at {target_raw}. Run scripts/download_data.py first."
        )

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw_df = pd.read_csv(target_raw)
    paired_df = reconstruct_conversation_pairs(raw_df)
    paired_df.to_csv(PAIRED_CONVERSATIONS_FILE, index=False)
    return paired_df


def load_golden_evaluation_set(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Loads the hand-labeled golden evaluation dataset (JSON format).
    Each sample contains:
    - id: Unique query identifier
    - text: Raw customer tweet
    - gold_intent: True 7-class intent label
    - gold_escalation: True/False escalation decision
    - gold_reason: Ground-truth rationale for escalation/auto-handle
    - gold_historical_resolution: Real historical Apple resolution
    """
    target = path or GOLDEN_EVAL_FILE
    if not target.exists():
        raise FileNotFoundError(
            f"Golden evaluation set not found at {target}. Run scripts/create_golden_set.py first."
        )

    with open(target, "r", encoding="utf-8") as f:
        return json.load(f)
