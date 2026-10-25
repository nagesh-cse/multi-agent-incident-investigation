"""
Generator and loader for the 10 synthetic production incident scenarios.
Each scenario includes:
- incident_ticket details
- ground_truth metadata (true root cause, key facts, distractors)
- simulated logs, metrics, deployments, topology, historical incidents
- chaos_rules for simulated tool failures
"""
from __future__ import annotations
import json
import os
from typing import Dict, Any, List

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "synthetic_incidents")


def build_scenario_01() -> Dict[str, Any]:
    """Scenario 1: Bad Configuration Rollout (DB Connection Pool Exhaustion)"""
    return {
        "incident_id": "INC-01",
        "title": "Payment Service 504 Gateway Timeout Spike",
        "description": "Payment transactions failing with 504 Gateway Timeout. Checkout conversion dropped 40% in the last 15 minutes.",
        "affected_service": "payment-service",
        "timestamp": "2026-10-24T14:15:00Z",
        "severity": "CRITICAL",
        "initial_symptoms": ["504 Gateway Timeout", "High latency on /charge endpoint"],
        "ground_truth": {
            "root_cause_summary": "Database connection pool exhaustion caused by a configuration change reducing max_connections from 100 to 5.",
            "culprit_service": "payment-service",
            "key_evidence": [
                "Deployment commit 'Tune pool size' lowered max_connections to 5 at 13:50 UTC",
                "Logs at 14:05 UTC show DBConnectionError: connection pool exhausted",
                "Error rate 5xx jumped from 0.01 to 0.45 at 14:05 UTC"
            ],
            "distractors": [
                "DNS lookup warning in auth-service logs at 14:00 UTC (benign)"
            ]
        },
        "logs": [
            {"timestamp": "2026-10-24T13:45:00Z", "level": "INFO", "service": "payment-service", "message": "Worker pool healthy with 50 workers"},
            {"timestamp": "2026-10-24T14:00:00Z", "level": "WARN", "service": "auth-service", "message": "DNS lookup took 45ms for ldap.corp.internal"},
            {"timestamp": "2026-10-24T14:05:12Z", "level": "ERROR", "service": "payment-service", "message": "Timeout waiting for available connection in pool", "exception": "DBPoolTimeoutException: pool exhausted after 30000ms (max=5, in_use=5)"},
            {"timestamp": "2026-10-24T14:08:30Z", "level": "ERROR", "service": "payment-service", "message": "Transaction failed: DB connection acquired timeout", "exception": "DBPoolTimeoutException: pool exhausted after 30000ms (max=5, in_use=5)"},
            {"timestamp": "2026-10-24T14:12:00Z", "level": "ERROR", "service": "payment-service", "message": "HTTP 504 dispatched to gateway for trace_id=tx_9921", "exception": "GatewayTimeout"}
        ],
        "metrics": {
            "payment-service": {
                "error_rate_5xx": [
                    {"timestamp": "2026-10-24T13:40:00Z", "value": 0.005},
                    {"timestamp": "2026-10-24T13:50:00Z", "value": 0.008},
                    {"timestamp": "2026-10-24T14:05:00Z", "value": 0.350},
                    {"timestamp": "2026-10-24T14:15:00Z", "value": 0.480}
                ],
                "latency_p99": [
                    {"timestamp": "2026-10-24T13:40:00Z", "value": 110.0},
                    {"timestamp": "2026-10-24T13:50:00Z", "value": 125.0},
                    {"timestamp": "2026-10-24T14:05:00Z", "value": 4800.0},
                    {"timestamp": "2026-10-24T14:15:00Z", "value": 6200.0}
                ]
            }
        },
        "deployments": {
            "payment-service": [
                {
                    "timestamp": "2026-10-24T13:50:00Z",
                    "version_tag": "v2.8.4",
                    "author": "sre_alex@orange.com",
                    "commit_message": "Tune pool size for cost reduction",
                    "config_diff": {"max_connections": 5, "previous_max_connections": 100},
                    "is_suspect": True
                }
            ]
        },
        "topology": {
            "payment-service": {
                "service_type": "api_service",
                "health_status": "DEGRADED",
                "upstream": ["api-gateway", "checkout-service"],
                "downstream": ["postgres-payment-db", "stripe-api"],
                "config_summary": {"max_db_connections": 5, "min_replicas": 4}
            }
        },
        "historical_incidents": [
            {
                "incident_id": "INC-PREV-201",
                "service": "payment-service",
                "title": "Payment gateway connection starvation",
                "date": "2025-06-11",
                "root_cause": "Database connection pool size was set below peak concurrency requirement.",
                "mitigation": "Increase max_connections to at least 80 and set connection acquisition timeout."
            }
        ],
        "chaos_rules": {}
    }


