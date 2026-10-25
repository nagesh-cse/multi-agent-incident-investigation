import pytest
from src.tools import (
    ToolExecutionContext,
    ToolTimeoutError,
    query_logs,
    query_metrics,
    query_deployments,
    query_service_topology,
    query_historical_incidents,
)

SAMPLE_SCENARIO = {
    "logs": [
        {"timestamp": "2026-10-24T14:00:00Z", "level": "INFO", "service": "payment-service", "message": "Starting worker"},
        {"timestamp": "2026-10-24T14:05:00Z", "level": "ERROR", "service": "payment-service", "message": "Connection refused to db", "exception": "DBConnectionError: pool exhausted"},
        {"timestamp": "2026-10-24T14:06:00Z", "level": "WARN", "service": "auth-service", "message": "Token refresh slow"},
    ],
    "metrics": {
        "payment-service": {
            "error_rate_5xx": [
                {"timestamp": "2026-10-24T14:00:00Z", "value": 0.01},
                {"timestamp": "2026-10-24T14:05:00Z", "value": 0.45},
            ],
            "latency_p99": [
                {"timestamp": "2026-10-24T14:00:00Z", "value": 120.0},
                {"timestamp": "2026-10-24T14:05:00Z", "value": 4500.0},
            ]
        }
    },
    "deployments": {
        "payment-service": [
            {
                "timestamp": "2026-10-24T13:50:00Z",
                "version_tag": "v1.2.3",
                "author": "dev@corp.com",
                "commit_message": "Tune pool size",
                "config_diff": {"max_connections": 5},
                "is_suspect": True,
            }
        ]
    },
    "topology": {
        "payment-service": {
            "service_type": "api_service",
            "health_status": "DEGRADED",
            "upstream": ["api-gateway"],
            "downstream": ["postgres-db", "stripe-gateway"],
            "config_summary": {"pool_size": 5}
        }
    },
    "historical_incidents": [
        {
            "incident_id": "INC-101",
            "service": "payment-service",
            "title": "Postgres pool exhaustion",
            "date": "2025-08-12",
            "root_cause": "max_connections set too low",
            "mitigation": "Increased pool to 50"
        }
    ],
    "chaos_rules": {}
}


def test_query_logs_filtering():
    ctx = ToolExecutionContext(scenario_data=SAMPLE_SCENARIO)
    res = query_logs(service="payment-service", query="refused", context=ctx)
    assert res.total_found == 1
    assert res.logs[0].level == "ERROR"
    assert "DBConnectionError" in (res.logs[0].exception or "")
    assert ctx.total_calls == 1


def test_query_metrics_anomaly_detection():
    ctx = ToolExecutionContext(scenario_data=SAMPLE_SCENARIO)
    res = query_metrics(service="payment-service", metric_name="error_rate_5xx", context=ctx)
    assert res.is_anomalous is True
    assert "spiked" in res.anomaly_summary
    assert res.peak_value == 0.45


def test_query_deployments_and_topology():
    ctx = ToolExecutionContext(scenario_data=SAMPLE_SCENARIO)
    deploys = query_deployments(service="payment-service", context=ctx)
    assert len(deploys.deployments) == 1
    assert deploys.deployments[0].config_diff == {"max_connections": 5}

    topo = query_service_topology(service="payment-service", context=ctx)
    assert topo.health_status == "DEGRADED"
    assert "postgres-db" in topo.dependencies_downstream


def test_query_historical_incidents():
    ctx = ToolExecutionContext(scenario_data=SAMPLE_SCENARIO)
    history = query_historical_incidents(service="payment-service", search_keywords="pool", context=ctx)
    assert len(history.incidents) == 1
    assert history.incidents[0].incident_id == "INC-101"


def test_chaos_timeout_injection():
    chaos_scenario = dict(SAMPLE_SCENARIO)
    chaos_scenario["chaos_rules"] = {
        "query_logs": {"action": "timeout", "message": "Cluster timeout"}
    }
    ctx = ToolExecutionContext(scenario_data=chaos_scenario)
    
    with pytest.raises(ToolTimeoutError) as exc_info:
        query_logs(service="payment-service", context=ctx)
    
    assert "Cluster timeout" in str(exc_info.value)
    assert len(ctx.failure_log) == 1
