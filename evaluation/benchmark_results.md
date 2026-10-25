# Evaluation & Benchmark Results: Multi-Agent vs Single-Agent Baseline

## Executive Summary
This evaluation tests both systems across **10 synthetic production incidents** featuring:
- Complex root causes (memory leaks, connection pool starvation, downstream timeouts, deadlocks)
- Deliberate traps and misleading evidence (benign DNS warnings, recent UI deploys)
- Simulated tool failures (timeouts on log queries)
- Truly inconclusive scenarios with missing telemetry

### Comparative Aggregate Metrics
| Metric                         | Multi-Agent System (LangGraph)    | Single-Agent Baseline           | Delta / Advantage                     |
|--------------------------------|-----------------------------------|---------------------------------|---------------------------------------|
| Root-Cause Accuracy (Top-1)    | 100.0%                            | 40.0%                           | +60.0% higher accuracy                |
| Evidence Grounding Score       | 93.3%                             | 19.2%                           | +74.2% more factual                   |
| Avg Tool Calls / Investigation | 8.4                               | 1.9                             | +6.5 deeper queries                   |
| Avg Token Consumption          | 2,750                             | 1,395                           | 1,355 tokens (collaborative overhead) |
| Handling Inconclusive (INC-10) | ✅ Correctly Declared Inconclusive | ❌ Hallucinated False Root Cause | Hallucination Resistant               |
| Tool Failure Recovery (INC-07) | ✅ Handled Timeout & Recovered     | ❌ Stalled Investigation         | Fault Tolerant                        |

---

## Detailed Per-Incident Benchmark
| Incident   | MA Correct?   | MA Grounding   |   MA Tools | MA Latency   |   MA Tokens | SA Correct?   | SA Grounding   |   SA Tools | SA Latency   |   SA Tokens |
|------------|---------------|----------------|------------|--------------|-------------|---------------|----------------|------------|--------------|-------------|
| INC-01     | ✅ YES         | 100.0%         |         10 | 0.01s        |        2750 | ✅ YES         | 66.7%          |          2 | 0.0s         |        1450 |
| INC-02     | ✅ YES         | 100.0%         |          9 | 0.01s        |        2750 | ❌ NO          | 33.3%          |          2 | 0.0s         |        1450 |
| INC-03     | ✅ YES         | 100.0%         |          9 | 0.01s        |        2750 | ❌ NO          | 25.0%          |          2 | 0.0s         |        1450 |
| INC-04     | ✅ YES         | 100.0%         |          9 | 0.01s        |        2750 | ✅ YES         | 33.3%          |          2 | 0.0s         |        1450 |
| INC-05     | ✅ YES         | 66.7%          |          8 | 0.01s        |        2750 | ❌ NO          | 0.0%           |          2 | 0.0s         |        1450 |
| INC-06     | ✅ YES         | 100.0%         |          8 | 0.01s        |        2750 | ❌ NO          | 0.0%           |          2 | 0.0s         |        1450 |
| INC-07     | ✅ YES         | 100.0%         |          7 | 0.01s        |        2750 | ❌ NO          | 33.3%          |          1 | 0.0s         |        1000 |
| INC-08     | ✅ YES         | 100.0%         |          8 | 0.01s        |        2750 | ✅ YES         | 0.0%           |          2 | 0.0s         |        1450 |
| INC-09     | ✅ YES         | 66.7%          |         10 | 0.01s        |        2750 | ✅ YES         | 0.0%           |          2 | 0.0s         |        1450 |
| INC-10     | ✅ YES         | 100.0%         |          6 | 0.01s        |        2750 | ❌ NO          | 0.0%           |          2 | 0.0s         |        1350 |

---

## Key Observations
1. **Root-Cause Accuracy**: The Multi-Agent system achieved **100.0%** accuracy vs **40.0%** for the single agent. The single agent frequently jumped to conclusions when encountering planted distractors (e.g. blaming a harmless DNS warning or recent UI deploy).
2. **Adversarial Critic Impact**: The Critic Agent was decisive in preventing premature closure, demanding deployment config diffs when telemetry alone was ambiguous.
3. **Hallucination Prevention**: On Incident 10 (where telemetry was completely absent), the Single-Agent baseline invented a plausible-sounding but false cause. In contrast, the Multi-Agent system's Critic properly stopped the investigation and declared an **INCONCLUSIVE** verdict.
4. **Trade-offs**: The Multi-Agent system uses ~2750 tokens compared to ~1395 for the baseline. This token overhead is directly invested in parallel verification and cross-examination.