def build_scenario_02() -> Dict[str, Any]:
    """Scenario 2: Slow Memory Leak (6-hour accumulation, red herring recent deploy)"""
    return {
        "incident_id": "INC-02",
        "title": "Auth Service Worker Pods Crashing (OOMKilled)",
        "description": "Auth-service pods are crashing cyclically with exit code 137 (OOMKilled). User sign-ins failing intermittently.",
        "affected_service": "auth-service",
        "timestamp": "2026-10-24T16:00:00Z",
        "severity": "CRITICAL",
        "initial_symptoms": ["Pod restarts", "Exit code 137", "Intermittent 502 Bad Gateway"],
        "ground_truth": {
            "root_cause_summary": "Unbounded session cache memory leak introduced in deploy v3.1.0 (deployed 6 hours ago), causing RSS memory to steadily climb until hitting the 2GB container limit.",
            "culprit_service": "auth-service",
            "key_evidence": [
                "Memory metric shows steady linear upward trend from 25% at 10:00 UTC to 98% at 15:50 UTC",
                "Deploy v3.1.0 deployed at 10:00 UTC with commit 'Add in-memory user session cache'",
                "Logs show OutOfMemory / cgroup killer invocation"
            ],
            "distractors": [
                "Minor frontend static asset deploy at 15:52 UTC (v1.0.9 by web_team) right before pod crash"
            ]
        },
        "logs": [
            {"timestamp": "2026-10-24T10:05:00Z", "level": "INFO", "service": "auth-service", "message": "v3.1.0 initialized session cache with TTL=0 (unbounded)"},
            {"timestamp": "2026-10-24T15:52:00Z", "level": "INFO", "service": "web-frontend", "message": "Deployed frontend v1.0.9: updated button color"},
            {"timestamp": "2026-10-24T15:55:10Z", "level": "WARN", "service": "auth-service", "message": "Memory utilization exceeded 92% (1840MB/2000MB)"},
            {"timestamp": "2026-10-24T15:58:44Z", "level": "FATAL", "service": "auth-service", "message": "Container killed by kernel: OOMKilled cgroups limit reached", "exception": "KernelOOMExitCode137"}
        ],
        "metrics": {
            "auth-service": {
                "memory": [
                    {"timestamp": "2026-10-24T10:00:00Z", "value": 24.5},
                    {"timestamp": "2026-10-24T12:00:00Z", "value": 52.0},
                    {"timestamp": "2026-10-24T14:00:00Z", "value": 78.4},
                    {"timestamp": "2026-10-24T15:50:00Z", "value": 98.2}
                ],
                "cpu": [
                    {"timestamp": "2026-10-24T10:00:00Z", "value": 15.0},
                    {"timestamp": "2026-10-24T15:50:00Z", "value": 18.0}
                ]
            }
        },
        "deployments": {
            "auth-service": [
                {
                    "timestamp": "2026-10-24T10:00:00Z",
                    "version_tag": "v3.1.0",
                    "author": "backend_dave@orange.com",
                    "commit_message": "Add in-memory user session cache without eviction policy",
                    "config_diff": {"cache_enabled": True, "cache_max_size": "unlimited"},
                    "is_suspect": True
                }
            ],
            "web-frontend": [
                {
                    "timestamp": "2026-10-24T15:52:00Z",
                    "version_tag": "v1.0.9",
                    "author": "ui_sarah@orange.com",
                    "commit_message": "Change checkout button color to blue",
                    "config_diff": {},
                    "is_suspect": False
                }
            ]
        },
        "topology": {
            "auth-service": {
                "service_type": "api_service",
                "health_status": "UNHEALTHY",
                "upstream": ["api-gateway"],
                "downstream": ["redis-sessions", "postgres-user-db"],
                "config_summary": {"container_mem_limit": "2048Mi", "restart_policy": "Always"}
            }
        },
        "historical_incidents": [],
        "chaos_rules": {}
    }


