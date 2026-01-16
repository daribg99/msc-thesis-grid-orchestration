import json
import re
import subprocess
from typing import Set, Tuple

def run(cmd):
    p = subprocess.run(cmd, shell=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}")

def docker_ps_names():
    p = subprocess.run(
        "docker ps --format '{{.Names}}'",
        shell=True, text=True, capture_output=True
    )
    return [l.strip() for l in p.stdout.splitlines() if l.strip()]

def find_cluster_server_container(cluster_id, names):
    m = re.fullmatch(r"cluster-?(\d+)", cluster_id)
    if not m:
        raise ValueError(f"Invalid cluster id: {cluster_id}")
    n = m.group(1)

    wanted = f"k3d-cluster-{n}-server-0"
    if wanted in names:
        return wanted

    prefix = f"k3d-cluster-{n}-server-"
    candidates = [c for c in names if c.startswith(prefix) and "serverlb" not in c]
    if not candidates:
        raise RuntimeError(f"No server container found for {cluster_id}")
    return candidates[0]

def get_pid(container):
    p = subprocess.run(
        f"docker inspect -f '{{{{.State.Pid}}}}' {container}",
        shell=True, text=True, capture_output=True
    )
    pid = int(p.stdout.strip())
    if pid <= 0:
        raise RuntimeError(f"Invalid PID for {container}")
    return pid

def cluster_to_graph_node(cluster_id, cc_cluster):
    if re.sub("-", "", cluster_id) == re.sub("-", "", cc_cluster):
        return "CC"
    m = re.fullmatch(r"cluster-?(\d+)", cluster_id)
    return f"N{m.group(1)}"

def apply_delay(
    G,
    output_json_path: str,
    iface: str = "eth0",
    cc_cluster: str = "cluster27",
):
   

    with open(output_json_path) as f:
        out = json.load(f)

    paths = out.get("paths", [])
    if not paths:
        raise ValueError("output.json has no paths")

    container_names = docker_ps_names()

    configured_sources: Set[str] = set()
    configured_edges: Set[Tuple[str, str]] = set()

    for p in paths:
        if len(p) < 3:
            continue

        # ignora PMU -> primo cluster
        for i in range(1, len(p) - 1):
            src_cluster = p[i]
            dst_cluster = p[i + 1]

            if src_cluster in configured_sources:
                continue

            hop = (src_cluster, dst_cluster)
            if hop in configured_edges:
                continue

            u = cluster_to_graph_node(src_cluster, cc_cluster)
            v = cluster_to_graph_node(dst_cluster, cc_cluster)

            if not G.has_edge(u, v):
                raise RuntimeError(f"Graph has no edge {u}–{v}")

            delay = float(G[u][v]["latency"])

            container = find_cluster_server_container(src_cluster, container_names)
            pid = get_pid(container)

            print(f"🧩 {src_cluster} → {dst_cluster} | delay={delay}ms | container={container}")

            run(f"sudo nsenter -t {pid} -n ip link | grep -w {iface}")
            run(
                f"sudo nsenter -t {pid} -n "
                f"tc qdisc replace dev {iface} root netem delay {delay}ms"
            )

            configured_sources.add(src_cluster)
            configured_edges.add(hop)
