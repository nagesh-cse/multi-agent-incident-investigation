from __future__ import annotations
from typing import List, Dict, Any
from src.state.models import InvestigationState, EvidenceItem, EvidenceType, InvestigationTask
from src.tools import (
    ToolExecutionContext,
    ToolException,
    query_logs,
    query_metrics,
)


def observability_node(state: InvestigationState, context: ToolExecutionContext) -> Dict[str, Any]:
    """
    Observability Agent:
    - Executes tasks assigned to 'observability' using telemetry tools.
    - Handles tool errors and timeouts with graceful degradation.
    - Adds verified telemetry facts to the evidence store via reducer.
    """
    new_evidence: List[EvidenceItem] = []
    completed: List[InvestigationTask] = []
    failures: List[str] = []
    tool_calls_count = 0

    ticket = state["incident_ticket"]
    active = state.get("active_tasks", [])

    for task in active:
        if task.assigned_to != "observability":
            continue

        try:
            if task.tool_name == "query_logs":
                res = query_logs(
                    service=task.tool_params.get("service", ticket.affected_service),
                    query=task.tool_params.get("query"),
                    limit=task.tool_params.get("limit", 20),
                    context=context,
                )
                tool_calls_count += 1

                if res.logs:
                    for log in res.logs:
                        if log.level in ("ERROR", "FATAL", "WARN"):
                            ev_id = f"EV-LOG-{len(new_evidence) + 1}"
                            desc = f"[{log.level}] {log.service}: {log.message}"
                            if log.exception:
                                desc += f" | Exception: {log.exception}"
                            new_evidence.append(
                                EvidenceItem(
                                    id=ev_id,
                                    source="logs",
                                    type=EvidenceType.FACT,
                                    description=desc,
                                    timestamp=log.timestamp,
                                    is_fact=True,
                                    confidence=1.0,
                                    raw_data=log.model_dump(),
                                )
                            )
                task.status = "COMPLETED"
                task.result = f"Found {res.total_found} log entries (is_truncated={res.is_truncated})"
                completed.append(task)

            elif task.tool_name == "query_metrics":
                metric_name = task.tool_params.get("metric_name", "error_rate_5xx")
                res = query_metrics(
                    service=task.tool_params.get("service", ticket.affected_service),
                    metric_name=metric_name,
                    context=context,
                )
                tool_calls_count += 1

                if res.is_anomalous or res.points:
                    ev_id = f"EV-METRIC-{len(new_evidence) + 1}"
                    desc = f"Metric '{res.metric_name}' on '{res.service}': {res.anomaly_summary} (peak={res.peak_value}, baseline={res.baseline_mean})"
                    new_evidence.append(
                        EvidenceItem(
                            id=ev_id,
                            source="metrics",
                            type=EvidenceType.FACT,
                            description=desc,
                            is_fact=True,
                            confidence=1.0,
                            raw_data=res.model_dump(),
                        )
                    )
                task.status = "COMPLETED"
                task.result = res.anomaly_summary
                completed.append(task)

        except ToolException as e:
            fail_msg = f"Observability tool failure in {e.tool_name}: {e.message}"
            failures.append(fail_msg)
            task.status = "FAILED"
            task.result = fail_msg
            completed.append(task)

    return {
        "evidence_store": new_evidence,
        "completed_tasks": completed,
        "tool_failure_events": failures,
        "total_tool_calls": tool_calls_count,
        "total_tokens_used": 400,
    }