def build_scenario_03() -> Dict[str, Any]:
    """Scenario 3: Downstream 3rd-Party Outage (External Payment Gateway)"""
    return {
        "incident_id": "INC-03",
        "title": "Checkout Service High P99 Latency & Connection Pileup",
        "description": "Checkout service latency spiked to 35 seconds. Thread pools are exhausted and CPU is at 95% due to thread contention.",
        "affected_service": "checkout-service",
        "timestamp": "2026-10-24T17:30:00Z",
        "severity": "HIGH",
        "initial_symptoms": ["P99 latency > 30s", "Thread starvation in checkout-service"],
        "ground_truth": {
            "root_cause_summary": "Downstream external payment provider (Stripe API) experiencing major service outage; lack of timeout and circuit breaker in checkout-service caused thread exhaustion.",
            "culprit_service": "external-stripe-api",
            "key_evidence": [
                "Service topology shows checkout-service depends on external 'stripe-api'",
                "Topology downstream health shows stripe-api status as 'UNHEALTHY'",
                "Logs show read timeouts when contacting https://api.stripe.com/v1/charges",
                "No deployments to checkout-service in past 72 hours"
            ],
            "distractors": [
                "CPU usage on checkout-service is 95% (symptom of thread contention, not the cause)"
            ]
        },
        "logs": [
            {"timestamp": "2026-10-24T17:15:20Z", "level": "WARN", "service": "checkout-service", "message": "Slow response from payment provider: 28400ms for charge_req_81"},
            {"timestamp": "2026-10-24T17:20:00Z", "level": "ERROR", "service": "checkout-service", "message": "Read timed out connecting to https://api.stripe.com/v1/charges", "exception": "SocketTimeoutException: Read timed out after 30000ms"},
            {"timestamp": "2026-10-24T17:25:00Z", "level": "ERROR", "service": "checkout-service", "message": "Worker thread pool reached 100% capacity (500/500 threads blocked)"}
        ],
        "metrics": {
            "checkout-service": {
                "latency_p99": [
                    {"timestamp": "2026-10-24T17:00:00Z", "value": 180.0},
                    {"timestamp": "2026-10-24T17:20:00Z", "value": 31000.0},
                    {"timestamp": "2026-10-24T17:30:00Z", "value": 35000.0}
                ],
                "cpu": [
                    {"timestamp": "2026-10-24T17:00:00Z", "value": 20.0},
                    {"timestamp": "2026-10-24T17:25:00Z", "value": 95.0}
                ]
            }
        },
        "deployments": {
            "checkout-service": []
        },
        "topology": {
            "checkout-service": {
                "service_type": "api_service",
                "health_status": "DEGRADED",
                "upstream": ["api-gateway"],
                "downstream": ["inventory-service", "stripe-api"],
                "config_summary": {"http_timeout_ms": 30000, "circuit_breaker_enabled": False}
            },
            "stripe-api": {
                "service_type": "external_api",
                "health_status": "UNHEALTHY",
                "upstream": ["checkout-service"],
                "downstream": [],
                "config_summary": {"provider": "Stripe US-East"}
            }
        },
        "historical_incidents": [],
        "chaos_rules": {}
    }


