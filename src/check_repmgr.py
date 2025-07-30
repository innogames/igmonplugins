#!/usr/bin/env python3
"""
InnoGames Monitoring Plugins - check for repmgrd status
Checks if repmgr cluster is healthy and all nodes are connected and healthy
"""

import csv
import subprocess
import sys
from typing import Dict, List, Tuple


def main() -> None:
    # Check "repmgr cluster show"
    ret_code, stdout, stderr = run_command("repmgr cluster show --csv")
    if ret_code != 0:
        print(f"CRITICAL - Failed to get cluster status: {stderr}")
        sys.exit(2)
    cluster_nodes = parse_cluster_show_csv(stdout)

    # Check "repmgr service status" e.g., for paused service
    ret_code, stdout, stderr = run_command("repmgr service status --csv")
    if ret_code != 0:
        print(f"CRITICAL - Failed to get service status: {stderr}")
        sys.exit(2)
    service_status = parse_service_status_csv(stdout)

    # Check overall cluster health
    is_healthy, health_message = check_cluster_health(cluster_nodes, service_status)
    if not is_healthy:
        print(f"CRITICAL - {health_message}")
        sys.exit(2)

    print(f"OK - {health_message}")
    sys.exit(0)


def check_cluster_health(
    cluster_nodes: List[dict], service_status: Dict[int, dict]
) -> Tuple[bool, str]:
    """Check if the cluster is healthy (everything connected and running)"""
    issues = []

    if not cluster_nodes:
        issues.append("No nodes found in cluster")

    for node in cluster_nodes:
        service = service_status.get(node["node_id"])
        if not service:
            issues.append(f"node {node['node_id']}: service status not found")
            continue

        node_name = service["node_name"]

        # Check connection
        if node["connection_status"] != "0":
            issues.append(f"{node_name} is disconnected")

        if not int(service["pg_running"]):
            issues.append(f"{node_name}: postgres not running")

        if not int(service["repmgrd_running"]):
            issues.append(f"{node_name}: repmgrd not running")

        if int(service["paused"]):
            issues.append(f"{node_name}: repmgrd is paused")

    if issues:
        return False, "\n".join(issues)

    return True, f"Cluster healthy with {len(cluster_nodes)} nodes"


def run_command(command: str) -> Tuple[int, str, str]:
    """Execute a shell command and return output"""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=10
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def parse_cluster_show_csv(output: str) -> List[dict]:
    """Parse repmgr cluster show --csv output"""
    lines = output.strip().splitlines()
    reader = csv.DictReader(lines, ["node_id", "connection_status", "recovery_type"])
    result = list([row for row in reader])

    return result


def parse_service_status_csv(output: str) -> Dict[int, dict]:
    """Parse repmgr service status --csv output. Indexed by node_id."""

    lines = output.strip().splitlines()
    reader = csv.DictReader(
        lines,
        [
            "node_id",
            "node_name",
            "role",
            "pg_running",
            "repmgrd_running",
            "pid",
            "paused",
            "priority",
            "last_seen",
            "location",
        ],
    )
    return {row["node_id"]: row for row in reader}


if __name__ == "__main__":
    main()
