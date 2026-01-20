#!/usr/bin/env python3
import json
import sys
import subprocess
import time
from pathlib import Path
from collections import defaultdict, deque


# --------------------------------------------------------
#   HELPER: run command
# --------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
OPENPDC_CLI = BASE_DIR / "openpdc_cli.sh"

def run_cmd(cmd):
    print("\n>>> RUNNING:\n" + " ".join(cmd) + "\n")
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)


def get_pdc_pod(cluster):
    context = cluster_to_context(cluster)
    cmd = f"kubectl --context {context} get pods -n lower -o jsonpath='{{.items[*].metadata.name}}'"
    out = subprocess.check_output(cmd, shell=True).decode().split()

    pods = [
        p for p in out
        if "openpdc" in p and not p.startswith("openpdc-test-")
    ]

    if not pods:
        raise RuntimeError(f"No openpdc pod found in {cluster}")

    return pods[0]



def get_node_ip(cluster):
    context = cluster_to_context(cluster)
    node_name = f"{context}-server-0"
    cmd = (
        f"kubectl --context {context} get node {node_name} "
        f"-o jsonpath='{{.status.addresses[?(@.type==\"InternalIP\")].address}}'"
    )
    return subprocess.check_output(cmd, shell=True).decode().strip()




def calc_port(child_cluster):
    num = int(child_cluster.replace("cluster", ""))
    return int(f"30{num-1}99")   # e.g., cluster4 → 30399

def cluster_to_context(cluster):
    # cluster arrives as "clusterX"
    number = cluster.replace("cluster", "")
    return f"k3d-cluster-{number}"

def cluster_number(cluster):
    return cluster.replace("cluster", "")

def print_operation_plan(order, config):
    print("\n=== ORDER OF OPERATIONS (bottom → top) ===\n")

    for cluster in order:
        print(f"Cluster {cluster}:")
        if config[cluster]["pmu_direct"]:
            print("  - addpmu")
        if config[cluster]["connections_downstream"]:
            print("  - connectiontopdc")
        print("  - createoutputstream")
        print()

def wait_for_pdc_ready(cluster, timeout=7200):
    context = cluster_to_context(cluster)
    start = time.time()

    print(f"\n⏳ Waiting for PDC in {cluster} to become Running. The operation may take several minutes...")

    while True:
        try:
            pod = get_pdc_pod(cluster)
        except RuntimeError:
            pod = None

        if pod:
            cmd = (
                f"kubectl --context {context} get pod {pod} -n lower "
                f"-o jsonpath='{{.status.phase}}'"
            )
            try:
                status = subprocess.check_output(cmd, shell=True).decode().strip()
            except subprocess.CalledProcessError:
                status = ""
        else:
            status = ""

        if status == "Running":
            print(f"✅ PDC in {cluster} is Running. Configuration can proceed...")
            return

        if time.time() - start > timeout:
            print(f"\n❌ ERROR: PDC in {cluster} did NOT become Running within {timeout} seconds.")
            sys.exit(1)

        time.sleep(2)

def to_cluster_name(node: str, cc_cluster_id: int = 27) -> str:
    # N4 -> cluster4, CC -> cluster27
    if node == "CC":
        return f"cluster{cc_cluster_id}"
    if node.startswith("N") and node[1:].isdigit():
        return f"cluster{int(node[1:])}"
    return node  # fallback


def to_pmu_name(pmu: str) -> str:
    # PMU1 -> PMU-1
    if pmu.startswith("PMU") and pmu[3:].isdigit():
        return f"PMU-{int(pmu[3:])}"
    return pmu  # fallback


def extract_paths_from_new_json(paths_json, cc_cluster_id: int = 27):
    
    paths = []

    for pmu, info in paths_json["path"].items():
        node_path = info["path"]

        pmu_old = to_pmu_name(node_path[0])
        clusters_old = [to_cluster_name(x, cc_cluster_id) for x in node_path[1:]]

        paths.append([pmu_old] + clusters_old)

    return paths

# --------------------------------------------------------
#   Construction of PDC configuration from paths
# --------------------------------------------------------

def build_pdc_topology(paths_json):
    
    paths = extract_paths_from_new_json(paths_json)
    config = {}
    
    # Initialization
    for path in paths:
        pmu = path[0]
        clusters = path[1:]  

        for c in clusters:
            if c not in config:
                config[c] = {
                    "pmu_direct": [],
                    "outputstream": set(),
                    "connections_downstream": []
                }

        leaf = clusters[0]
        config[leaf]["pmu_direct"].append(pmu)
        config[leaf]["outputstream"].add(pmu)

    # Propagation + connections
    for path in paths:
        pmu = path[0]
        clusters = path[1:]

        for i in range(1, len(clusters)):
            child = clusters[i - 1]
            parent = clusters[i]

            config[parent]["outputstream"].add(pmu)

            existing = None
            for conn in config[parent]["connections_downstream"]:
                if conn["node"] == child:
                    existing = conn
                    break

            if existing:
                if pmu not in existing["pmus"]:
                    existing["pmus"].append(pmu)
            else:
                config[parent]["connections_downstream"].append({
                    "node": child,
                    "pmus": [pmu],
                    "port": calc_port(child)
                })

    def pmu_sort_key(pmu_name: str) -> int:
        return int(pmu_name.split("-")[-1])

    for c in config:
        config[c]["outputstream"] = sorted(
            config[c]["outputstream"],
            key=pmu_sort_key
        )

    return config



