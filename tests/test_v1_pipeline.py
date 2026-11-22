"""
Regression tests for v1 SupportAgentPipeline.
"""

from src.config import PAIRED_CONVERSATIONS_FILE
from src.data_loader import load_or_process_paired_data
from src.llm_client import LLMClient
from src.pipeline import SupportAgentPipeline


def test_pipeline_initialization():
    llm = LLMClient(offline=True)
    pipeline = SupportAgentPipeline(llm_client=llm)
    assert pipeline is not None


def test_pipeline_processes_query(sample_queries):
    llm = LLMClient(offline=True)
    kb_df = None
    if PAIRED_CONVERSATIONS_FILE.exists():
        kb_df = load_or_process_paired_data(PAIRED_CONVERSATIONS_FILE)

    pipeline = SupportAgentPipeline(knowledge_base_df=kb_df, llm_client=llm)
    output = pipeline.process(sample_queries["battery_issue"])

    assert "intent" in output
    assert "should_escalate" in output
    assert "drafted_reply" in output
    assert "retrieved_cases" in output
    assert isinstance(output["intent_confidence"], float)


def test_pipeline_escalates_hazard(sample_queries):
    llm = LLMClient(offline=True)
    pipeline = SupportAgentPipeline(llm_client=llm)
    output = pipeline.process(sample_queries["battery_hazard"])

    assert output["should_escalate"] is True
    assert output["escalation_tier"] == "TIER_1_HARD_GUARDRAIL"
    assert output["reason_code"] == "HARD_GUARDRAIL_SAFETY_LEGAL"
