"""
Production Incident Investigation System - Main CLI Entrypoint.
Usage:
  python main.py run --incident INC-01
  python main.py evaluate
  python main.py list
"""
from __future__ import annotations
import sys
import argparse
from tabulate import tabulate

from src.data_loader import list_scenarios, load_scenario
from src.graph import run_investigation
from evaluation.benchmark import run_benchmark, format_and_save_benchmark_report


def handle_list():
    scenarios = list_scenarios()
    print("\n=======================================================")
    print("  Available Synthetic Production Incidents")
    print("=======================================================")
    rows = []
    for inc_id in scenarios:
        sc = load_scenario(inc_id)
        rows.append([inc_id, sc.get("title", ""), sc.get("affected_service", ""), sc.get("severity", "")])
    
    print(tabulate(rows, headers=["Incident ID", "Title", "Affected Service", "Severity"], tablefmt="github"))
    print("\nRun an incident via: python main.py run --incident INC-01\n")


def handle_run(incident_id: str):
    print(f"\n[+] Loading incident fixture for {incident_id.upper()}...")
    try:
        scenario = load_scenario(incident_id)
    except FileNotFoundError:
        print(f"[!] Error: Incident '{incident_id}' not found. Run 'python main.py list' to see available incidents.")
        sys.exit(1)

    print(f"[*] Starting Multi-Agent Investigation for: {scenario.get('title')}...")
    print(f"    Affected Service: {scenario.get('affected_service')}")
    print(f"    Initial Ticket: {scenario.get('description')}\n")

    state = run_investigation(scenario)
    report = state.get("final_report")

    if not report:
        print("[!] Error: No report generated.")
        sys.exit(1)

    print("=" * 70)
    print("           OFFICIAL ROOT CAUSE ANALYSIS (RCA) REPORT           ")
    print("=" * 70)
    print(f"Incident ID        : {report.incident_id}")
    print(f"Status             : {report.conclusion_status}")
    print(f"Probable Root Cause: {report.probable_root_cause or 'N/A (INCONCLUSIVE)'}")
    print(f"Confidence Level   : {report.confidence_level * 100:.1f}%")
    print(f"Iterations         : {report.investigation_iterations}")
    print(f"Tool Calls Made    : {report.total_tool_calls}")
    print(f"Tokens Consumed    : {report.total_tokens_used:,}")
    print(f"Wall Clock Time    : {report.wall_clock_seconds}s")
    print("\n--- Executive Summary ---")
    print(report.executive_summary)

    print("\n--- Ranked Competing Hypotheses ---")
    hypo_rows = []
    for h in report.ranked_hypotheses:
        hypo_rows.append([h.id, h.title, f"{h.confidence*100:.1f}%", len(h.supporting_evidence_ids), len(h.contradicting_evidence_ids)])
    print(tabulate(hypo_rows, headers=["ID", "Hypothesis", "Confidence", "Supporting Ev", "Contradicting Ev"], tablefmt="github"))

    print("\n--- Verified Facts vs Unverified Assumptions ---")
    print(f"Facts ({len(report.facts)} verified):")
    for f in report.facts[:6]:
        print(f"  • [{f.source.upper()}] {f.description}")
    if report.assumptions:
        print(f"\nAssumptions ({len(report.assumptions)}):")
        for a in report.assumptions:
            print(f"  • {a.description}")

    print("\n--- Recommended Remediation Actions ---")
    action_rows = []
    for act in report.recommended_actions:
        action_rows.append([act.priority, act.type.value, act.target_service, act.description])
    print(tabulate(action_rows, headers=["Priority", "Action Type", "Target Service", "Description"], tablefmt="github"))
    print("\n" + "=" * 70 + "\n")


def handle_evaluate():
    print("\n=======================================================")
    print("  Running Multi-Agent vs Baseline Evaluation Benchmark ")
    print("=======================================================")
    results = run_benchmark()
    report = format_and_save_benchmark_report(results)
    print("\n" + report)
    print("\n[+] Full markdown report saved to: evaluation/benchmark_results.md\n")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Incident Investigation System")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: list
    subparsers.add_parser("list", help="List all available synthetic incidents")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run multi-agent investigation on a specific incident")
    run_parser.add_argument("--incident", "-i", default="INC-01", help="Incident ID (e.g. INC-01, INC-02)")

    # Command: evaluate
    subparsers.add_parser("evaluate", help="Run full evaluation comparing Multi-Agent vs Single-Agent baseline")

    args = parser.parse_args()

    if args.command == "list":
        handle_list()
    elif args.command == "run":
        handle_run(args.incident)
    elif args.command == "evaluate":
        handle_evaluate()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
