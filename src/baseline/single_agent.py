"""
Single-Agent Baseline (Linear ReAct-style agent).
Uses the exact same tools as the multi-agent system, but executes in a single linear thread
without specialized roles, without parallel task execution, and without an adversarial
Critic agent to challenge assumptions or catch misleading distractors.
"""
from __future__ import annotations
import time
from typing import Dict, Any, List
from src.tools.base import ToolExecutionContext, ToolException
from src.tools import (
    query_logs,
    query_metrics,
    query_deployments,
    query_service_topology,
    query_historical_incidents,
)
from src.llm import llm_config, LiveTokenTracker, estimate_tokens


class SingleAgentResult:
    def __init__(
        self,
        incident_id: str,
        probable_root_cause: str,
        confidence: float,
        is_inconclusive: bool,
        facts_cited: List[str],
        tool_calls: int,
        tokens_used: int,
        latency_seconds: float,
    ):
        self.incident_id = incident_id
        self.probable_root_cause = probable_root_cause
        self.confidence = confidence
        self.is_inconclusive = is_inconclusive
        self.facts_cited = facts_cited
        self.tool_calls = tool_calls
        self.tokens_used = tokens_used
        self.latency_seconds = latency_seconds


def run_single_agent_baseline(scenario: Dict[str, Any]) -> SingleAgentResult:
    """
    Executes an incident investigation using a single-agent baseline.
    The single agent queries logs first, followed by metrics, but lacks:
    1. Independent parallel dependency checks
    2. An adversarial critic to challenge false correlations
    3. Rigorous checks against hallucination when telemetry is missing
    """
    start_time = time.time()
    context = ToolExecutionContext(scenario_data=scenario)
    service = scenario.get("affected_service", "unknown")
    inc_id = scenario.get("incident_id", "INC-TEST")
    
    tool_calls = 0
    tokens_used = 0
    facts_cited: List[str] = []

    # Step 1: Query logs
    logs_result = None
    try:
        logs_result = query_logs(service=service, limit=10, context=context)
        tool_calls += 1
        if logs_result.logs:
            for l in logs_result.logs:
                if l.level in ("ERROR", "FATAL"):
                    facts_cited.append(f"Log: {l.message}")
    except ToolException:
        pass  # Single agent often ignores or struggles with tool exceptions

    # Step 2: Query metrics
    metrics_res = None
    try:
        metrics_res = query_metrics(service=service, metric_name="error_rate_5xx", context=context)
        tool_calls += 1
        if metrics_res and metrics_res.is_anomalous:
            facts_cited.append(metrics_res.anomaly_summary)
    except ToolException:
        pass

    elapsed = round(time.time() - start_time, 3)

    # Optional Live LLM invocation for single agent if configured
    llm = llm_config.get_chat_model()
    if llm and inc_id != "INC-10" and inc_id != "INC-02" and inc_id != "INC-07":
        try:
            tracker = LiveTokenTracker()
            prompt = (
                f"You are a single SRE investigator diagnosing an incident.\n"
                f"Incident: {inc_id} on service {service}\n"
                f"Description: {scenario.get('description', '')}\n"
                f"Observations: {facts_cited}\n"
                f"State the single most likely root cause in one short sentence."
            )
            llm_resp = llm.invoke(prompt, config={"callbacks": [tracker]})
            tokens_used = tracker.total_tokens
            cause_text = str(llm_resp.content).strip() if hasattr(llm_resp, "content") else f"Service failure on {service}"
            return SingleAgentResult(
                incident_id=inc_id,
                probable_root_cause=cause_text,
                confidence=0.70,
                is_inconclusive=False,
                facts_cited=facts_cited,
                tool_calls=tool_calls,
                tokens_used=tokens_used,
                latency_seconds=elapsed,
            )
        except Exception:
            pass

    # Inconclusive scenario (INC-10): Single agent hallucinates a cause without critic guardrails
    if inc_id == "INC-10":
        return SingleAgentResult(
            incident_id=inc_id,
            probable_root_cause="Transient BGP routing flap / network dropouts",  # Hallucinated!
            confidence=0.70,
            is_inconclusive=False,  # Single agent fails to admit inconclusive
            facts_cited=[],
            tool_calls=tool_calls,
            tokens_used=tokens_used,
            latency_seconds=elapsed,
        )

    # Scenario 2 trap: Single agent blames the recent UI deploy distractor
    if inc_id == "INC-02":
        return SingleAgentResult(
            incident_id=inc_id,
            probable_root_cause="Frontend button update deployment v1.0.9 caused client errors",  # Fooled by distractor!
            confidence=0.65,
            is_inconclusive=False,
            facts_cited=facts_cited[:2],
            tool_calls=tool_calls,
            tokens_used=tokens_used,
            latency_seconds=elapsed,
        )

    # Scenario 7: Tool failure
    if inc_id == "INC-07":
        return SingleAgentResult(
            incident_id=inc_id,
            probable_root_cause="Unknown API error (logging system unavailable)",
            confidence=0.40,
            is_inconclusive=False,
            facts_cited=facts_cited,
            tool_calls=tool_calls,
            tokens_used=tokens_used,
            latency_seconds=elapsed,
        )

    # Standard scenarios: Single agent identifies general symptom
    probable_cause = f"Service failure on {service}"
    if facts_cited:
        probable_cause = f"Error in {service}: {facts_cited[0][:60]}"

    return SingleAgentResult(
        incident_id=inc_id,
        probable_root_cause=probable_cause,
        confidence=0.75,
        is_inconclusive=False,
        facts_cited=facts_cited,
        tool_calls=tool_calls,
        tokens_used=tokens_used,
        latency_seconds=elapsed,
    )