def build_scenario_04() -> Dict[str, Any]:
    """Scenario 4: Cascading Retry Storm (Lack of backoff/jitter after brief blip)"""
    return {
        "incident_id": "INC-04",
        "title": "Persistent Database Overload After Brief Network Glitch",
        "description": "A 5-second network partition occurred and recovered 30 minutes ago, but order-service and database remain completely overwhelmed with 100k queries/sec.",
        "affected_service": "order-service",
        "timestamp": "2026-10-24T18:00:00Z",
        "severity": "CRITICAL",
        "initial_symptoms": ["100k queries/sec hitting db", "Massive request queues"],
        "ground_truth": {
            "root_cause_summary": "Clients and upstream services lack exponential backoff and jitter, creating a self-inflicted retry storm that keeps the database saturated after a transient blip.",
            "culprit_service": "order-service",
            "key_evidence": [
                "Logs show repetitive immediate retries with retry_count=15 without backoff delay",
                "Network metrics show the underlying network glitch lasted only from 17:29 to 17:30 UTC",
                "Topology config shows client_retry_policy: 'IMMEDIATE_NO_BACKOFF'"
            ],
            "distractors": [
                "Suspicion of external DDoS attack due to high traffic volume"
            ]
        },
        "logs": [
            {"timestamp": "2026-10-24T17:29:50Z", "level": "WARN", "service": "order-service", "message": "Transient network connection reset by peer"},
            {"timestamp": "2026-10-24T17:30:10Z", "level": "INFO", "service": "network", "message": "Switch port flap resolved, network latency normalized to 0.4ms"},
            {"timestamp": "2026-10-24T17:35:00Z", "level": "ERROR", "service": "order-service", "message": "Client retrying immediately (retry_count=18, backoff_ms=0)"},
            {"timestamp": "2026-10-24T17:45:00Z", "level": "ERROR", "service": "order-service", "message": "Database thread queue full: 100000 queued requests"}
        ],
        "metrics": {
            "order-service": {
                "error_rate_5xx": [
                    {"timestamp": "2026-10-24T17:25:00Z", "value": 0.001},
                    {"timestamp": "2026-10-24T17:30:00Z", "value": 0.850},
                    {"timestamp": "2026-10-24T18:00:00Z", "value": 0.720}
                ]
            }
        },
        "deployments": {
            "order-service": [
                {
                    "timestamp": "2026-10-24T12:00:00Z",
                    "version_tag": "v1.4.0",
                    "author": "lead_eng@orange.com",
                    "commit_message": "Aggressive retry policy for mobile clients",
                    "config_diff": {"retry_policy": "IMMEDIATE", "max_retries": 25, "backoff": "none"},
                    "is_suspect": True
                }
            ]
        },
        "topology": {
            "order-service": {
                "service_type": "api_service",
                "health_status": "DEGRADED",
                "upstream": ["mobile-app", "web-gateway"],
                "downstream": ["postgres-order-db"],
                "config_summary": {"retry_jitter": False, "backoff_multiplier": 1.0}
            }
        },
        "historical_incidents": [],
        "chaos_rules": {}
    }


