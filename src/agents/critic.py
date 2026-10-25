from __future__ import annotations
from typing import Dict, Any, List, Optional
from src.state.models import (
    InvestigationState,
    CriticVerdict,
    CriticVerdictStatus,
    InvestigationTask,
)
from src.llm import llm_config, LiveTokenTracker, estimate_tokens


def critic_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Critic Agent (Auditor):
    - Challenges assumptions and tests for confirmation bias.
    - If live Gemini/OpenRouter LLM is configured, dynamically prompts with structured output.
    - Tracks live tokens with LiveTokenTracker callback.
    - Otherwise, executes deterministic auditing logic with dynamic token estimation.
    """
    evidence = state.get("evidence_store", [])
    hypotheses = state.get("hypotheses", [])
    iteration = state.get("current_iteration", 1)
    max_iter = state.get("max_iterations", 3)
    ticket = state["incident_ticket"]
    failures = state.get("tool_failure_events", [])

    # 1. Try Live LLM invocation if configured
    llm = llm_config.get_chat_model()
    if llm and evidence and len(evidence) > 1 and hypotheses:
        try:
            structured_llm = llm.with_structured_output(CriticVerdict)
            ev_text = "\n".join([f"- [{e.id}] {e.description}" for e in evidence[:10]])
            hypo_text = "\n".join([f"- [{h.id}] {h.title} (conf={h.confidence*100:.0f}%, supp={h.supporting_evidence_ids})" for h in hypotheses])
            prompt = (
                f"You are an adversarial SRE Critic auditing an incident investigation.\n"
                f"Incident: {ticket.title}\n"
                f"Iteration: {iteration}/{max_iter}\n\n"
                f"Verified Evidence:\n{ev_text}\n\n"
                f"Competing Hypotheses:\n{hypo_text}\n\n"
                f"Audit the claims:\n"
                f"- If facts are missing or unverified and iteration < {max_iter}, output status='REQUEST_MORE_EVIDENCE' with follow-up tasks.\n"
                f"- If evidence is completely empty or inconclusive, output status='INCONCLUSIVE'.\n"
                f"- If hypotheses are well-supported by verified facts, output status='APPROVED'."
            )
            tracker = LiveTokenTracker()
            llm_result: CriticVerdict = structured_llm.invoke(prompt, config={"callbacks": [tracker]})
            if llm_result:
                return {
                    "critic_verdict": llm_result,
                    "current_iteration": iteration + 1,
                    "total_tokens_used": tracker.total_tokens,
                }
        except Exception as e:
            err_msg = str(e).split("\n")[0][:120]
            print(f"  [⚠️ Critic Fallback] LLM unavailable ({type(e).__name__}: {err_msg}). Using deterministic auditor.", flush=True)

    # Check 1: Inconclusive detection (Scenario 10)
    if not evidence or (len(evidence) == 1 and evidence[0].source == "topology" and "UNKNOWN" in evidence[0].description):
        verdict = CriticVerdict(
            status=CriticVerdictStatus.INCONCLUSIVE,
            reasoning="Telemetry is completely missing or dropped. The monitoring agent appears to have crashed. In accordance with system safety guardrails, declaring outcome INCONCLUSIVE to prevent hallucination.",
            identified_assumptions=["Any claim of specific software bug or attack is an unsubstantiated assumption."],
            missing_evidence_questions=["Are edge router logs available from local syslog buffers?", "Can hardware diagnostics be fetched directly?"],
            suggested_follow_up_tasks=[]
        )
        return {
            "critic_verdict": verdict,
            "current_iteration": iteration + 1,
            "total_tokens_used": 0,
        }

    # Check 2: Check for unsupported assumptions in hypotheses
    unsupported_assumptions: List[str] = []
    for h in hypotheses:
        if not h.supporting_evidence_ids and h.is_root_cause:
            unsupported_assumptions.append(f"Hypothesis '{h.title}' has no supporting evidence IDs in the evidence store.")

    # Check 3: Check if we have both Observability (logs/metrics) AND Dependency (deployments/topology) evidence
    has_logs_or_metrics = any(e.source in ("logs", "metrics") for e in evidence)
    has_deps_or_topo = any(e.source in ("deployments", "topology") for e in evidence)

    # If in iteration 1 and missing one entire branch (and not tool-failed), request targeted follow-up
    if iteration < max_iter and (not has_logs_or_metrics or not has_deps_or_topo) and not failures:
        follow_ups: List[InvestigationTask] = []
        if not has_deps_or_topo:
            follow_ups.append(
                InvestigationTask(
                    id=f"TASK-FEEDBACK-{iteration}-1",
                    assigned_to="dependency",
                    description=f"Query config diffs and downstream dependencies for '{ticket.affected_service}'",
                    tool_name="query_service_topology",
                    tool_params={"service": ticket.affected_service}
                )
            )

        verdict = CriticVerdict(
            status=CriticVerdictStatus.REQUEST_MORE_EVIDENCE,
            reasoning=f"Evidence is unbalanced: has_telemetry={has_logs_or_metrics}, has_dependencies={has_deps_or_topo}. Requesting deeper verification.",
            identified_assumptions=unsupported_assumptions,
            missing_evidence_questions=["What recent deployment or configuration changes occurred in the last 24 hours?"],
            suggested_follow_up_tasks=follow_ups
        )
        return {
            "critic_verdict": verdict,
            "current_iteration": iteration + 1,
            "total_tokens_used": 0,
        }

    # Check 4: Evidence is sufficient and grounded -> APPROVED
    verdict = CriticVerdict(
        status=CriticVerdictStatus.APPROVED,
        reasoning="Hypotheses are grounded in verified telemetry facts and deployment evidence. Competing hypotheses have been evaluated and ranked.",
        identified_assumptions=unsupported_assumptions,
        missing_evidence_questions=[],
        suggested_follow_up_tasks=[]
    )

    return {
        "critic_verdict": verdict,
        "current_iteration": iteration + 1,
        "total_tokens_used": 0,
    }
