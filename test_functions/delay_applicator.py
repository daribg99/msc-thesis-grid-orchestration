import json
import re
import subprocess
from typing import Set, Tuple, List

#SCALE_FACTOR = 2.39  # empirically found to match the observed end-to-end delay in the testbed
SCALE_FACTOR = 1.0  # use the raw graph latencies without scaling

def run(cmd):
    p = subprocess.run(cmd, shell=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}")


def docker_ps_names() -> List[str]:
    p = subprocess.run(
        "docker ps --format '{{.Names}}'",
        shell=True, text=True, capture_output=True
    )
    return [l.strip() for l in p.stdout.splitlines() if l.strip()]


def normalize_cluster_id(x: str, cc_cluster: str) -> str:
    s = (x or "").strip()

    if s.upper() == "CC":
        m = re.fullmatch(r"cluster-?(\d+)", cc_cluster.strip(), re.IGNORECASE)
        if not m:
            raise ValueError(f"Invalid cc_cluster: {cc_cluster}")
        return f"cluster-{int(m.group(1))}"

    m = re.fullmatch(r"N(\d+)", s, re.IGNORECASE)
    if m:
        return f"cluster-{int(m.group(1))}"

    m = re.fullmatch(r"cluster-?(\d+)", s, re.IGNORECASE)
    if m:
        return f"cluster-{int(m.group(1))}"

    raise ValueError(f"Unrecognized node id: {x}")


def find_cluster_server_container(cluster_id: str, names: List[str]) -> str:
    m = re.fullmatch(r"cluster-(\d+)", cluster_id)
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


def get_pid(container: str) -> int:
    p = subprocess.run(
        f"docker inspect -f '{{{{.State.Pid}}}}' {container}",
        shell=True, text=True, capture_output=True
    )
    pid = int(p.stdout.strip())
    if pid <= 0:
        raise RuntimeError(f"Invalid PID for {container}")
    return pid


def cluster_to_graph_node(cluster_id: str, cc_cluster: str) -> str:
    # cluster-27 -> CC, cluster-12 -> N12
    cc_norm = normalize_cluster_id(cc_cluster, cc_cluster)
    if cluster_id == cc_norm:
        return "CC"
    m = re.fullmatch(r"cluster-(\d+)", cluster_id)
    return f"N{m.group(1)}"


def apply_delay(G, output_json_path: str, iface: str = "eth0", cc_cluster: str = "cluster27"):
    with open(output_json_path) as f:
        out = json.load(f)

    path_dict = out.get("path", {})
    if not isinstance(path_dict, dict) or not path_dict:
        raise ValueError("output.json has no 'path' dict")

    paths = [
        obj["path"]
        for obj in path_dict.values()
        if isinstance(obj, dict) and isinstance(obj.get("path"), list)
    ]
    if not paths:
        raise ValueError("output.json has no valid PMU paths")

    container_names = docker_ps_names()

    configured_sources: Set[str] = set()
    configured_edges: Set[Tuple[str, str]] = set()

    for p in paths:
        if len(p) < 3:
            continue

        # ignore PMU -> first node
        for i in range(1, len(p) - 1):
            src_raw = p[i]
            dst_raw = p[i + 1]

            # normalize N12/CC -> cluster-12/cluster-27
            src_cluster = normalize_cluster_id(src_raw, cc_cluster)
            dst_cluster = normalize_cluster_id(dst_raw, cc_cluster)

            if src_cluster in configured_sources:
                continue

            hop = (src_cluster, dst_cluster)
            if hop in configured_edges:
                continue

            u = cluster_to_graph_node(src_cluster, cc_cluster)
            v = cluster_to_graph_node(dst_cluster, cc_cluster)

            if not G.has_edge(u, v):
                raise RuntimeError(f"Graph has no edge {u}–{v}")

            base_delay = float(G[u][v]["latency"])
            delay = base_delay * SCALE_FACTOR


            container = find_cluster_server_container(src_cluster, container_names)
            pid = get_pid(container)

            print(f"🧩 {src_cluster} → {dst_cluster} | delay={delay}ms | container={container}")

            run(f"sudo nsenter -t {pid} -n ip link show {iface} >/dev/null")
            run(
                f"sudo nsenter -t {pid} -n "
                f"tc qdisc replace dev {iface} root netem delay {delay}ms"
            )

            configured_sources.add(src_cluster)
            configured_edges.add(hop)
