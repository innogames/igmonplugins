#!/usr/bin/env python3
#
# InnoGames Monitoring Plugins - Mailgun ESP Block Check
#
# Nagios check for monitoring Mailgun ESP blocks using Reporting Metrics API.
#
# Copyright © 2025 InnoGames GmbH
#
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
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.utils import formatdate


def parse_args():
    """Define the CLI of the check."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="Mailgun API key")
    parser.add_argument(
        "--api-url",
        default="https://api.mailgun.net",
        help="Mailgun API base URL (default: https://api.mailgun.net)",
    )
    parser.add_argument(
        "--warning-threshold",
        type=int,
        default=10,
        help="Warning threshold for total ESP blocks",
    )
    parser.add_argument(
        "--critical-threshold",
        type=int,
        default=50,
        help="Critical threshold for total ESP blocks",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=1,
        help="Duration in hours to check (default: 1)",
    )
    return parser.parse_args()


def get_time_range(duration_hours):
    """Calculate start and end times for the specified duration."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=duration_hours)

    # Format times in RFC 2822 format using email.utils.formatdate
    start_str = formatdate(start_time.timestamp(), usegmt=True)
    end_str = formatdate(end_time.timestamp(), usegmt=True)

    return start_str, end_str


def create_payload(duration_hours):
    """Create JSON payload for API request."""
    start_time, end_time = get_time_range(duration_hours)

    payload = {
        "start": start_time,
        "end": end_time,
        "dimensions": ["domain", "recipient_provider"],
        "metrics": [
            "permanent_failed_esp_block_count",
            "temporary_failed_esp_block_count",
        ],
        "pagination": {
            "limit": 50,
            "skip": 0,
            "sort": "permanent_failed_esp_block_count:desc",
        },
        "resolution": "hour",
        "filter": {"AND": []},
        "include_aggregates": True,
        "include_subaccounts": False,
    }

    return json.dumps(payload).encode("utf-8")


def make_api_request(api_key, api_url, duration_hours):
    """Make API request to Mailgun."""
    payload = create_payload(duration_hours)

    # Build the full metrics endpoint URL
    metrics_url = f"{api_url.rstrip('/')}/v1/analytics/metrics"

    # Create basic auth header
    credentials = f"api:{api_key}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    # Create request
    request = urllib.request.Request(
        metrics_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_credentials}",
        },
    )

    with urllib.request.urlopen(request) as response:
        response_data = response.read().decode("utf-8")
        return json.loads(response_data)


def process_response_data(response_data):
    """Process API response and calculate totals."""
    items = response_data.get("items", [])

    if not items:
        return 0, 0, []

    total_permanent = 0
    total_temporary = 0
    domain_issues = []

    for item in items:
        dimensions_list = item.get("dimensions", [])
        metrics = item.get("metrics", {})

        # Extract domain and provider from dimensions list
        domain = "Unknown"
        provider = "Unknown"

        for dim in dimensions_list:
            dim_name = dim.get("dimension", "")
            dim_value = dim.get("value", "")
            if dim_name == "domain":
                domain = dim_value
            elif dim_name == "recipient_provider":
                provider = dim_value if dim_value else "unknown"

        permanent_count = metrics.get("permanent_failed_esp_block_count", 0)
        temporary_count = metrics.get("temporary_failed_esp_block_count", 0)
        total_blocks = permanent_count + temporary_count

        # Only include domains with blocks
        if total_blocks > 0:
            domain_issues.append(
                {
                    "domain": domain,
                    "provider": provider,
                    "permanent": permanent_count,
                    "temporary": temporary_count,
                    "total": total_blocks,
                }
            )

        total_permanent += permanent_count
        total_temporary += temporary_count

    # Sort by total blocks descending
    domain_issues.sort(key=lambda x: x["total"], reverse=True)

    return total_permanent, total_temporary, domain_issues


def format_domain_list(domain_issues, max_domains=10):
    """Format domain issues as a human-readable list."""
    if not domain_issues:
        return "No domains with ESP blocks found"

    # Limit to top domains
    top_domains = domain_issues[:max_domains]

    # Create human-readable list
    domain_list = ""
    for domain_info in top_domains:
        domain = domain_info["domain"]
        provider = domain_info["provider"]
        total = domain_info["total"]

        # Format with better spacing and readability
        if provider == "unknown":
            domain_list += f"{domain}: {total} blocks\n"
        else:
            domain_list += f"{domain} ({provider}): {total} blocks\n"

    # Add summary if there are more domains
    if len(domain_issues) > max_domains:
        remaining = len(domain_issues) - max_domains
        domain_list += f"... and {remaining} more domains with ESP blocks\n"

    return domain_list


def format_output(status, total_permanent, total_temporary, domain_issues):
    """Format clean human-readable output with simple list."""
    total_blocks = total_permanent + total_temporary

    if len(domain_issues) == 0:
        return "OK - No ESP blocks found in the specified time period"

    # Main status message
    message = (
        f"{status} - Found {len(domain_issues)} domains with ESP blocks "
        f"({total_blocks} total: {total_permanent} permanent, {total_temporary} temporary)"
    )

    # Domain list
    domain_list = format_domain_list(domain_issues)

    # Combine all parts with empty line between message and list
    return f"{message}\n\n{domain_list}"


def main(api_key, api_url, warning_threshold, critical_threshold, duration_hours):
    """Execute the check and generate exit codes and messages."""
    try:
        # Make API request
        response_data = make_api_request(api_key, api_url, duration_hours)

        # Process response data
        total_permanent, total_temporary, domain_issues = process_response_data(
            response_data
        )
        total_blocks = total_permanent + total_temporary

        # Determine status
        if total_blocks >= critical_threshold:
            status = "CRITICAL"
            exit_code = 2
        elif total_blocks >= warning_threshold:
            status = "WARNING"
            exit_code = 1
        else:
            status = "OK"
            exit_code = 0

        # Format and return output
        output = format_output(status, total_permanent, total_temporary, domain_issues)

        return exit_code, output

    except Exception as e:
        return 3, f"UNKNOWN: {e}"


if __name__ == "__main__":
    args = parse_args()
    code, output = main(
        args.api_key,
        args.api_url,
        args.warning_threshold,
        args.critical_threshold,
        args.duration,
    )
    print(output)
    sys.exit(code)
