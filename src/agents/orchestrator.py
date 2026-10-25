from __future__ import annotations
from typing import List, Dict, Any
from src.state.models import InvestigationState, InvestigationTask, CriticVerdictStatus


def orchestrator_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Orchestrator Agent:
    - Plans the investigation.
    - If Critic requested more evidence in a previous iteration, schedules targeted tasks.
    - Otherwise, creates the initial parallel investigation plan for Observability and Dependency agents.
    """
    new_tasks: List[InvestigationTask] = []
    ticket = state["incident_ticket"]
    iteration = state.get("current_iteration", 1)
    critic = state.get("critic_verdict")

    # Case A: Responding to Critic's feedback
    if critic and critic.status == CriticVerdictStatus.REQUEST_MORE_EVIDENCE and critic.suggested_follow_up_tasks:
        for t in critic.suggested_follow_up_tasks:
            t.id = f"TASK-ITER{iteration}-{len(new_tasks)+1}"
            new_tasks.append(t)
    
    # Case B: Initial iteration (Broad investigation)
    else:
        # Observability tasks
        new_tasks.append(
            InvestigationTask(
                id=f"TASK-ITER{iteration}-1",
                assigned_to="observability",
                description=f"Inspect error logs for service '{ticket.affected_service}' around {ticket.timestamp}",
                tool_name="query_logs",
                tool_params={"service": ticket.affected_service, "limit": 20}
            )
        )
        new_tasks.append(
            InvestigationTask(
                id=f"TASK-ITER{iteration}-2",
                assigned_to="observability",
                description=f"Check latency and error metrics for service '{ticket.affected_service}'",
                tool_name="query_metrics",
                tool_params={"service": ticket.affected_service, "metric_name": "error_rate_5xx"}
            )
        )
        new_tasks.append(
            InvestigationTask(
                id=f"TASK-ITER{iteration}-3",
                assigned_to="observability",
                description=f"Check P99 latency metrics for service '{ticket.affected_service}'",
                tool_name="query_metrics",
                tool_params={"service": ticket.affected_service, "metric_name": "latency_p99"}
            )
        )

        # Dependency tasks
        new_tasks.append(
            InvestigationTask(
                id=f"TASK-ITER{iteration}-4",
                assigned_to="dependency",
                description=f"Check recent code or config deployments for service '{ticket.affected_service}'",
                tool_name="query_deployments",
                tool_params={"service": ticket.affected_service, "lookback_hours": 24}
            )
        )
        new_tasks.append(
            InvestigationTask(
                id=f"TASK-ITER{iteration}-5",
                assigned_to="dependency",
                description=f"Examine topology and downstream dependencies of '{ticket.affected_service}'",
                tool_name="query_service_topology",
                tool_params={"service": ticket.affected_service}
            )
        )
        new_tasks.append(
            InvestigationTask(
                id=f"TASK-ITER{iteration}-6",
                assigned_to="dependency",
                description=f"Search historical incident records for '{ticket.affected_service}'",
                tool_name="query_historical_incidents",
                tool_params={"service": ticket.affected_service}
            )
        )

    return {
        "active_tasks": new_tasks,
        "total_tokens_used": 350,
    }
