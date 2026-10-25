from __future__ import annotations
from typing import List, Dict, Any
from src.state.models import InvestigationState, InvestigationTask, CriticVerdictStatus, OrchestratorLLMOutput
from src.llm import llm_config, LiveTokenTracker, estimate_tokens


def orchestrator_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Orchestrator Agent:
    - Plans the investigation.
    - If live Gemini/OpenRouter LLM is configured, dynamically prompts with structured output.
    - Tracks live token usage via LiveTokenTracker callback.
    - Otherwise, executes deterministic expert planning logic with dynamic token estimation.
    """
    ticket = state["incident_ticket"]
    iteration = state.get("current_iteration", 1)
    critic = state.get("critic_verdict")

    # 1. Try Live LLM invocation if configured
    llm = llm_config.get_chat_model()
    if llm:
        try:
            structured_llm = llm.with_structured_output(OrchestratorLLMOutput)
            critic_info = f"Critic feedback: {critic.reasoning}" if critic else "Initial iteration"
            prompt = (
                f"You are an expert SRE Incident Orchestrator.\n"
                f"Incident Ticket: {ticket.incident_id} - '{ticket.title}' on service '{ticket.affected_service}'.\n"
                f"Description: {ticket.description}\n"
                f"Current Iteration: {iteration}\n"
                f"Context: {critic_info}\n\n"
                f"Generate a list of InvestigationTask items. "
                f"Assign to 'observability' (tools: 'query_logs', 'query_metrics') or "
                f"'dependency' (tools: 'query_deployments', 'query_service_topology', 'query_historical_incidents')."
            )
            tracker = LiveTokenTracker()
            llm_result: OrchestratorLLMOutput = structured_llm.invoke(prompt, config={"callbacks": [tracker]})
            if llm_result and llm_result.tasks:
                for idx, t in enumerate(llm_result.tasks):
                    t.id = f"TASK-LLM-{iteration}-{idx+1}"
                return {
                    "active_tasks": llm_result.tasks,
                    "total_tokens_used": tracker.total_tokens,
                }
        except Exception as e:
            err_msg = str(e).split("\n")[0][:120]
            print(f"  [⚠️ Orchestrator Fallback] LLM unavailable ({type(e).__name__}: {err_msg}). Using deterministic planner.", flush=True)

    # 2. Deterministic Fallback Logic
    new_tasks: List[InvestigationTask] = []
    if critic and critic.status == CriticVerdictStatus.REQUEST_MORE_EVIDENCE and critic.suggested_follow_up_tasks:
        for t in critic.suggested_follow_up_tasks:
            t.id = f"TASK-ITER{iteration}-{len(new_tasks)+1}"
            new_tasks.append(t)
    else:
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
        "total_tokens_used": 0,
    }