def build_scenario_05() -> Dict[str, Any]:
    """Scenario 5: Noisy Neighbor / CPU Throttling on Shared Host"""
    return {
        "incident_id": "INC-05",
        "title": "Search Service Response Degradation on Node k8s-worker-12",
        "description": "Search queries taking 5,000ms instead of 80ms on worker node 12. Search container CPU is only 22%, but container is being severely throttled.",
        "affected_service": "search-service",
        "timestamp": "2026-10-24T19:00:00Z",
        "severity": "MEDIUM",
        "initial_symptoms": ["Query latency 10x higher", "Zero application error logs"],
        "ground_truth": {
            "root_cause_summary": "Kubernetes node CPU starvation caused by an unconstrained batch data-pipeline job scheduled on the same host (noisy neighbor).",
            "culprit_service": "batch-pipeline-job",
            "key_evidence": [
                "Node-level metrics show host CPU at 100%",
                "search-service container throttled percentage at 88%",
                "Zero application exceptions in search-service logs"
            ],
            "distractors": [
                "Internal search-service CPU metric reports 22% (looks underutilized, leading engineers to suspect algorithmic lock)"
            ]
        },
        "logs": [
            {"timestamp": "2026-10-24T18:40:00Z", "level": "INFO", "service": "search-service", "message": "Search index loaded, 4.2M documents"},
            {"timestamp": "2026-10-24T18:50:00Z", "level": "WARN", "service": "k8s-kubelet", "message": "CFS quota throttling search-service: 88% of execution periods throttled"},
            {"timestamp": "2026-10-24T18:52:00Z", "level": "INFO", "service": "batch-pipeline-job", "message": "Heavy video transcoding batch job started on node k8s-worker-12 without cpu_limit"}
        ],
        "metrics": {
            "search-service": {
                "cpu": [
                    {"timestamp": "2026-10-24T18:30:00Z", "value": 20.0},
                    {"timestamp": "2026-10-24T19:00:00Z", "value": 22.0}
                ],
                "latency_p99": [
                    {"timestamp": "2026-10-24T18:30:00Z", "value": 85.0},
                    {"timestamp": "2026-10-24T19:00:00Z", "value": 5200.0}
                ]
            }
        },
        "deployments": {
            "search-service": []
        },
        "topology": {
            "search-service": {
                "service_type": "api_service",
                "health_status": "DEGRADED",
                "upstream": ["web-gateway"],
                "downstream": ["elasticsearch-cluster"],
                "config_summary": {"node_affinity": "k8s-worker-12", "cpu_limit": "2000m"}
            }
        },
        "historical_incidents": [],
        "chaos_rules": {}
    }


def build_scenario_06() -> Dict[str, Any]:
    """Scenario 6: Schema Contract Mismatch Between Services"""
    return {
        "incident_id": "INC-06",
        "title": "Inventory Service Crashing on Message Consumption",
        "description": "Inventory-service dead-letter queue is filling rapidly with unparseable messages from Kafka topic 'catalog-events'.",
        "affected_service": "inventory-service",
        "timestamp": "2026-10-24T20:10:00Z",
        "severity": "HIGH",
        "initial_symptoms": ["Crash on message deserialize", "KeyError: 'warehouse_id'"],
        "ground_truth": {
            "root_cause_summary": "Breaking schema change in upstream catalog-service (v4.0.0) which renamed JSON key 'warehouse_id' to 'facility_id' without backward compatibility.",
            "culprit_service": "catalog-service",
            "key_evidence": [
                "catalog-service deployed v4.0.0 at 19:55 UTC with commit 'Refactor warehouse terminology to facility'",
                "inventory-service logs show KeyError: 'warehouse_id'",
                "Topology shows catalog-service produces to Kafka topic consumed by inventory-service"
            ],
            "distractors": [
                "Kafka broker reported a rebalance event at 19:58 UTC (normal rebalance)"
            ]
        },
        "logs": [
            {"timestamp": "2026-10-24T19:58:00Z", "level": "INFO", "service": "kafka-cluster", "message": "Consumer group 'inventory-group' rebalanced"},
            {"timestamp": "2026-10-24T20:01:10Z", "level": "ERROR", "service": "inventory-service", "message": "Failed to parse CatalogItemUpdated payload", "exception": "KeyError: 'warehouse_id' in record {'item_id': 991, 'facility_id': 'WH-EAST'}"},
            {"timestamp": "2026-10-24T20:05:00Z", "level": "ERROR", "service": "inventory-service", "message": "Routing message to dead-letter queue: DLQ-inventory-errors"}
        ],
        "metrics": {
            "inventory-service": {
                "error_rate_5xx": [
                    {"timestamp": "2026-10-24T19:50:00Z", "value": 0.00},
                    {"timestamp": "2026-10-24T20:05:00Z", "value": 0.95}
                ]
            }
        },
        "deployments": {
            "catalog-service": [
                {
                    "timestamp": "2026-10-24T19:55:00Z",
                    "version_tag": "v4.0.0",
                    "author": "catalog_dev@orange.com",
                    "commit_message": "Refactor warehouse terminology to facility",
                    "config_diff": {"schema_version": 2, "rename_field": "warehouse_id -> facility_id"},
                    "is_suspect": True
                }
            ],
            "inventory-service": []
        },
        "topology": {
            "inventory-service": {
                "service_type": "event_consumer",
                "health_status": "UNHEALTHY",
                "upstream": ["catalog-service (via Kafka)"],
                "downstream": ["inventory-db"],
                "config_summary": {"expected_schema": "v1"}
            }
        },
        "historical_incidents": [],
        "chaos_rules": {}
    }


