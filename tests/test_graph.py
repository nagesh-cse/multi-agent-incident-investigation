import pytest
from src.data_loader import load_scenario
from src.graph import run_investigation
from src.state.models import CriticVerdictStatus


def test_investigation_scenario_01_config_rollout():
    scenario = load_scenario("INC-01")
    final_state = run_investigation(scenario)

    assert final_state.get("final_report") is not None
    report = final_state["final_report"]

    # Check root cause resolution
    assert report.conclusion_status == "RESOLVED"
    assert "pool" in (report.probable_root_cause or "").lower() or "connection" in (report.probable_root_cause or "").lower()
    assert report.confidence_level >= 0.80

    # Check evidence grounding: facts vs assumptions
    assert len(report.facts) >= 2
    fact_sources = {f.source for f in report.facts}
    assert "logs" in fact_sources or "deployments" in fact_sources

    # Check mitigations
    assert len(report.recommended_actions) >= 1
    assert any(a.priority == "P0" for a in report.recommended_actions)

    # Check metrics
    assert final_state["total_tool_calls"] > 0
    assert final_state["total_tokens_used"] > 0


def test_investigation_scenario_07_tool_failure_recovery():
    """Scenario 7 simulates a timeout in query_logs. Agent must recover gracefully."""
    scenario = load_scenario("INC-07")
    final_state = run_investigation(scenario)

    assert final_state.get("final_report") is not None
    # Verify that the tool failure event was recorded in state
    assert len(final_state.get("tool_failure_events", [])) >= 1
    assert any("timeout" in f.lower() for f in final_state["tool_failure_events"])
    # The investigation completed despite the tool failure
    assert final_state["final_report"].conclusion_status == "RESOLVED"


def test_investigation_scenario_10_inconclusive_verdict():
    """Scenario 10 has zero telemetry. Critic must flag INCONCLUSIVE and avoid hallucinating."""
    scenario = load_scenario("INC-10")
    final_state = run_investigation(scenario)

    assert final_state.get("final_report") is not None
    report = final_state["final_report"]
    assert report.conclusion_status == "INCONCLUSIVE"
    assert report.probable_root_cause is None
    assert final_state["critic_verdict"].status == CriticVerdictStatus.INCONCLUSIVE
