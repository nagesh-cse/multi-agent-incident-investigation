# Technical Note: Multi-Agent Production Incident Investigation System

### Key Decisions
1. **LangGraph Cyclic State Machine**: We rejected static prompt chains in favor of a stateful, cyclic multi-agent graph. Chaining LLM calls cannot recover from dead ends or challenge premature conclusions. LangGraph allows dynamic routing, parallel task fan-out, and feedback loops.
2. **Separation of Facts from Assumptions**: Every evidence item is strictly typed. Telemetry directly returned by tools is marked `FACT`, while agent extrapolations are tagged `ASSUMPTION`. The Critic agent explicitly audits that the winning root-cause hypothesis is supported by verified facts, preventing speculative hallucinations.
3. **Specialized Division of Labor**: Splitting telemetry analysis (Observability) from topology/deployments (Dependency) mirrors how human SRE teams operate. It prevents context saturation and ensures configuration changes and downstream outages are evaluated alongside log stack traces.
4. **Adversarial Critic & Inconclusive Verdicts**: Rather than always forcing a guess, the Critic enforces an `INCONCLUSIVE` verdict when telemetry is absent (Scenario 10). This provides critical safety in production environments where hallucinations lead to wrong runbook actions.

### Trade-Offs
* **Token Overhead vs. Hallucination Resistance**: The multi-agent system consumes an average of 2,750 tokens per incident compared to 1,395 for the single-agent baseline. This 2x token investment represents the cost of collaborative debate, cross-examination, and validation. In exchange, root-cause accuracy rose from 40% to 100%, and evidence grounding increased from 19.2% to 93.3%.
* **Parallel Execution vs. Graph Complexity**: Executing Observability and Dependency agents concurrently requires typed state reducers (`operator.add`) to prevent race conditions during fan-in. This added engineering complexity, but enabled simultaneous retrieval across telemetry and topology.
* **Deterministic Guardrails vs. Open-Ended Agency**: To ensure bounded execution, we enforced strict iteration caps (max 3 cycles) and explicit task schemas. While this limits open-ended tool discovery, it guarantees deterministic termination within 0.1s offline and under 5s with live LLMs.

### Limitations
* **Simulated Telemetry Fixtures**: The current implementation operates over simulated in-memory fixtures. In an enterprise deployment, tools would interface with live REST/gRPC endpoints (Datadog, Prometheus, Elasticsearch, GitHub).
* **Predefined Anomaly Heuristics**: Metric anomaly detection uses baseline ratio thresholds (e.g. 2.5x above baseline, >5% error rate). In production, dynamic seasonal models (e.g. Prophet, Holt-Winters) are necessary to account for organic diurnal traffic variations.
* **Static Topology Definitions**: Topology queries currently inspect static service dependency graphs rather than dynamically tracing distributed OpenTelemetry spans (e.g. Jaeger/Tempo).

### Potential Improvements
1. **Direct OpenTelemetry / Jaeger Trace Ingestion**: Ingest live trace spans to automatically pinpoint slow service hops in the call tree.
2. **Automated Remediation Execution**: Connect the Reporting agent's recommended P0 actions to an automated approval gate (e.g., Slack webhook or ArgoCD rollback API) for one-click mitigation.
3. **Continuous Fine-Tuning on Past Postmortems**: Feed verified incident postmortems back into the historical index to improve future hypothesis scoring over time.
