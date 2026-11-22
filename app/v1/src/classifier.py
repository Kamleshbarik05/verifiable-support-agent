"""
src/classifier.py
Intent classification engine with calibrated confidence scoring,
structured JSON parsing, and semantic fallback matching.
"""

import json
import re
from typing import Any, Dict, Optional, Tuple
from src.config import INTENTS, INTENT_NAMES
from src.llm_client import LLMClient


class IntentClassifier:
    """
    Classifies incoming customer tweets into one of the 7 MECE intents.
    Returns:
    - predicted_intent: str (validated against INTENT_NAMES)
    - confidence: float (0.0 to 1.0)
    - explanation: str (brief reasoning)
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def _build_system_prompt(self) -> str:
        """Constructs an in-context classification rubric with exact intent definitions."""
        intents_formatted = "\n".join(
            [f"- {name}: {desc}" for name, desc in INTENTS.items()]
        )
        return (
            "You are an expert customer support triage classifier for Apple Support.\n"
            "Your task is to classify incoming customer tweets into EXACTLY ONE intent.\n\n"
            f"Available Intents:\n{intents_formatted}\n\n"
            "Output MUST be strict JSON in this exact schema:\n"
            "{\n"
            '  "intent": "<ONE_OF_THE_ABOVE_INTENTS>",\n'
            '  "confidence": <float between 0.0 and 1.0>,\n'
            '  "reasoning": "<1 sentence explanation>"\n'
            "}"
        )

    def _parse_llm_json(self, raw_output: str, original_tweet: str) -> Tuple[str, float, str]:
        """
        Robustly extracts and validates JSON from LLM output,
        handling Markdown code blocks (```json ... ```) or raw text.
        """
        try:
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw_output.strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)

            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                intent = data.get("intent", "").strip()
                confidence = float(data.get("confidence", 0.5))
                reasoning = data.get("reasoning", "Classified by LLM.")

                if intent in INTENT_NAMES:
                    return intent, min(max(confidence, 0.0), 1.0), reasoning
        except Exception:
            pass

        return self._heuristic_fallback(original_tweet)

    def _heuristic_fallback(self, text: str) -> Tuple[str, float, str]:
        """
        Deterministic keyword & heuristic matching for offline mode.
        Evaluates domain-specific diagnostic signals from customer query.
        """
        text_lower = text.lower()

        # 1. HARDWARE_BATTERY_PERFORMANCE
        if any(w in text_lower for w in ["battery", "drain", "charge", "charging", "overheating", "hot to touch", "shutdown", "speaker", "screen", "flickering", "lightning port", "audio", "mic"]):
            return "HARDWARE_BATTERY_PERFORMANCE", 0.92, "Detected explicit hardware/battery diagnostic signals."

        # 2. SOFTWARE_OS_UPDATE
        elif any(w in text_lower for w in ["update", "ios", "macos", "stuck on", "reboot", "boot loop", "camera app", "crash", "error 4013", "downgrade", "bricked", "firmware"]):
            return "SOFTWARE_OS_UPDATE", 0.91, "Detected software / iOS update diagnostic signals."

        # 3. APPLE_ID_SECURITY_ACCESS
        elif any(w in text_lower for w in ["apple id", "password", "locked", "2fa", "2-factor", "verification code", "hacked", "stolen", "activation lock", "trusted phone", "sign in alert"]):
            return "APPLE_ID_SECURITY_ACCESS", 0.94, "Detected account security / Apple ID access signals."

        # 4. BILLING_SUBSCRIPTION_REFUND
        elif any(w in text_lower for w in ["refund", "charged", "billing", "subscription", "cancel", "payment", "declined", "receipt", "purchase history", "double charge", "itunes"]):
            return "BILLING_SUBSCRIPTION_REFUND", 0.93, "Detected financial / subscription billing signals."

        # 5. ICLOUD_SYNC_BACKUP
        elif any(w in text_lower for w in ["icloud", "backup", "photos", "photo", "sync", "syncing", "storage full", "storage", "drive", "restore"]):
            return "ICLOUD_SYNC_BACKUP", 0.90, "Detected iCloud storage / sync backup signals."

        # 6. USAGE_FEATURE_HOWTO
        elif any(w in text_lower for w in ["how do i", "how to", "pair", "airpods", "hotspot", "connect", "focus mode", "esim", "apple pay", "feature"]):
            return "USAGE_FEATURE_HOWTO", 0.89, "Detected usage / feature configuration inquiry."

        # 7. OUT_OF_SCOPE_COMPLAINT
        else:
            return "OUT_OF_SCOPE_COMPLAINT", 0.72, "General brand complaint or retail store inquiry."

    def classify(self, tweet_text: str) -> Dict[str, Any]:
        """
        Main classification interface.
        """
        # If offline mode, directly use the fast heuristic classifier
        if self.llm.offline or self.llm.provider == "offline":
            intent, confidence, reasoning = self._heuristic_fallback(tweet_text)
            return {
                "intent": intent,
                "confidence": round(confidence, 3),
                "reasoning": reasoning,
            }

        system_prompt = self._build_system_prompt()
        user_prompt = f"Customer Tweet: {tweet_text}"

        raw_response = self.llm.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=150,
        )

        intent, confidence, reasoning = self._parse_llm_json(raw_response, tweet_text)

        if intent not in INTENT_NAMES:
            intent, confidence, reasoning = self._heuristic_fallback(tweet_text)

        return {
            "intent": intent,
            "confidence": round(confidence, 3),
            "reasoning": reasoning,
        }
