#!/usr/bin/env python3
"""
InnoGames Monitoring Plugins - check for repmgrd status
Checks if repmgr cluster is healthy and all nodes are connected and healthy
"""

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
            issues.append(f"node_{node['node_id']}: service status not found")
            continue

        node_name = service["node_name"]

        # Check connection
        if node["connection_status"] != 0:
            issues.append(f"{node_name} is disconnected")

        if not service["repmgrd_running"]:
            issues.append(f"{node_name}: repmgrd not running")

        if service["paused"]:
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
    nodes: List[dict] = []
    lines = output.strip().split("\n")

    for line in lines:
        if not line.strip():
            continue

        parts = line.split(",")
        if len(parts) >= 3:
            node_info = {
                "node_id": int(parts[0]),
                "connection_status": int(parts[1]),  # 0 = connected
                "recovery_type": int(
                    parts[2]
                ),  # -1 = unknown, 0 = primary, 1 = standby
            }
            nodes.append(node_info)

    return nodes


def parse_service_status_csv(output: str) -> Dict[int, dict]:
    """Parse repmgr service status --csv output"""
    services: Dict[int, dict] = {}
    lines = output.strip().split("\n")

    for line in lines:
        if not line.strip():
            continue

        parts = line.split(",")
        if len(parts) >= 10:
            node_id = int(parts[0])
            service_info = {
                "node_id": node_id,
                "node_name": parts[1],
                "repmgrd_running": int(parts[4]) == 1,
                "paused": int(parts[6]),
            }
            services[node_id] = service_info

    return services


if __name__ == "__main__":
    main()
