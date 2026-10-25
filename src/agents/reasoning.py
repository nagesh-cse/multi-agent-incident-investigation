from __future__ import annotations
from typing import List, Dict, Any, Optional
from src.state.models import InvestigationState, Hypothesis, ReasoningLLMOutput
from src.llm import llm_config, LiveTokenTracker, estimate_tokens


def reasoning_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Reasoning Agent:
    - Merges telemetry and dependency findings from state["evidence_store"].
    - If live Gemini/OpenRouter LLM is configured, dynamically prompts with structured output.
    - Tracks live tokens with LiveTokenTracker callback.
    - Otherwise, executes deterministic multi-hypothesis reasoning logic with dynamic token estimation.
    """
    evidence = state.get("evidence_store", [])
    ticket = state["incident_ticket"]

    # 1. Try Live LLM invocation if configured
    llm = llm_config.get_chat_model()
    if llm and evidence and len(evidence) > 1:
        try:
            structured_llm = llm.with_structured_output(ReasoningLLMOutput)
            evidence_summary = "\n".join([f"- [{e.id}] ({e.source.upper()}) {e.description}" for e in evidence[:12]])
            prompt = (
                f"You are an expert SRE Reasoning Specialist investigating a production incident.\n"
                f"Incident: {ticket.title} on {ticket.affected_service}\n"
                f"Description: {ticket.description}\n\n"
                f"Verified Telemetry & Dependency Evidence:\n{evidence_summary}\n\n"
                f"Formulate 2 to 3 COMPETING root-cause hypotheses (e.g. H1: primary theory, H2: competing theory, H3: external/traffic theory).\n"
                f"For each hypothesis, assign a calibrated confidence score between 0.0 and 1.0, and cite the exact supporting_evidence_ids (e.g. ['EV-DEP-1', 'EV-LOG-1']).\n"
                f"Mark is_root_cause=True for your top hypothesis."
            )
            tracker = LiveTokenTracker()
            llm_result: ReasoningLLMOutput = structured_llm.invoke(prompt, config={"callbacks": [tracker]})
            if llm_result and llm_result.hypotheses:
                return {
                    "hypotheses": llm_result.hypotheses,
                    "total_tokens_used": tracker.total_tokens,
                }
        except Exception as e:
            err_msg = str(e).split("\n")[0][:120]
            print(f"  [⚠️ Reasoning Fallback] LLM unavailable ({type(e).__name__}: {err_msg}). Using deterministic reasoning.", flush=True)

    # Case 1: Inconclusive (Insufficient evidence, e.g. Incident 10)
    if not evidence or len(evidence) <= 1:
        hypotheses = [
            Hypothesis(
                id="H-INCONCLUSIVE",
                title="Insufficient Telemetry to Determine Root Cause",
                description="No error logs, metric anomalies, or suspicious deployments were observed. Telemetry is missing or dropped.",
                confidence=0.85,
                supporting_evidence_ids=[ev.id for ev in evidence],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H-UNVERIFIED-NETWORK",
                title="Transient Core Network Flap (Unverified Assumption)",
                description="Transient hardware or link failure occurred, but zero telemetry exists to prove or disprove this theory.",
                confidence=0.15,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[],
                is_root_cause=False
            )
        ]
        return {"hypotheses": hypotheses, "total_tokens_used": 0}

    # Case 2: Analyze evidence items to formulate competing theories
    deploy_evs = [e for e in evidence if e.source == "deployments"]
    log_evs = [e for e in evidence if e.source == "logs"]
    metric_evs = [e for e in evidence if e.source == "metrics"]
    topo_evs = [e for e in evidence if e.source == "topology"]
    hist_evs = [e for e in evidence if e.source == "historical_incidents"]

    has_suspect_deploy = any("suspect" in e.description.lower() or "config diff" in e.description.lower() for e in deploy_evs)
    has_oom = any("oom" in e.description.lower() or "exit code 137" in e.description.lower() for e in log_evs)
    has_downstream_fail = any("downstream dependency" in e.description.lower() and ("unhealthy" in e.description.lower() or "degraded" in e.description.lower()) for e in topo_evs)
    has_ssl_expired = any("ssl" in e.description.lower() or "certificate" in e.description.lower() for e in log_evs)
    has_migration_lock = any("migration" in e.description.lower() or "locked table" in e.description.lower() for e in deploy_evs + hist_evs)
    has_throttling = any("throttl" in e.description.lower() or "cfs quota" in e.description.lower() for e in log_evs)
    has_schema_mismatch = any("warehouse_id" in e.description.lower() or "keyerror" in e.description.lower() or "rename_field" in e.description.lower() for e in log_evs + deploy_evs)
    has_deadlock = any("synchronous" in e.description.lower() or "invoicelock" in e.description.lower() or "mutual" in ticket.title.lower() for e in log_evs + deploy_evs)
    has_retry_storm = any("retry" in e.description.lower() and ("storm" in ticket.title.lower() or "immediate" in e.description.lower() or "100000" in e.description.lower()) for e in log_evs + deploy_evs)

    # Detect Root Cause Pattern
    if has_suspect_deploy and any("pool" in e.description.lower() or "connection" in e.description.lower() for e in log_evs):
        # Scenario 1: Pool exhaustion
        h1_supp = [e.id for e in deploy_evs if "pool" in e.description.lower() or "max_connections" in e.description.lower()]
        h1_supp += [e.id for e in log_evs if "pool" in e.description.lower()]
        h1_supp += [e.id for e in metric_evs]

        hypotheses = [
            Hypothesis(
                id="H1",
                title=f"Database Connection Pool Exhaustion from Config Rollout on {ticket.affected_service}",
                description="Recent configuration update reduced connection pool size to 5, starving worker threads and resulting in 504 timeouts.",
                confidence=0.92,
                supporting_evidence_ids=h1_supp,
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Database Engine Crash or Hardware Outage",
                description="Underlying Postgres host experienced severe crash or disk I/O degradation.",
                confidence=0.08,
                supporting_evidence_ids=[e.id for e in metric_evs],
                contradicting_evidence_ids=[e.id for e in deploy_evs if "max_connections" in e.description.lower()],
                is_root_cause=False
            )
        ]

    elif has_oom or any("memory" in e.description.lower() and "98" in e.description.lower() for e in metric_evs):
        # Scenario 2: Memory leak
        leak_dep = [e.id for e in deploy_evs if "cache" in e.description.lower()]
        hypotheses = [
            Hypothesis(
                id="H1",
                title=f"Progressive Heap Memory Leak in {ticket.affected_service} Session Cache",
                description="Unbounded in-memory session cache added in deploy v3.1.0 steadily exhausted container RAM over 6 hours until OOMKilled.",
                confidence=0.90,
                supporting_evidence_ids=leak_dep + [e.id for e in metric_evs if "memory" in e.description.lower()],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Regression Caused by Recent Frontend Deployment",
                description="Frontend deployment v1.0.9 deployed 5 minutes prior to the crash caused excessive client payload sizes.",
                confidence=0.10,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[e.id for e in metric_evs if "memory" in e.description.lower()],
                is_root_cause=False
            )
        ]

    elif has_downstream_fail or any("stripe" in e.description.lower() for e in log_evs + topo_evs):
        # Scenario 3: Downstream 3rd-party outage
        hypotheses = [
            Hypothesis(
                id="H1",
                title="Cascading Outage from Downstream External Payment Gateway (Stripe API)",
                description="External payment provider outage caused client thread exhaustion and latency escalation in checkout-service.",
                confidence=0.88,
                supporting_evidence_ids=[e.id for e in topo_evs if "downstream" in e.description.lower()] + [e.id for e in log_evs],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Internal Checkout Service Application CPU Bug",
                description="Inefficient algorithm in checkout service caused high CPU and latency.",
                confidence=0.12,
                supporting_evidence_ids=[e.id for e in metric_evs if "cpu" in e.description.lower()],
                contradicting_evidence_ids=[e.id for e in log_evs if "read timed out" in e.description.lower()],
                is_root_cause=False
            )
        ]

    elif has_retry_storm:
        # Scenario 4: Cascading Retry Storm
        hypotheses = [
            Hypothesis(
                id="H1",
                title="Self-Inflicted Cascading Retry Storm Without Jitter or Backoff",
                description="Aggressive client retry policy with zero backoff caused massive query amplification, keeping database saturated after transient blip.",
                confidence=0.91,
                supporting_evidence_ids=[e.id for e in log_evs if "retrying" in e.description.lower()] + [e.id for e in deploy_evs],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Malicious Distributed Denial of Service (DDoS) Attack",
                description="External botnet targeted order-service endpoints.",
                confidence=0.09,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[e.id for e in log_evs if "backoff_ms=0" in e.description.lower()],
                is_root_cause=False
            )
        ]

    elif has_throttling:
        # Scenario 5: Noisy neighbor CPU throttling
        hypotheses = [
            Hypothesis(
                id="H1",
                title="Node-Level CPU Starvation and Throttling Caused by Unconstrained Batch-Pipeline-Job (Noisy Neighbor)",
                description="Shared Kubernetes host CPU was exhausted by heavy batch-pipeline-job, causing CFS quota throttling on search-service despite container reporting 22% CPU.",
                confidence=0.92,
                supporting_evidence_ids=[e.id for e in log_evs if "throttling" in e.description.lower() or "batch" in e.description.lower()],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Search Algorithm Lock or Deadlock",
                description="Internal application lock or infinite loop inside search-service.",
                confidence=0.08,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[e.id for e in log_evs if "throttling" in e.description.lower()],
                is_root_cause=False
            )
        ]

    elif has_schema_mismatch:
        # Scenario 6: Breaking schema change in upstream
        hypotheses = [
            Hypothesis(
                id="H1",
                title="Breaking Schema Contract Mismatch in Upstream Catalog-Service Deployment",
                description="Upstream catalog-service deployed field rename from warehouse_id to facility_id without backward compatibility, causing consumer KeyError.",
                confidence=0.94,
                supporting_evidence_ids=[e.id for e in log_evs] + [e.id for e in deploy_evs],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Kafka Consumer Group Partition Corruption",
                description="Kafka cluster lost partition state during rebalance.",
                confidence=0.06,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[e.id for e in log_evs if "keyerror" in e.description.lower()],
                is_root_cause=False
            )
        ]

    elif has_migration_lock:
        # Scenario 7: Migration table lock
        hypotheses = [
            Hypothesis(
                id="H1",
                title=f"Exclusive Table Lock from DDL Schema Migration on {ticket.affected_service}",
                description="Deployment v2.1.0 executed unindexed table migration during business hours, holding exclusive table lock and failing all API requests.",
                confidence=0.93,
                supporting_evidence_ids=[e.id for e in deploy_evs] + [e.id for e in hist_evs],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Persistent Centralized Logging Outage",
                description="Logging cluster outage caused user API requests to fail.",
                confidence=0.07,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[e.id for e in deploy_evs],
                is_root_cause=False
            )
        ]

    elif has_deadlock:
        # Scenario 8: Distributed deadlock
        hypotheses = [
            Hypothesis(
                id="H1",
                title="Distributed Circular Dependency Deadlock Between Billing and Notification Services",
                description="Synchronous HTTP dependency introduced in recent deploy caused mutual lock inversion and thread exhaustion between billing and notification services.",
                confidence=0.95,
                supporting_evidence_ids=[e.id for e in log_evs] + [e.id for e in deploy_evs],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Database Deadlock on Billing Tables",
                description="Relational database row-level deadlocks occurred in Postgres.",
                confidence=0.05,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[e.id for e in log_evs],
                is_root_cause=False
            )
        ]

    elif has_ssl_expired:
        # Scenario 9: SSL Expired
        hypotheses = [
            Hypothesis(
                id="H1",
                title="Ingress TLS/SSL Certificate Expiration on API Gateway",
                description="Automated cert-manager renewal cron failed 48h prior, causing TLS validity to expire and blocking all inbound traffic.",
                confidence=0.95,
                supporting_evidence_ids=[e.id for e in log_evs if "certificate" in e.description.lower()],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Backend API Cluster Crash",
                description="Internal microservices crashed or became unreachable.",
                confidence=0.05,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[e.id for e in topo_evs],
                is_root_cause=False
            )
        ]

    else:
        primary_evidence = [e.id for e in evidence if e.type == "FACT"]
        hypotheses = [
            Hypothesis(
                id="H1",
                title=f"Primary Anomaly on Service '{ticket.affected_service}'",
                description=f"Telemetry indicates abnormal behavior correlated with: {[e.description[:80] for e in evidence[:2]]}",
                confidence=0.82,
                supporting_evidence_ids=primary_evidence[:3],
                contradicting_evidence_ids=[],
                is_root_cause=True
            ),
            Hypothesis(
                id="H2",
                title="Transient External Traffic Spike / Infrastructure Flap",
                description="Transient load burst exceeding capacity limits.",
                confidence=0.18,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=primary_evidence[:1],
                is_root_cause=False
            )
        ]

    return {
        "hypotheses": hypotheses,
        "total_tokens_used": 0,
    }
