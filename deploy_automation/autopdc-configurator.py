#!/usr/bin/env python3
import json
import sys
from collections import defaultdict


def get_openpdc_port(cluster):
    """
    Placeholder: qui puoi inserire una vera tabella porte.
    """
    return 30000 + abs(hash(cluster)) % 1000


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

            # Propaga PMU al padre
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

    print(json.dumps(config, indent=4))


if __name__ == "__main__":
    main()
