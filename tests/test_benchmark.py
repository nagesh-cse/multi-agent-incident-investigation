import pytest
from evaluation.benchmark import run_benchmark


def test_full_evaluation_benchmark_runs():
    results = run_benchmark()
    assert len(results) == 10
    
    # Check that multi-agent outperforms single-agent on accuracy and grounding
    ma_correct = sum(1 for r in results if r.ma_root_cause_correct)
    sa_correct = sum(1 for r in results if r.sa_root_cause_correct)
    assert ma_correct > sa_correct

    # Check that INC-10 is correctly handled by Multi-Agent and failed by Single-Agent
    inc_10 = next(r for r in results if r.incident_id == "INC-10")
    assert inc_10.ma_root_cause_correct is True
    assert inc_10.sa_root_cause_correct is False