# --------------------------------------------------------
#   Construction of dependencies (ordering)
# --------------------------------------------------------

from collections import defaultdict, deque

def compute_order(paths_json):
    paths = extract_paths_from_new_json(paths_json)

    deps = defaultdict(set)
    all_clusters = set()

    for path in paths:
        nodes = path[1:]  

        for n in nodes:
            all_clusters.add(n)

        for i in range(1, len(nodes)):
            child = nodes[i - 1]
            parent = nodes[i]
            deps[parent].add(child)

    for c in all_clusters:
        deps.setdefault(c, set())

    in_degree = {c: 0 for c in all_clusters}
    for parent, children in deps.items():
        in_degree[parent] = len(children)

    queue = deque([c for c in all_clusters if in_degree[c] == 0])
    order = []

    # Kahn
    while queue:
        node = queue.popleft()
        order.append(node)

        for parent, children in deps.items():
            if node in children:
                in_degree[parent] -= 1
                if in_degree[parent] == 0:
                    queue.append(parent)

    return order


# --------------------------------------------------------
#   EXECUTE EVERYTHING 
# --------------------------------------------------------
        
def execute_all(order, config):
    for cluster in order:
        context = cluster_to_context(cluster)
        
        cmd_check = f"kubectl config get-contexts -o name | grep '^{context}$'"
        result = subprocess.run(cmd_check, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print(f"\n❌ ERROR: Kubernetes context '{context}' does not exist.\n"
                  f"   This means the cluster '{cluster}' is referenced in the PATHS JSON \n"
                  f"   but does not exist in your system.\n")
            sys.exit(1)
        
        wait_for_pdc_ready(cluster)
        db = cluster
        pod = get_pdc_pod(cluster)

        print(f"\n==============================")
        print(f" CONFIGURING {cluster}")
        print(f"==============================\n")

        # 0) HISTORIAN CREATION
        cmd = [
            str(OPENPDC_CLI), "createhistorian",
            "--db-context", "k3d-cluster-db",
            "--openpdc-context", context,
            "--db-ns", "db", "--pdc-ns", "lower",
            "--db", cluster,
            "--pod", pod
        ]
        run_cmd(cmd)
        
        # 1) ADDPMU
        for pmu in config[cluster]["pmu_direct"]:
            pmu_name = pmu.replace("PMU", "Pmu")

            cmd = [
                str(OPENPDC_CLI), "addpmu",
                "--db-context", "k3d-cluster-db",
                "--openpdc-context", context,
                "--db-ns", "db", "--pdc-ns", "lower",
                "--name", pmu_name,
                "--pod", pod,
                "--db", db
            ]
            run_cmd(cmd)

        # 2) CONNECTION
        for conn in config[cluster]["connections_downstream"]:
            child = conn["node"]
            pmus = ",".join(conn["pmus"])
            server_ip = get_node_ip(child)
            port = calc_port(child)
            name = f"lower{child}"
            child_num = cluster_number(child)
            parent_num = cluster_number(cluster)
            acronym = f"CNC{child_num}C{parent_num}"

            
            cmd = [
                str(OPENPDC_CLI), "connectiontopdc",
                "--db-context", "k3d-cluster-db",
                "--openpdc-context", context,
                "--db-ns", "db", "--pdc-ns", "lower",
                "--db", db,
                "--name", name,
                "--pod", pod,
                "--acronym", acronym,
                "--server", server_ip,
                "--port", str(port),
                "--pmus", pmus
            ]
            run_cmd(cmd)

        # 3) OUTPUTSTREAM
        pmus = ",".join(config[cluster]["outputstream"])
        name = f"output{cluster}"
        num = cluster_number(cluster)
        acronym = f"OUTC{num}"

        cmd = [
            str(OPENPDC_CLI), "createoutputstream",
            "--db-context", "k3d-cluster-db",
            "--openpdc-context", context,
            "--db-ns", "db", "--pdc-ns", "lower",
            "--db", db,
            "--pod", pod,
            "--acronym", acronym,
            "--name", name,
            "--pmus", pmus
        ]
        run_cmd(cmd)


# --------------------------------------------------------
#   MAIN
# --------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 autopdc-configurator.py <file_json>")
        sys.exit(1)

    json_path = sys.argv[1]

    try:
        with open(json_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    config = build_pdc_topology(data)

    print("=== CONFIG GENERATED ===")
    print(json.dumps(config, indent=4))

    order = compute_order(data)

    print_operation_plan(order, config)

    print("\n\n🚀 EXECUTING ALL COMMANDS...\n")
    execute_all(order, config)
    print("\n💥 PIPELINE COMPLETE.\n")


if __name__ == "__main__":
    main()
