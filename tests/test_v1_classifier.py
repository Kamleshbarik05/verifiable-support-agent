"""
Regression tests for v1 IntentClassifier.
"""

from src.classifier import IntentClassifier
from src.config import INTENT_NAMES
from src.llm_client import LLMClient


def test_classifier_initialization():
    llm = LLMClient(offline=True)
    classifier = IntentClassifier(llm_client=llm)
    assert classifier is not None


def test_classifier_predicts_valid_mece_intent(sample_queries):
    llm = LLMClient(offline=True)
    classifier = IntentClassifier(llm_client=llm)

    for query_name, text in sample_queries.items():
        res = classifier.classify(text)
        assert res["intent"] in INTENT_NAMES, f"Intent {res['intent']} for {query_name} not in valid taxonomy"
        assert 0.0 <= res["confidence"] <= 1.0, f"Confidence {res['confidence']} out of bounds"
        assert isinstance(res["reasoning"], str) and len(res["reasoning"]) > 0


def test_classifier_hardware_battery_intent():
    llm = LLMClient(offline=True)
    classifier = IntentClassifier(llm_client=llm)
    res = classifier.classify("iPhone 12 battery draining fast and phone overheating")
    assert res["intent"] == "HARDWARE_BATTERY_PERFORMANCE"
    assert res["confidence"] > 0.5
