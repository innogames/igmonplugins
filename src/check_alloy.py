#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Grafana Alloy Check

This script checks Grafana Alloy metrics to detect when data is being dropped
instead of being shipped. It automatically discovers all supported component
instances (loki.write, pyroscope.write, otelcol.exporter.otlp,
prometheus.remote_write) and reports on each of them.

A state file is used to compute per-interval deltas so that alerts clear as
soon as drops stop occurring.

Copyright (c) 2026 InnoGames GmbH
"""
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import argparse
import json
import re
import requests
import sys

from typing import Dict, List, Optional, Set, Tuple


# Mapping from component type prefix to (dropped_metric, sent_metric, unit).
# dropped_metric may be None if the component does not expose a drop counter.
COMPONENT_METRICS: Dict[str, Tuple[Optional[str], str, str]] = {
    'loki.write': (
        'loki_write_dropped_bytes_total',
        'loki_write_sent_bytes_total',
        'bytes',
    ),
    'pyroscope.write': (
        'pyroscope_write_dropped_bytes_total',
        'pyroscope_write_sent_bytes_total',
        'bytes',
    ),
    'otelcol.exporter.otlp': (
        'otelcol_exporter_send_failed_spans_total',
        'otelcol_exporter_sent_spans_total',
        'spans',
    ),
    'prometheus.remote_write': (
        'prometheus_remote_storage_samples_failed_total',
        'prometheus_remote_storage_samples_total',
        'samples',
    ),
}

# All metric names we care about across all component types
ALL_METRICS: Set[str] = {
    metric
    for dropped, sent, _ in COMPONENT_METRICS.values()
    for metric in (dropped, sent)
    if metric is not None
}

STATUS_MAP: Dict[int, str] = {0: 'OK', 1: 'WARNING', 2: 'CRITICAL'}

COL_HEADERS: Tuple[str, str, str, str] = ('Component', 'Status', 'Dropped', 'Sent')


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Check Grafana Alloy metrics for dropped data across all components'
    )

    parser.add_argument(
        '--url',
        default='http://localhost:12345/metrics',
        help='Alloy metrics endpoint URL (default: http://localhost:12345/metrics)',
    )
    parser.add_argument(
        '--warning', '-w',
        required=True,
        type=float,
        help='Warning threshold — number of dropped units per interval',
    )
    parser.add_argument(
        '--critical', '-c',
        required=True,
        type=float,
        help='Critical threshold — number of dropped units per interval',
    )
    parser.add_argument(
        '--state-file',
        default='/run/check_alloy_backlog.json',
        help='Path to state file (default: /run/check_alloy_backlog.json)',
    )

    return parser.parse_args()


def fetch_metrics(url: str, timeout: int) -> str:
    """Fetch metrics from Alloy endpoint

    :param url: URL of the metrics endpoint
    :param timeout: Timeout in seconds
    :return: Raw metrics text
    :raises Exception: If the metrics endpoint returns a non-200 status code
    """
    response = requests.get(url, timeout=timeout)
    if response.status_code != 200:
        raise Exception(
            f'Non-200 status code from metrics endpoint: {response.status_code}'
        )
    return response.content.decode('utf-8')


def parse_all_component_metrics(metrics_text: str) -> Dict[str, Dict[str, float]]:
    """Parse all relevant metrics, grouped by component_id.

    :param metrics_text: Raw metrics text in Prometheus format
    :return: {component_id: {metric_name: value}}
    """
    result: Dict[str, Dict[str, float]] = {}

    for line in metrics_text.split('\n'):
        if not line or line.startswith('#'):
            continue

        # Quick pre-filter: skip lines that don't start with a metric we want
        if not any(line.startswith(m + '{') for m in ALL_METRICS):
            continue

        try:
            metric_name = line[:line.index('{')]
            labels_end = line.index('}')
            labels_str = line[line.index('{') + 1:labels_end]
            value_str = line[labels_end + 1:].strip()

            # Extract component_id label value
            for part in labels_str.split(','):
                part = part.strip()
                if part.startswith('component_id="') and part.endswith('"'):
                    component_id = part[len('component_id="'):-1]
                    value = float(value_str)
                    result.setdefault(component_id, {})[metric_name] = value
                    break

        except (ValueError, IndexError):
            continue

    return result


def load_state(state_file: str) -> Dict:
    """Load persisted counter state from disk"""
    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as e:
        print(f'WARNING - Could not load state file: {e}', file=sys.stderr)
        return {}


def save_state(state_file: str, state: Dict) -> None:
    """Persist counter state to disk"""
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except OSError as e:
        print(f'WARNING - Could not save state file: {e}', file=sys.stderr)


def fmt_row(cols: Tuple[str, str, str, str], col_widths: List[int]) -> str:
    """Format a table row with left-justified columns of given widths"""
    return '  '.join(c.ljust(w) for c, w in zip(cols, col_widths))


def component_type(component_id: str) -> Optional[str]:
    """Derive component type from a fully qualified component_id.

    Returns None if the component type is not in COMPONENT_METRICS.
    """
    prefix = component_id.rsplit('.', 1)[0]
    return prefix if prefix in COMPONENT_METRICS else None


def main() -> None:
    """Main entrypoint for script"""
    args = parse_args()

    try:
        metrics_text = fetch_metrics(args.url, timeout=10)
        by_component = parse_all_component_metrics(metrics_text)

        state = load_state(args.state_file)
        new_state: Dict = {}

        # Filter to only components whose type we support
        supported_components = {
            cid: metrics
            for cid, metrics in by_component.items()
            if component_type(cid) is not None
        }

        if not supported_components:
            print('OK - No supported components found (no data written yet)')
            sys.exit(0)

        worst_code = 0
        perfdata_parts: List[str] = []

        # Collect rows: (component_id, status_label, code, dropped_str, sent_str)
        rows: List[Tuple[str, str, int, str, str]] = []

        for component_id, metrics in sorted(supported_components.items()):
            ctype = component_type(component_id)
            if ctype is None:
                continue
            dropped_metric, sent_metric, unit = COMPONENT_METRICS[ctype]

            dropped = metrics.get(dropped_metric, 0.0)
            sent = metrics.get(sent_metric, 0.0)

            prev = state.get(component_id, {})
            new_state[component_id] = {'dropped': dropped, 'sent': sent}

            if not prev:
                # First time seeing this component — baseline only, no delta
                rows.append((component_id, 'BASELINE', 0, '-', '-'))
                continue

            delta_dropped = max(dropped - prev.get('dropped', 0.0), 0.0)
            delta_sent = max(sent - prev.get('sent', 0.0), 0.0)

            safe_id = re.sub(r'[^a-zA-Z0-9_]+', '_', component_id)
            perfdata_parts.append(
                f'{safe_id}_dropped={delta_dropped};{args.warning};{args.critical};0'
            )
            perfdata_parts.append(f'{safe_id}_sent={delta_sent}')

            if delta_dropped >= args.critical:
                code = 2
            elif delta_dropped > 0:
                code = 1
            else:
                code = 0

            worst_code = max(worst_code, code)
            rows.append((
                component_id,
                STATUS_MAP[code],
                code,
                f'{delta_dropped:.0f} {unit}',
                f'{delta_sent:.0f} {unit}',
            ))

        save_state(args.state_file, new_state)

        overall = STATUS_MAP[worst_code]

        # Build aligned table
        col_widths = [
            max(len(COL_HEADERS[0]), max(len(r[0]) for r in rows)),
            max(len(COL_HEADERS[1]), max(len(r[1]) for r in rows)),
            max(len(COL_HEADERS[2]), max(len(r[3]) for r in rows)),
            max(len(COL_HEADERS[3]), max(len(r[4]) for r in rows)),
        ]

        separator = '  '.join('-' * w for w in col_widths)
        table_lines = [
            fmt_row(COL_HEADERS, col_widths),
            separator,
        ] + [fmt_row((r[0], r[1], r[3], r[4]), col_widths) for r in rows]

        perfdata = ' '.join(perfdata_parts)
        first_line = f'{overall} - {len(rows)} component(s) checked'
        if perfdata:
            first_line += f' | {perfdata}'

        print(first_line)
        for line in table_lines:
            print(line)
        sys.exit(worst_code)

    except requests.exceptions.Timeout:
        print('UNKNOWN - Timeout connecting to Alloy metrics endpoint')
        sys.exit(3)
    except Exception as e:
        print(f'UNKNOWN - Error: {e}')
        sys.exit(3)


if __name__ == '__main__':
    main()
