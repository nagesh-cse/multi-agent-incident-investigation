import pytest
from src.data_loader import list_scenarios, load_scenario
from src.tools import ToolExecutionContext, query_logs, query_metrics, query_deployments


def test_all_10_scenarios_load():
    scenarios = list_scenarios()
    assert len(scenarios) == 10
    
    for inc_id in scenarios:
        data = load_scenario(inc_id)
        assert data["incident_id"] == inc_id
        assert "ground_truth" in data
        assert "root_cause_summary" in data["ground_truth"]
        assert "key_evidence" in data["ground_truth"]
        assert len(data["ground_truth"]["key_evidence"]) > 0


def test_scenario_01_querying():
    data = load_scenario("INC-01")
    ctx = ToolExecutionContext(scenario_data=data)
    logs = query_logs(service="payment-service", query="pool exhausted", context=ctx)
    assert len(logs.logs) >= 1
    
    deploys = query_deployments(service="payment-service", context=ctx)
    assert len(deploys.deployments) == 1
    assert deploys.deployments[0].config_diff.get("max_connections") == 5


def test_scenario_10_inconclusive_structure():
    data = load_scenario("INC-10")
    assert "INCONCLUSIVE" in data["ground_truth"]["root_cause_summary"]
