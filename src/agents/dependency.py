from __future__ import annotations
from typing import List, Dict, Any
from src.state.models import InvestigationState, EvidenceItem, EvidenceType, InvestigationTask
from src.tools import (
    ToolExecutionContext,
    ToolException,
    query_deployments,
    query_service_topology,
    query_historical_incidents,
)
from src.llm import estimate_tokens


def dependency_node(state: InvestigationState, context: ToolExecutionContext) -> Dict[str, Any]:
    """
    Dependency Agent:
    - Queries deployment history, config changes, service dependencies, and past postmortems.
    - Adds verified dependency and change facts to the evidence store via reducer.
    """
    new_evidence: List[EvidenceItem] = []
    completed: List[InvestigationTask] = []
    failures: List[str] = []
    tool_calls_count = 0

    ticket = state["incident_ticket"]
    active = state.get("active_tasks", [])

    for task in active:
        if task.assigned_to != "dependency":
            continue

        try:
            if task.tool_name == "query_deployments":
                service = task.tool_params.get("service", ticket.affected_service)
                res = query_deployments(
                    service=service,
                    lookback_hours=task.tool_params.get("lookback_hours", 24),
                    context=context,
                )
                tool_calls_count += 1

                for d in res.deployments:
                    ev_id = f"EV-DEP-{len(new_evidence) + 1}"
                    desc = f"Deployment on '{service}' at {d.timestamp} by {d.author} (tag={d.version_tag}): '{d.commit_message}'"
                    if d.config_diff:
                        desc += f" | Config Diff: {d.config_diff}"
                    new_evidence.append(
                        EvidenceItem(
                            id=ev_id,
                            source="deployments",
                            type=EvidenceType.FACT,
                            description=desc,
                            timestamp=d.timestamp,
                            is_fact=True,
                            confidence=1.0,
                            raw_data=d.model_dump(),
                        )
                    )
                task.status = "COMPLETED"
                task.result = f"Found {len(res.deployments)} deployments for {service}"
                completed.append(task)

            elif task.tool_name == "query_service_topology":
                service = task.tool_params.get("service", ticket.affected_service)
                res = query_service_topology(service=service, context=context)
                tool_calls_count += 1

                ev_id = f"EV-TOPO-{len(new_evidence) + 1}"
                desc = (
                    f"Topology for '{service}': status={res.health_status}, "
                    f"upstream={res.dependencies_upstream}, downstream={res.dependencies_downstream}"
                )
                if res.config_summary:
                    desc += f", config={res.config_summary}"

                new_evidence.append(
                    EvidenceItem(
                        id=ev_id,
                        source="topology",
                        type=EvidenceType.FACT,
                        description=desc,
                        is_fact=True,
                        confidence=1.0,
                        raw_data=res.model_dump(),
                    )
                )

                # Also inspect health of downstream dependencies and deployments of upstream producers
                for upstream_svc in res.dependencies_upstream:
                    # Clean service name if formatted like "catalog-service (via Kafka)"
                    clean_upstream = upstream_svc.split()[0]
                    up_deploys = query_deployments(service=clean_upstream, context=context)
                    tool_calls_count += 1
                    for ud in up_deploys.deployments:
                        up_ev_id = f"EV-DEP-UP-{len(new_evidence) + 1}"
                        new_evidence.append(
                            EvidenceItem(
                                id=up_ev_id,
                                source="deployments",
                                type=EvidenceType.FACT,
                                description=f"Upstream deployment on '{clean_upstream}' at {ud.timestamp}: '{ud.commit_message}' | Diff: {ud.config_diff}",
                                timestamp=ud.timestamp,
                                is_fact=True,
                                confidence=1.0,
                                raw_data=ud.model_dump(),
                            )
                        )

                for downstream_svc in res.dependencies_downstream:
                    downstream_topo = query_service_topology(service=downstream_svc, context=context)
                    tool_calls_count += 1
                    if downstream_topo.health_status in ("UNHEALTHY", "DEGRADED"):
                        down_ev_id = f"EV-TOPO-DOWN-{len(new_evidence) + 1}"
                        new_evidence.append(
                            EvidenceItem(
                                id=down_ev_id,
                                source="topology",
                                type=EvidenceType.FACT,
                                description=f"Downstream dependency '{downstream_svc}' is {downstream_topo.health_status}!",
                                is_fact=True,
                                confidence=1.0,
                                raw_data=downstream_topo.model_dump(),
                            )
                        )

                task.status = "COMPLETED"
                task.result = f"Analyzed topology for {service}"
                completed.append(task)

            elif task.tool_name == "query_historical_incidents":
                service = task.tool_params.get("service", ticket.affected_service)
                res = query_historical_incidents(
                    service=service,
                    search_keywords=task.tool_params.get("search_keywords"),
                    context=context,
                )
                tool_calls_count += 1

                for inc in res.incidents:
                    ev_id = f"EV-HIST-{len(new_evidence) + 1}"
                    desc = f"Historical Incident {inc.incident_id} ({inc.date}): '{inc.title}' | Cause: {inc.root_cause} | Fix: {inc.mitigation}"
                    new_evidence.append(
                        EvidenceItem(
                            id=ev_id,
                            source="historical_incidents",
                            type=EvidenceType.FACT,
                            description=desc,
                            is_fact=True,
                            confidence=0.85,
                            raw_data=inc.model_dump(),
                        )
                    )
                task.status = "COMPLETED"
                task.result = f"Found {len(res.incidents)} historical incidents"
                completed.append(task)

        except ToolException as e:
            fail_msg = f"Dependency tool failure in {e.tool_name}: {e.message}"
            failures.append(fail_msg)
            task.status = "FAILED"
            task.result = fail_msg
            completed.append(task)

    return {
        "evidence_store": new_evidence,
        "completed_tasks": completed,
        "tool_failure_events": failures,
        "total_tool_calls": tool_calls_count,
        "total_tokens_used": 0,
    }
