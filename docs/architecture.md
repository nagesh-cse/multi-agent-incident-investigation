# System Architecture: Multi-Agent Production Incident Investigation

## 1. High-Level Architecture Overview

The system is designed as a **Stateful, Cyclic Multi-Agent Investigation Engine** built on **LangGraph** and **Pydantic**. Rather than chaining static LLM prompts, the architecture models how an elite Site Reliability Engineering (SRE) team investigates critical production incidents: specialist agents gather telemetry and dependency facts in parallel, synthesize competing hypotheses, cross-examine evidence through an adversarial Critic, and iterate through feedback loops before producing an authoritative Root Cause Analysis (RCA).

```mermaid
graph TD
    %% Entry
    Start([🚨 Production Incident Alert]) --> Orchestrator[<b>1. Orchestrator Agent</b><br/>Plans & delegates tasks]

    %% Parallel Investigation Branch
    subgraph Parallel Specialists ["Parallel Investigation Branch"]
        Orchestrator -->|Dispatch log & metric queries| ObsAgent[<b>2. Observability Agent</b><br/>• query_logs<br/>• query_metrics<br/>• Anomaly detection]
        Orchestrator -->|Dispatch deploy & topology queries| DepAgent[<b>3. Dependency Agent</b><br/>• query_deployments<br/>• query_service_topology<br/>• query_historical_incidents]
    end

    %% Blackboard Fan-In
    ObsAgent -->|Emit Verified Facts| SharedState[(<b>Shared Investigation State</b><br/>Blackboard: Facts vs Assumptions)]
    DepAgent -->|Emit Verified Facts| SharedState

    SharedState --> Reasoning[<b>4. Reasoning Agent</b><br/>• Competing hypotheses H1, H2, H3<br/>• Calibrated confidence weights]

    Reasoning --> Critic[<b>5. Critic Agent (Auditor)</b><br/>• Challenges false correlations<br/>• Detects unsupported assumptions]

    %% Feedback Loop / Conditional Branch
    Critic -->|Verdict: REQUEST_MORE_EVIDENCE<br/>Iteration < Max Iterations| Orchestrator
    Critic -->|Verdict: APPROVED or INCONCLUSIVE<br/>or Max Iterations Reached| Reporter[<b>6. Reporting Agent</b><br/>• Executive summary<br/>• Facts vs assumptions table<br/>• Immediate & long-term actions]

    Reporter --> EndNode([📄 Final Grounded RCA Report])

    %% Styling
    style Start fill:#f97316,stroke:#c2410c,stroke-width:2px,color:#fff
    style Orchestrator fill:#2563eb,stroke:#1d4ed8,stroke-width:2px,color:#fff
    style ObsAgent fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#fff
    style DepAgent fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#fff
    style SharedState fill:#475569,stroke:#334155,stroke-width:2px,color:#fff
    style Reasoning fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#fff
    style Critic fill:#dc2626,stroke:#b91c1c,stroke-width:2px,color:#fff
    style Reporter fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    style EndNode fill:#10b981,stroke:#059669,stroke-width:2px,color:#fff
```

---

## 2. The Six Specialized Agents

