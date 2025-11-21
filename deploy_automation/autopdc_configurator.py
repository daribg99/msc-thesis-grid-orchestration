#!/usr/bin/env python3
import json
import sys
from collections import defaultdict, deque


def get_openpdc_port(cluster):
    """
    Placeholder: qui puoi inserire una vera tabella porte.
    """
    return 30000 + abs(hash(cluster)) % 1000


# --------------------------------------------------------
#   Construction of PDC configuration from paths
# --------------------------------------------------------

def build_pdc_topology(paths_json):
    paths = paths_json["paths"]

    # final dictionary
    config = {}

    # === 1) Initialization of clusters ===
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

        # leaf cluster (second element in path)
        leaf = clusters[0]
        config[leaf]["pmu_direct"].append(pmu)
        config[leaf]["outputstream"].add(pmu)

    # === 2) Propagation of PMU and creation of connections ===
    for path in paths:
        pmu = path[0]
        clusters = path[1:]

        for i in range(1, len(clusters)):
            child = clusters[i - 1]
            parent = clusters[i]

            # Propagate PMU to the parent
            config[parent]["outputstream"].add(pmu)

            existing = None
            for conn in config[parent]["connections_downstream"]:
                if conn["node"] == child:
                    existing = conn
                    break

            if existing:
                # add PMU to the list, avoiding duplicates
                if pmu not in existing["pmus"]:
                    existing["pmus"].append(pmu)
            else:
                # create a new downstream connection
                config[parent]["connections_downstream"].append({
                    "node": child,
                    "pmus": [pmu],
                    "port": get_openpdc_port(child)
                })

    # === 3) Convert sets to lists ===
    for c in config:
        config[c]["outputstream"] = list(config[c]["outputstream"])

    return config


# --------------------------------------------------------
#   Construction of dependencies (only on PATHS)
# --------------------------------------------------------

def compute_order(paths_json):
    paths = paths_json["paths"]

    deps = defaultdict(set)    # parent -> children that must come BEFORE
    all_clusters = set()

    for path in paths:
        pmu = path[0]
        nodes = path[1:]   # cluster1, cluster3, cluster6 ...

        # nodes seen
        for n in nodes:
            all_clusters.add(n)

        # create dependencies
        for i in range(1, len(nodes)):
            child = nodes[i - 1]
            parent = nodes[i]
            deps[parent].add(child)

    # be sure all clusters are in deps
    for c in all_clusters:
        if c not in deps:
            deps[c] = set()

    # --- Topological sort ---
    in_degree = {c: 0 for c in all_clusters} # count of requisites on each node

    for parent, children in deps.items():
        for child in children:
            in_degree[parent] += 1

    # nodes without dependencies
    queue = deque([c for c in all_clusters if in_degree[c] == 0])
    order = []

    # Kahn's algorithm for topological sorting: extract nodes with minimum in-degree
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
#   Print operation plan
# --------------------------------------------------------

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

    # PRINT CONFIG
    print("=== CONFIG GENERATED ===")
    print(json.dumps(config, indent=4))

    # COMPUTE ORDER
    order = compute_order(data)

    # PRINT ORDER
    print_operation_plan(order, config)


if __name__ == "__main__":
    main()
