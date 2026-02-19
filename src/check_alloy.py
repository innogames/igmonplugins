#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Grafana Alloy Check

This script checks Grafana Alloy metrics to detect when logs are piling up
instead of being shipped. It monitors the difference between encoded bytes
(queued) and sent bytes (shipped) via Alloy's Prometheus metrics endpoint.

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
import sys
from typing import Dict, List

import requests


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Check Grafana Alloy metrics for log backlog'
    )

    parser.add_argument(
        '--url',
        default='http://localhost:12345/metrics',
        help='Alloy metrics endpoint URL (default: http://localhost:12345/metrics)',
    )
    parser.add_argument(
        '--component',
        default='loki.write.default',
        help='Component to monitor (default: loki.write.default)',
    )
    parser.add_argument(
        '--warning', '-w',
        required=True,
        type=float,
        help='Warning threshold in bytes',
    )
    parser.add_argument(
        '--critical', '-c',
        required=True,
        type=float,
        help='Critical threshold in bytes',
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


def parse_component_metrics(
    metrics_text: str,
    component: str,
    metric_names: List[str]
) -> Dict[str, float]:
    """Parse specific Prometheus metrics for a component and stop early

    :param metrics_text: Raw metrics text in Prometheus format
    :param component: Component ID to filter by
    :param metric_names: List of metric names to find
    :return: Dictionary mapping metric names to their values
    """
    found_metrics: Dict[str, float] = {}
    needed_metrics = set(metric_names)

    for line in metrics_text.split('\n'):
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue

        # Quick check: does this line contain any metric we need?
        line_has_needed_metric = False
        for metric_name in needed_metrics:
            if line.startswith(metric_name + '{'):
                line_has_needed_metric = True
                break

        if not line_has_needed_metric:
            continue

        try:
            # Parse metric line: metric_name{label="value",...} numeric_value
            if '{' not in line:
                continue

            metric_name = line[:line.index('{')]
            labels_end = line.index('}')
            labels_str = line[line.index('{') + 1:labels_end]
            value_str = line[labels_end + 1:].strip()

            # Check if this is for our component
            if f'component_id="{component}"' in labels_str:
                value = float(value_str)
                found_metrics[metric_name] = value
                needed_metrics.discard(metric_name)

                # Early exit if we found all metrics
                if not needed_metrics:
                    break

        except (ValueError, IndexError):
            # Skip lines that can't be parsed
            continue

    return found_metrics


def main() -> None:
    """Main entrypoint for script"""
    args = parse_args()

    try:
        # Fetch and parse metrics
        metrics_text = fetch_metrics(args.url, timeout=10)

        # Parse only the metrics we need for this component
        metrics = parse_component_metrics(
            metrics_text,
            args.component,
            ['loki_write_encoded_bytes_total', 'loki_write_sent_bytes_total']
        )

        # Verify we got both metrics
        if 'loki_write_encoded_bytes_total' not in metrics:
            raise KeyError(
                f'Metric "loki_write_encoded_bytes_total" not found for component "{args.component}"'
            )
        if 'loki_write_sent_bytes_total' not in metrics:
            raise KeyError(
                f'Metric "loki_write_sent_bytes_total" not found for component "{args.component}"'
            )

        # Get metric values and calculate backlog
        encoded_bytes = metrics['loki_write_encoded_bytes_total']
        sent_bytes = metrics['loki_write_sent_bytes_total']

        # Backlog can be negative if counters reset or roll over; treat that as zero
        raw_backlog = encoded_bytes - sent_bytes
        check_value = max(raw_backlog, 0.0)
        value_label = 'backlog'

        # Determine status based on thresholds
        if check_value >= args.critical:
            status = 'CRITICAL'
            code = 2
        elif check_value >= args.warning:
            status = 'WARNING'
            code = 1
        else:
            status = 'OK'
            code = 0

        # Build performance data
        perfdata_parts = [
            f'{value_label}={check_value};{args.warning};{args.critical};0',
            f'encoded={encoded_bytes}',
            f'sent={sent_bytes}'
        ]
        perfdata = ' '.join(perfdata_parts)

        # Output result
        print(f'{status} - {value_label} {check_value:.0f} bytes | {perfdata}')

        sys.exit(code)

    except requests.exceptions.Timeout:
        print('UNKNOWN - Timeout connecting to Alloy metrics endpoint')
        sys.exit(3)
    except Exception as e:
        print(f'UNKNOWN - Error: {e}')
        sys.exit(3)


if __name__ == '__main__':
    main()
