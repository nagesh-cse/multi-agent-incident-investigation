"""
LangGraph Multi-Agent Production Incident Investigation State Machine.
Implements:
- Parallel execution of Observability & Dependency specialist agents
- Shared Blackboard InvestigationState with TypedDict and Annotated reducers
- Feedback loop through Critic agent back to Orchestrator
- Bounded retries and termination conditions
- Failure recovery and inconclusive verdict handling
"""
from __future__ import annotations
import time
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, START, END

from src.state.models import (
    InvestigationState,
    IncidentTicket,
    CriticVerdictStatus
)
from src.tools.base import ToolExecutionContext
from src.agents.orchestrator import orchestrator_node
from src.agents.observability import observability_node
from src.agents.dependency import dependency_node
from src.agents.reasoning import reasoning_node
from src.agents.critic import critic_node
from src.agents.reporting import reporting_node


def route_critic_verdict(state: InvestigationState) -> Literal["orchestrator", "reporting"]:
    """
    Conditional Edge:
    - If Critic requests more evidence and we haven't hit max iterations -> Loop back to Orchestrator!
    - Otherwise (Approved, Inconclusive, or max iterations reached) -> Proceed to Reporting!
    """
    critic = state.get("critic_verdict")
    current_iter = state.get("current_iteration", 1)
    max_iter = state.get("max_iterations", 3)
    
    if critic and critic.status == CriticVerdictStatus.REQUEST_MORE_EVIDENCE and current_iter <= max_iter:
        return "orchestrator"
    return "reporting"


def build_investigation_graph(context: ToolExecutionContext):
    """
    Constructs and compiles the multi-agent StateGraph with parallel specialist execution
    and dynamic feedback loops.
    """
    workflow = StateGraph(InvestigationState)

    # Helper logger
    def logged_node(agent_name: str, emoji: str, desc: str, fn):
        def _wrapper(state):
            print(f"[{emoji} {agent_name}] {desc} (Iteration {state.get('current_iteration', 1)})...", flush=True)
            res = fn(state)
            return res
        return _wrapper

    # 1. Register Agent Nodes with live progress feedback
    workflow.add_node("orchestrator", logged_node("Orchestrator Agent", "🤖", "Formulating investigation plan and task assignments", orchestrator_node))
    
    # Tool nodes wrap execution context
    workflow.add_node("observability", logged_node("Observability Agent", "🔍", "Querying telemetry logs and metrics", lambda s: observability_node(s, context)))
    workflow.add_node("dependency", logged_node("Dependency Agent", "🕸️ ", "Inspecting topology, deployments, and incident history", lambda s: dependency_node(s, context)))
    
    workflow.add_node("reasoning", logged_node("Reasoning Agent", "🧠", "Evaluating telemetry & constructing competing hypotheses", reasoning_node))
    workflow.add_node("critic", logged_node("Critic Agent", "⚖️ ", "Auditing hypotheses against verified facts and testing confirmation bias", critic_node))
    workflow.add_node("reporting", logged_node("Reporting Agent", "📝", "Synthesizing final evidence-backed RCA report", reporting_node))

    # 2. Wire Graph Topology
    # Start -> Orchestrator
    workflow.add_edge(START, "orchestrator")

    # Parallel Fan-Out: Orchestrator -> Observability AND Orchestrator -> Dependency
    workflow.add_edge("orchestrator", "observability")
    workflow.add_edge("orchestrator", "dependency")

    # Fan-In: Both Observability and Dependency feed into Reasoning
    workflow.add_edge("observability", "reasoning")
    workflow.add_edge("dependency", "reasoning")

    # Reasoning -> Critic Audit
    workflow.add_edge("reasoning", "critic")

    # Conditional Routing from Critic: Loop back to Orchestrator or finalize in Reporting
    workflow.add_conditional_edges(
        "critic",
        route_critic_verdict,
        {
            "orchestrator": "orchestrator",
            "reporting": "reporting",
        }
    )

    # Reporting -> End
    workflow.add_edge("reporting", END)

    return workflow.compile()


def run_investigation(scenario: Dict[str, Any], max_iterations: int = 3) -> Dict[str, Any]:
    """
    Entrypoint function to run a complete multi-agent investigation on a scenario.
    """
    ticket = IncidentTicket(
        incident_id=scenario.get("incident_id", "INC-TEST"),
        title=scenario.get("title", "Untitled Incident"),
        description=scenario.get("description", ""),
        timestamp=scenario.get("timestamp", "2026-10-24T00:00:00Z"),
        affected_service=scenario.get("affected_service", "unknown"),
        severity=scenario.get("severity", "HIGH"),
        initial_symptoms=scenario.get("initial_symptoms", []),
    )

    context = ToolExecutionContext(scenario_data=scenario)
    
    initial_state: InvestigationState = {
        "incident_ticket": ticket,
        "current_iteration": 1,
        "max_iterations": max_iterations,
        "active_tasks": [],
        "completed_tasks": [],
        "evidence_store": [],
        "hypotheses": [],
        "critic_verdict": None,
        "final_report": None,
        "total_tokens_used": 0,
        "total_tool_calls": 0,
        "start_time": time.time(),
        "end_time": 0.0,
        "tool_failure_events": [],
    }

    app = build_investigation_graph(context)
    final_output = app.invoke(initial_state)

    final_output["end_time"] = time.time()
    return final_output
