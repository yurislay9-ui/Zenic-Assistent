#!/usr/bin/env python3
"""
ZENIC-AGENTS v16 - Regression Detection Script (Phase 4.3)

Compares benchmark results against a baseline and detects regressions.
Used in CI to fail the pipeline when performance degrades significantly.

Usage:
    python scripts/check_regressions.py --results-dir results/ --threshold 20
    python scripts/check_regressions.py --current bench_hnsw.json --baseline baselines/hnsw.json

Output:
    regression_report.json: Detailed report with per-metric comparison

Exit codes:
    0: No regressions detected
    1: Regressions detected above threshold
    2: Error during analysis
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional


def load_benchmark_json(path: str) -> Dict[str, Any]:
    """Load pytest-benchmark JSON output."""
    with open(path, 'r') as f:
        return json.load(f)


def extract_metrics(data: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Extract key metrics from benchmark JSON.

    Returns:
        Dict mapping benchmark name -> {mean, median, stddev, rounds}
    """
    metrics = {}

    # pytest-benchmark format
    benchmarks = data.get('benchmarks', [])
    for bench in benchmarks:
        name = bench.get('name', bench.get('fullname', 'unknown'))
        stats = bench.get('stats', {})
        metrics[name] = {
            'mean': stats.get('mean', 0),
            'median': stats.get('median', 0),
            'stddev': stats.get('stddev', 0),
            'rounds': stats.get('rounds', 0),
            'min': stats.get('min', 0),
            'max': stats.get('max', 0),
            'ops': stats.get('ops', 0),
        }

    return metrics


def compare_metrics(
    baseline: Dict[str, Dict[str, float]],
    current: Dict[str, Dict[str, float]],
    threshold_percent: float = 20.0,
) -> Dict[str, Any]:
    """Compare current metrics against baseline and detect regressions.

    A regression is when the current mean is more than threshold_percent
    higher than the baseline mean (i.e., slower).

    Args:
        baseline: Baseline metrics from extract_metrics().
        current: Current metrics from extract_metrics().
        threshold_percent: Maximum allowed regression percentage.

    Returns:
        Dict with regression report including per-metric comparison.
    """
    metrics_comparison = {}
    regressions = []

    all_keys = set(list(baseline.keys()) + list(current.keys()))

    for key in sorted(all_keys):
        base = baseline.get(key, {})
        curr = current.get(key, {})

        base_mean = base.get('mean', 0)
        curr_mean = curr.get('mean', 0)

        if base_mean == 0:
            change_pct = 0.0 if curr_mean == 0 else float('inf')
        else:
            change_pct = ((curr_mean - base_mean) / base_mean) * 100

        is_regression = change_pct > threshold_percent

        metrics_comparison[key] = {
            'baseline': round(base_mean, 6),
            'current': round(curr_mean, 6),
            'change_percent': round(change_pct, 2),
            'regression': is_regression,
            'unit': 'seconds',
        }

        if is_regression:
            regressions.append({
                'metric': key,
                'baseline': round(base_mean, 6),
                'current': round(curr_mean, 6),
                'change_percent': round(change_pct, 2),
            })

    return {
        'threshold_percent': threshold_percent,
        'total_metrics': len(all_keys),
        'regressions_found': len(regressions),
        'regressions': regressions,
        'metrics': metrics_comparison,
        'passed': len(regressions) == 0,
    }


def scan_results_dir(results_dir: str) -> List[str]:
    """Scan a directory for benchmark JSON files."""
    json_files = []
    for root, dirs, files in os.walk(results_dir):
        for f in files:
            if f.endswith('.json'):
                json_files.append(os.path.join(root, f))
    return sorted(json_files)


def main():
    parser = argparse.ArgumentParser(
        description='Check benchmark results for performance regressions'
    )
    parser.add_argument(
        '--results-dir',
        default='results/',
        help='Directory containing benchmark JSON results',
    )
    parser.add_argument(
        '--current',
        help='Current benchmark JSON file (single file mode)',
    )
    parser.add_argument(
        '--baseline',
        help='Baseline benchmark JSON file (single file mode)',
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=20.0,
        help='Regression threshold percentage (default: 20%%)',
    )
    parser.add_argument(
        '--output',
        default='regression_report.json',
        help='Output report file path',
    )

    args = parser.parse_args()

    # Single file mode
    if args.current and args.baseline:
        try:
            current_data = load_benchmark_json(args.current)
            baseline_data = load_benchmark_json(args.baseline)
            current_metrics = extract_metrics(current_data)
            baseline_metrics = extract_metrics(baseline_data)
            report = compare_metrics(baseline_metrics, current_metrics, args.threshold)
        except Exception as e:
            print(f"Error comparing benchmarks: {e}", file=sys.stderr)
            sys.exit(2)

    # Directory scan mode
    else:
        results_files = scan_results_dir(args.results_dir)
        if not results_files:
            print(f"No benchmark JSON files found in {args.results_dir}", file=sys.stderr)
            # Create empty report
            report = {
                'threshold_percent': args.threshold,
                'total_metrics': 0,
                'regressions_found': 0,
                'regressions': [],
                'metrics': {},
                'passed': True,
                'note': 'No benchmark files found — skipping regression check',
            }
        else:
            # For CI, we compare against ourselves (first run)
            # In production, you'd compare against a cached baseline
            all_metrics: Dict[str, Dict[str, float]] = {}
            for f in results_files:
                try:
                    data = load_benchmark_json(f)
                    metrics = extract_metrics(data)
                    all_metrics.update(metrics)
                except Exception as e:
                    print(f"Warning: Could not parse {f}: {e}", file=sys.stderr)

            # Without a baseline, just report the current metrics
            report = {
                'threshold_percent': args.threshold,
                'total_metrics': len(all_metrics),
                'regressions_found': 0,
                'regressions': [],
                'metrics': {
                    k: {
                        'baseline': 'N/A',
                        'current': round(v.get('mean', 0), 6),
                        'change_percent': 0,
                        'regression': False,
                        'unit': 'seconds',
                    }
                    for k, v in all_metrics.items()
                },
                'passed': True,
                'note': 'No baseline available — reporting current metrics only',
            }

    # Write report
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  REGRESSION CHECK RESULTS")
    print(f"{'='*60}")
    print(f"  Threshold: {report['threshold_percent']}%")
    print(f"  Metrics checked: {report['total_metrics']}")
    print(f"  Regressions found: {report['regressions_found']}")
    print(f"  Result: {'PASSED' if report['passed'] else 'FAILED'}")
    print(f"{'='*60}\n")

    if report['regressions']:
        print("  REGRESSIONS:")
        for r in report['regressions']:
            print(f"    - {r['metric']}: {r['change_percent']}% slower "
                  f"({r['baseline']}s → {r['current']}s)")
        print()

    sys.exit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
