from __future__ import annotations
from typing import List, Dict, Any, Optional
import re
from pydantic import BaseModel, Field
from src.tools.base import ToolExecutionContext
from src.tools.chaos import apply_chaos


class LogEntry(BaseModel):
    timestamp: str
    level: str  # INFO, WARN, ERROR, FATAL
    service: str
    message: str
    trace_id: Optional[str] = None
    exception: Optional[str] = None


class LogsQueryResult(BaseModel):
    service: str
    total_found: int
    logs: List[LogEntry]
    is_truncated: bool = False
    truncation_notice: Optional[str] = None


class MetricDataPoint(BaseModel):
    timestamp: str
    value: float


class MetricQueryResult(BaseModel):
    service: str
    metric_name: str
    points: List[MetricDataPoint]
    baseline_mean: float
    peak_value: float
    is_anomalous: bool
    anomaly_summary: str


def query_logs(
    service: str,
    query: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    context: Optional[ToolExecutionContext] = None,
) -> LogsQueryResult:
    """
    Queries simulated log entries for a given service, with optional regex/keyword filtering
    and timestamp bounding.
    """
    if context:
        context.record_call("query_logs")
    chaos_override = apply_chaos("query_logs", context)

    raw_logs: List[Dict[str, Any]] = []
    if context and context.scenario_data:
        raw_logs = context.scenario_data.get("logs", [])

    filtered: List[LogEntry] = []
    query_regex = re.compile(query, re.IGNORECASE) if query else None

    for entry in raw_logs:
        msg = entry.get("message", "")
        exc = entry.get("exception", "") or ""
        entry_svc = entry.get("service", "")

        # Match service directly, or match if the message explicitly references this service
        if entry_svc != service and (not service or service not in msg):
            continue
        if query_regex and not (query_regex.search(msg) or query_regex.search(exc)):
            continue

        # Match timestamps if provided (simple string comparison ISO-8601)
        ts = entry.get("timestamp", "")
        if start_time and ts < start_time:
            continue
        if end_time and ts > end_time:
            continue

        filtered.append(
            LogEntry(
                timestamp=ts,
                level=entry.get("level", "INFO"),
                service=entry.get("service", service),
                message=msg,
                trace_id=entry.get("trace_id"),
                exception=exc if exc else None,
            )
        )

    total_found = len(filtered)
    is_truncated = False
    notice = None

    if chaos_override and chaos_override.get("truncate"):
        trunc_limit = chaos_override.get("limit", 2)
        filtered = filtered[:trunc_limit]
        is_truncated = True
        notice = chaos_override.get("notice", "Results truncated by telemetry cluster.")
    elif len(filtered) > limit:
        filtered = filtered[:limit]
        is_truncated = True
        notice = f"Results capped at limit={limit} out of {total_found} entries."

    return LogsQueryResult(
        service=service,
        total_found=total_found,
        logs=filtered,
        is_truncated=is_truncated,
        truncation_notice=notice,
    )


def query_metrics(
    service: str,
    metric_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    context: Optional[ToolExecutionContext] = None,
) -> MetricQueryResult:
    """
    Queries simulated metrics (e.g. cpu, memory, latency_p99, error_rate_5xx) for a service.
    Computes statistical anomalies against baseline.
    """
    if context:
        context.record_call("query_metrics")
    chaos_override = apply_chaos("query_metrics", context)

    raw_metrics: Dict[str, Any] = {}
    if context and context.scenario_data:
        raw_metrics = context.scenario_data.get("metrics", {}).get(service, {})

    points_data = raw_metrics.get(metric_name, [])
    points: List[MetricDataPoint] = []

    for pt in points_data:
        ts = pt.get("timestamp", "")
        if start_time and ts < start_time:
            continue
        if end_time and ts > end_time:
            continue
        points.append(MetricDataPoint(timestamp=ts, value=float(pt.get("value", 0.0))))

    if chaos_override and chaos_override.get("truncate"):
        points = points[: chaos_override.get("limit", 2)]

    if not points:
        return MetricQueryResult(
            service=service,
            metric_name=metric_name,
            points=[],
            baseline_mean=0.0,
            peak_value=0.0,
            is_anomalous=False,
            anomaly_summary=f"No data available for metric '{metric_name}' on service '{service}'.",
        )

    values = [p.value for p in points]
    baseline_mean = sum(values) / len(values)
    peak_value = max(values)
    
    # Simple anomaly threshold: peak is > 2.5x mean or error_rate > 5%
    is_anomalous = False
    summary = f"Normal telemetry for {metric_name}."

    if metric_name.startswith("error_rate") and peak_value > 0.05:
        is_anomalous = True
        summary = f"CRITICAL: Error rate spiked to {peak_value*100:.1f}% (baseline is {baseline_mean*100:.1f}%)."
    elif metric_name.startswith("latency") and baseline_mean > 0 and (peak_value / baseline_mean > 3.0):
        is_anomalous = True
        summary = f"HIGH LATENCY: Latency spiked to {peak_value:.0f}ms (normal baseline: {baseline_mean:.0f}ms)."
    elif metric_name in ["cpu", "memory"] and peak_value > 85.0:
        is_anomalous = True
        summary = f"RESOURCE EXHAUSTION: {metric_name.upper()} reached {peak_value:.1f}%."

    return MetricQueryResult(
        service=service,
        metric_name=metric_name,
        points=points,
        baseline_mean=round(baseline_mean, 2),
        peak_value=round(peak_value, 2),
        is_anomalous=is_anomalous,
        anomaly_summary=summary,
    )