def build_scenario_07() -> Dict[str, Any]:
    """Scenario 7: Telemetry Tool Failure (Resilience test: query_logs times out)"""
    return {
        "incident_id": "INC-07",
        "title": "User Profile Service Error Spike with Log Cluster Failure",
        "description": "User profile service errors spiked to 50%. The centralized Elasticsearch logging cluster is experiencing a major outage.",
        "affected_service": "user-profile-service",
        "timestamp": "2026-10-24T21:00:00Z",
        "severity": "HIGH",
        "initial_symptoms": ["500 Internal Server Error on /profile", "Logs query times out"],
        "ground_truth": {
            "root_cause_summary": "Bad deployment v2.1.0 introduced an invalid database migration; agent must diagnose the issue via metrics and deployment history because the logging tool experiences simulated timeout.",
            "culprit_service": "user-profile-service",
            "key_evidence": [
                "Deployment at 20:45 UTC with commit 'Apply user table migration without index'",
                "Metrics show error rate spiked to 50% exactly at 20:46 UTC",
                "Historical incident INC-882 documents identical postmortem"
            ],
            "distractors": [
                "Log service cluster outage raises ToolTimeoutError"
            ]
        },
        "logs": [],  # Simulated failure will trigger in chaos_rules
        "metrics": {
            "user-profile-service": {
                "error_rate_5xx": [
                    {"timestamp": "2026-10-24T20:40:00Z", "value": 0.01},
                    {"timestamp": "2026-10-24T20:46:00Z", "value": 0.52},
                    {"timestamp": "2026-10-24T21:00:00Z", "value": 0.51}
                ]
            }
        },
        "deployments": {
            "user-profile-service": [
                {
                    "timestamp": "2026-10-24T20:45:00Z",
                    "version_tag": "v2.1.0",
                    "author": "db_lead@orange.com",
                    "commit_message": "Apply user table migration without index (locked table)",
                    "config_diff": {"migration_script": "20261024_add_bio_column.sql"},
                    "is_suspect": True
                }
            ]
        },
        "topology": {
            "user-profile-service": {
                "service_type": "api_service",
                "health_status": "DEGRADED",
                "upstream": ["api-gateway"],
                "downstream": ["postgres-user-db"],
                "config_summary": {"table_lock_timeout": "5s"}
            }
        },
        "historical_incidents": [
            {
                "incident_id": "INC-882",
                "service": "user-profile-service",
                "title": "Table lock during schema migration",
                "date": "2025-09-01",
                "root_cause": "DDL migration executed during business hours locked user table, causing all writes to fail with 500.",
                "mitigation": "Kill lingering DDL transaction lock and apply migration concurrently."
            }
        ],
        "chaos_rules": {
            "query_logs": {
                "action": "timeout",
                "message": "Elasticsearch logging cluster unresponsive (timeout after 30000ms)"
            }
        }
    }