| Agent | Core Responsibility | Tools Available | Structured Output |
| :--- | :--- | :--- | :--- |
| **1. Orchestrator** | Coordinates the investigation lifecycle. Breaks down alerts, delegates tasks, and re-plans when the Critic requests targeted follow-ups. | None (Meta-coordinator) | `active_tasks`: List of `InvestigationTask` with tool params. |
| **2. Observability** | Investigates log streams and time-series metrics. Detects statistical anomalies (P99 latency spikes, error rate jumps). | `query_logs`, `query_metrics` | Structured `EvidenceItem(type=FACT)` with level and stack traces. |
| **3. Dependency** | Inspects code releases, configuration diffs, upstream/downstream service graphs, and historical postmortems. | `query_deployments`, `query_service_topology`, `query_historical_incidents` | Verified deployment config diffs and downstream health states. |
| **4. Reasoning** | Synthesizes findings across Observability and Dependency streams to generate 2–3 competing hypotheses with calibrated confidence. | None (Synthesis Engine) | `hypotheses`: Ranked `Hypothesis` list with supporting and contradicting evidence IDs. |
| **5. Critic (Auditor)** | Adversarial auditor that prevents confirmation bias. Checks if claims are grounded in telemetry or rely on unverified assumptions. | None (Verification Engine) | `CriticVerdict`: `APPROVED`, `REQUEST_MORE_EVIDENCE`, or `INCONCLUSIVE`. |
| **6. Reporting** | Assembles the authoritative Root Cause Analysis (RCA) report, distinguishing verified facts from assumptions. | None (Presentation Engine) | `IncidentReport`: Executive summary, ranked hypotheses, facts table, and P0/P1 actions. |

---

## 3. Agent Coordination, Shared State & Concurrent Reducers

### Typed Blackboard Architecture
Agents communicate through a shared `InvestigationState` (`TypedDict`). To support **true parallel execution** without race conditions, concurrent branches write through `operator.add` reducers:

```python
class InvestigationState(TypedDict, total=False):
    incident_ticket: IncidentTicket
    current_iteration: int
    max_iterations: int
    active_tasks: List[InvestigationTask]
    completed_tasks: Annotated[List[InvestigationTask], operator.add]
    evidence_store: Annotated[List[EvidenceItem], operator.add]  # Thread-safe fan-in
    hypotheses: List[Hypothesis]
    critic_verdict: Optional[CriticVerdict]
    final_report: Optional[IncidentReport]
    total_tokens_used: Annotated[int, operator.add]
    total_tool_calls: Annotated[int, operator.add]
    tool_failure_events: Annotated[List[str], operator.add]
```

### Parallel Execution (Fan-Out & Fan-In)
When the `Orchestrator` generates the initial task list:
1. **Fan-Out**: LangGraph dispatches execution simultaneously to both the `Observability` and `Dependency` nodes.
2. **Independent Tool Calling**: The Observability agent queries logs and metrics while the Dependency agent queries deployments and service topologies.
3. **Fan-In**: LangGraph's channel reducers automatically merge evidence items into `evidence_store` before invoking the `Reasoning` node.

---

## 4. Feedback Loops & Dynamic Termination

Unlike linear pipelines, this system supports **stateful cyclic iteration**:
1. If the `Critic` detects that telemetry is unbalanced (e.g. error logs exist, but nobody checked for a recent config change) and `iteration < max_iterations`:
   - The Critic issues `REQUEST_MORE_EVIDENCE` with specific follow-up questions.
   - The conditional graph router routes the flow back to `Orchestrator`.
   - The Orchestrator schedules targeted tasks to fill the missing gaps.
2. **Termination Conditions**:
   - **`APPROVED`**: Hypotheses are grounded in verified telemetry facts and cross-examined.
   - **`INCONCLUSIVE`**: Telemetry is completely missing or corrupted (e.g. Scenario 10); stops guessing to prevent hallucinations.
   - **`MAX_ITERATIONS`**: Hard guardrail (default: 3 iterations) guarantees termination and prevents infinite loops.

---

## 5. Fault Tolerance & Chaos Recovery

Production telemetry tools frequently fail. The tool execution layer includes a **Chaos Simulator** (`src/tools/chaos.py`) that tests resilience against:
- **`ToolTimeoutError`**: Centralized log clusters timing out after 30s.
- **`ToolRateLimitError`**: HTTP 429 backoff handling.
- **`Truncated Results`**: Partial observations requiring filter refinement.

**Recovery Mechanism**: When a tool fails, the specialist agent logs a `tool_failure_event` into state and continues investigating using alternate data sources (e.g., if logs time out in Scenario 7, the system reconstructs the root cause using metrics anomalies and deployment history).
