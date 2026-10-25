from __future__ import annotations
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from src.tools.base import ToolExecutionContext
from src.tools.chaos import apply_chaos


class DeploymentEvent(BaseModel):
    timestamp: str
    version_tag: str
    author: str
    commit_message: str
    config_diff: Dict[str, Any] = Field(default_factory=dict)
    is_suspect: bool = False


class DeploymentsQueryResult(BaseModel):
    service: str
    deployments: List[DeploymentEvent]


class TopologyNode(BaseModel):
    service_name: str
    service_type: str  # "api_service", "database", "cache", "external_api", "queue"
    health_status: str  # "HEALTHY", "DEGRADED", "UNHEALTHY"
    dependencies_upstream: List[str] = Field(default_factory=list)
    dependencies_downstream: List[str] = Field(default_factory=list)
    config_summary: Dict[str, Any] = Field(default_factory=dict)


class HistoricalIncidentRecord(BaseModel):
    incident_id: str
    title: str
    date: str
    root_cause: str
    mitigation: str
    similarity_score: float = 1.0


class HistoricalIncidentsQueryResult(BaseModel):
    service: str
    incidents: List[HistoricalIncidentRecord]


def query_deployments(
    service: str,
    lookback_hours: int = 24,
    context: Optional[ToolExecutionContext] = None,
) -> DeploymentsQueryResult:
    """
    Queries deployment and configuration change events for a service.
    """
    if context:
        context.record_call("query_deployments")
    chaos_override = apply_chaos("query_deployments", context)

    raw_deploys: List[Dict[str, Any]] = []
    if context and context.scenario_data:
        raw_deploys = context.scenario_data.get("deployments", {}).get(service, [])

    results: List[DeploymentEvent] = []
    for d in raw_deploys:
        results.append(
            DeploymentEvent(
                timestamp=d.get("timestamp", ""),
                version_tag=d.get("version_tag", ""),
                author=d.get("author", "unknown"),
                commit_message=d.get("commit_message", ""),
                config_diff=d.get("config_diff", {}),
                is_suspect=d.get("is_suspect", False),
            )
        )

    if chaos_override and chaos_override.get("truncate"):
        results = results[: chaos_override.get("limit", 1)]

    return DeploymentsQueryResult(service=service, deployments=results)


def query_service_topology(
    service: str,
    context: Optional[ToolExecutionContext] = None,
) -> TopologyNode:
    """
    Queries the service dependency graph: upstream callers, downstream dependencies,
    and health status of neighbor services.
    """
    if context:
        context.record_call("query_service_topology")
    apply_chaos("query_service_topology", context)

    topo_data: Dict[str, Any] = {}
    if context and context.scenario_data:
        topo_data = context.scenario_data.get("topology", {}).get(service, {})

    return TopologyNode(
        service_name=service,
        service_type=topo_data.get("service_type", "api_service"),
        health_status=topo_data.get("health_status", "UNKNOWN"),
        dependencies_upstream=topo_data.get("upstream", []),
        dependencies_downstream=topo_data.get("downstream", []),
        config_summary=topo_data.get("config_summary", {}),
    )


def query_historical_incidents(
    service: str,
    search_keywords: Optional[str] = None,
    context: Optional[ToolExecutionContext] = None,
) -> HistoricalIncidentsQueryResult:
    """
    Searches past incident postmortems for similar patterns and historical mitigations.
    """
    if context:
        context.record_call("query_historical_incidents")
    apply_chaos("query_historical_incidents", context)

    raw_history: List[Dict[str, Any]] = []
    if context and context.scenario_data:
        raw_history = context.scenario_data.get("historical_incidents", [])

    matches: List[HistoricalIncidentRecord] = []
    kw = (search_keywords or "").lower()

    for rec in raw_history:
        # Match service or keyword
        rec_service = rec.get("service", "")
        title = rec.get("title", "")
        rc = rec.get("root_cause", "")
        
        matches_kw = not kw or (kw in title.lower() or kw in rc.lower())
        if rec_service == service or matches_kw:
            matches.append(
                HistoricalIncidentRecord(
                    incident_id=rec.get("incident_id", "INC-PREV"),
                    title=title,
                    date=rec.get("date", "2025-01-01"),
                    root_cause=rc,
                    mitigation=rec.get("mitigation", ""),
                    similarity_score=float(rec.get("similarity_score", 0.8)),
                )
            )

    return HistoricalIncidentsQueryResult(service=service, incidents=matches)