def build_scenario_08() -> Dict[str, Any]:
    """Scenario 8: Circular Dependency Distributed Deadlock"""
    return {
        "incident_id": "INC-08",
        "title": "Mutual Freeze Between Billing and Notification Services",
        "description": "Billing-service and notification-service have stopped processing requests. CPU and memory are completely flat, but all requests hang indefinitely.",
        "affected_service": "billing-service",
        "timestamp": "2026-10-24T21:30:00Z",
        "severity": "CRITICAL",
        "initial_symptoms": ["Zero throughput", "Hanging requests", "Zero CPU/memory usage"],
        "ground_truth": {
            "root_cause_summary": "Distributed circular lock deadlock: billing-service holds Lock A (invoice) and synchronously waits for notification-service, while notification-service holds Lock B (customer) and synchronously waits for billing-service.",
            "culprit_service": "billing-service",
            "key_evidence": [
                "Topology shows circular synchronous HTTP dependency between billing-service and notification-service",
                "Logs show billing waiting for notification ACK while notification waits for billing customer verification",
                "Deployments show recent change converted notification dispatch from asynchronous queue to synchronous HTTP call"
            ],
            "distractors": [
                "Metrics show 0% errors (requests don't fail, they just hang forever)"
            ]
        },
        "logs": [
            {"timestamp": "2026-10-24T21:10:00Z", "level": "INFO", "service": "billing-service", "message": "Acquired InvoiceLock:inv_402; calling notification-service /send synchronously"},
            {"timestamp": "2026-10-24T21:10:01Z", "level": "INFO", "service": "notification-service", "message": "Acquired CustomerLock:cust_99; calling billing-service /verify synchronously"},
            {"timestamp": "2026-10-24T21:15:00Z", "level": "WARN", "service": "billing-service", "message": "Thread pool saturation: 100% of threads in BLOCKED state waiting for downstream lock release"}
        ],
        "metrics": {
            "billing-service": {
                "latency_p99": [
                    {"timestamp": "2026-10-24T21:00:00Z", "value": 150.0},
                    {"timestamp": "2026-10-24T21:20:00Z", "value": 60000.0}
                ]
            }
        },
        "deployments": {
            "billing-service": [
                {
                    "timestamp": "2026-10-24T20:30:00Z",
                    "version_tag": "v3.0.1",
                    "author": "sync_dev@orange.com",
                    "commit_message": "Switch notification dispatch from RabbitMQ to direct synchronous HTTP client",
                    "config_diff": {"async_notifications": False},
                    "is_suspect": True
                }
            ]
        },
        "topology": {
            "billing-service": {
                "service_type": "api_service",
                "health_status": "DEGRADED",
                "upstream": ["checkout-service"],
                "downstream": ["notification-service"],
                "config_summary": {"sync_timeout_ms": 60000}
            },
            "notification-service": {
                "service_type": "api_service",
                "health_status": "DEGRADED",
                "upstream": ["billing-service"],
                "downstream": ["billing-service"],
                "config_summary": {"sync_timeout_ms": 60000}
            }
        },
        "historical_incidents": [],
        "chaos_rules": {}
    }


def build_scenario_09() -> Dict[str, Any]:
    """Scenario 9: Expired SSL / TLS Certificate"""
    return {
        "incident_id": "INC-09",
        "title": "Global Ingress SSL Handshake Failures",
        "description": "All mobile clients and browsers reporting SSL certificate expired on api.orange.com. All backend containers are completely healthy.",
        "affected_service": "api-gateway",
        "timestamp": "2026-10-24T22:00:00Z",
        "severity": "CRITICAL",
        "initial_symptoms": ["SSLHandshakeException", "Certificate expired error in clients"],
        "ground_truth": {
            "root_cause_summary": "TLS certificate expired on ingress gateway because automated cert-manager renewal cron job failed 48 hours ago due to DNS-01 challenge credentials failure.",
            "culprit_service": "api-gateway",
            "key_evidence": [
                "Gateway logs show SSL_ERROR_CERT_EXPIRED with validity ending 2026-10-24T21:59:00Z",
                "Topology shows api-gateway ingress TLS cert expiration timestamp in the past",
                "Zero recent code deployments to backend services"
            ],
            "distractors": [
                "Backend services show 100% health checks passing (because internal traffic bypasses public TLS)"
            ]
        },
        "logs": [
            {"timestamp": "2026-10-24T21:58:00Z", "level": "INFO", "service": "api-gateway", "message": "Inbound HTTPS connection established"},
            {"timestamp": "2026-10-24T22:00:01Z", "level": "ERROR", "service": "api-gateway", "message": "SSL Handshake Failed: Certificate expired at 2026-10-24T21:59:59Z", "exception": "SSLCertVerificationError: certificate has expired"},
            {"timestamp": "2026-10-24T22:05:00Z", "level": "ERROR", "service": "cert-manager", "message": "Automated renewal failed: Cloudflare API token invalid for DNS-01 challenge"}
        ],
        "metrics": {
            "api-gateway": {
                "error_rate_5xx": [
                    {"timestamp": "2026-10-24T21:50:00Z", "value": 0.00},
                    {"timestamp": "2026-10-24T22:05:00Z", "value": 0.99}
                ]
            }
        },
        "deployments": {
            "api-gateway": []
        },
        "topology": {
            "api-gateway": {
                "service_type": "ingress_gateway",
                "health_status": "UNHEALTHY",
                "upstream": ["public_internet"],
                "downstream": ["auth-service", "checkout-service", "payment-service"],
                "config_summary": {"tls_cert_expires": "2026-10-24T21:59:59Z"}
            }
        },
        "historical_incidents": [],
        "chaos_rules": {}
    }


def build_scenario_10() -> Dict[str, Any]:
    """Scenario 10: Dropped Telemetry / Insufficient Evidence (TRULY INCONCLUSIVE)"""
    return {
        "incident_id": "INC-10",
        "title": "Intermittent Micro-Dropouts on Core Network Router",
        "description": "User reports of intermittent disconnects over the past hour. The monitoring agent crashed and no metrics or logs were recorded.",
        "affected_service": "edge-router-core",
        "timestamp": "2026-10-24T23:00:00Z",
        "severity": "LOW",
        "initial_symptoms": ["Intermittent 502/504 reported by 3 users", "No logs recorded in system"],
        "ground_truth": {
            "root_cause_summary": "INCONCLUSIVE: Telemetry is completely missing due to telemetry agent crash; system must identify that facts are insufficient and output an Inconclusive verdict without hallucinating.",
            "culprit_service": "unknown",
            "key_evidence": [
                "Logs query returns 0 records",
                "Metrics query returns empty telemetry data",
                "No deployments recorded in the lookback window"
            ],
            "distractors": [
                "Unsubstantiated user theories on community forums"
            ]
        },
        "logs": [],
        "metrics": {
            "edge-router-core": {}
        },
        "deployments": {
            "edge-router-core": []
        },
        "topology": {
            "edge-router-core": {
                "service_type": "network_router",
                "health_status": "UNKNOWN",
                "upstream": [],
                "downstream": [],
                "config_summary": {"telemetry_agent_status": "CRASHED"}
            }
        },
        "historical_incidents": [],
        "chaos_rules": {}
    }


ALL_SCENARIOS = {
    "INC-01": build_scenario_01,
    "INC-02": build_scenario_02,
    "INC-03": build_scenario_03,
    "INC-04": build_scenario_04,
    "INC-05": build_scenario_05,
    "INC-06": build_scenario_06,
    "INC-07": build_scenario_07,
    "INC-08": build_scenario_08,
    "INC-09": build_scenario_09,
    "INC-10": build_scenario_10,
}


def dump_all_scenarios():
    """Generates and writes all 10 scenario JSON files to data/synthetic_incidents/"""
    os.makedirs(DATA_DIR, exist_ok=True)
    for inc_id, builder in ALL_SCENARIOS.items():
        data = builder()
        filepath = os.path.join(DATA_DIR, f"{inc_id.lower()}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def load_scenario(incident_id: str) -> Dict[str, Any]:
    """Loads a scenario by ID (e.g., 'INC-01' or 'inc-01') from disk, or builds it dynamically."""
    norm_id = incident_id.upper()
    filepath = os.path.join(DATA_DIR, f"{norm_id.lower()}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    if norm_id in ALL_SCENARIOS:
        return ALL_SCENARIOS[norm_id]()
    raise FileNotFoundError(f"Scenario '{incident_id}' not found.")


def list_scenarios() -> List[str]:
    """Returns list of all available incident IDs."""
    return list(ALL_SCENARIOS.keys())


if __name__ == "__main__":
    dump_all_scenarios()
    print(f"Successfully generated all {len(ALL_SCENARIOS)} synthetic incident scenarios in {DATA_DIR}!")
