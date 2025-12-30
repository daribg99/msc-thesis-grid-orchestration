#!/usr/bin/env python3
import subprocess
import sys
import signal
import os
import time

from modelling_algorithms.modules.graph_model import create_graph, modify_latency, modify_edge_status, modify_bandwidth
from modelling_algorithms.modules.visualizer import draw_graph
from modelling_algorithms.modules.placement_pdc import place_pdcs_greedy, place_pdcs_random, place_pdcs_bruteforce, q_learning_placement
from modelling_algorithms.modules.gnn import train_with_policy_gradient

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent          # .../TESI/deploy_automation
REPO_ROOT  = SCRIPT_DIR.parent                        # .../TESI

DEPLOY_DIR   = REPO_ROOT / "deploy_automation"
RUNTIME_DIR  = REPO_ROOT / "runtime_results"

RUNTIME_FILE = str(RUNTIME_DIR / "runtime.log")
OUTPUT_JSON  = str(RUNTIME_DIR / "output.json")

DEPLOYER_SH  = DEPLOY_DIR / "deployer.sh"
APPLIER_PY   = DEPLOY_DIR / "applier.py"

DEBUG_SKIP_DEPLOY = True  # Set to True to skip deployer/applier for debugging

# ================== Utility Functions ==================

def run_command(cmd, cwd=None):
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    for line in process.stdout:
        print(line, end="")
    process.wait()
    return process.returncode



def format_hms(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {secs:05.2f}s"
    elif minutes > 0:
        return f"{minutes}m {secs:05.2f}s"
    else:
        return f"{secs*1000:.2f} ms"


def write_runtime(label, seconds):
    formatted = format_hms(seconds)
    with open(RUNTIME_FILE, "a") as f:
        f.write(f"{label:<20} {formatted}\n")

def normalize_paths(path_dict):
    cluster_ids = set()
    for pmu_info in path_dict.values():
        for node in pmu_info["path"]:
            if node.startswith("N"):
                cluster_ids.add(int(node[1:]))

    cc_cluster_id = max(cluster_ids) + 1 if cluster_ids else 1

    def normalize_node(node):
        if node.startswith("PMU"):
            return f"PMU-{node[3:]}"
        elif node.startswith("N"):
            return f"cluster{node[1:]}"
        elif node == "CC":
            return f"cluster{cc_cluster_id}"
        else:
            return node

    # Costruisce SOLO la lista dei paths normalizzati
    return [
        [normalize_node(n) for n in pmu_info["path"]]
        for pmu_info in path_dict.values()
    ]

# ================== Placement Logic ==================

def choose_algorithm(G):
    print("\n📘 Choose a placement algorithm:")
    print("1. Greedy (with maximum latency)")
    print("2. Random (with specified number of PDCs)")
    print("3. Q-Learning")
    print("4. GNN + Policy Gradient")
    print("5. Bruteforce")
    print("6. Exit")

    choice = input("Enter your choice (1-6): ")
    if choice == "6":
        print("Exiting...")
        sys.exit(0)
    elif choice not in ["1", "2", "3", "4", "5"]:
        print("Invalid choice. Please try again.")
        return choose_algorithm(G)

    flag_splitting = input("Enable cluster splitting? (y/n): ").lower() == 'y'
    max_latency = int(input("Enter maximum latency (ms): "))

    # ⏱️ Start timer ONLY for the algorithm execution (no user input time)
    start = time.perf_counter()

    if choice == "1":
        result = place_pdcs_greedy(G, max_latency, flag_splitting)
        label = "Placement(Greedy)"
    elif choice == "2":
        seed = int(input("Enter seed (default=42): ") or 42)
        result = place_pdcs_random(G, max_latency, seed, flag_splitting)
        label = "Placement(Random)"
    elif choice == "3":
        result = q_learning_placement(G, max_latency)
        label = "Placement(Q-Learn)"
    elif choice == "4":
        result = train_with_policy_gradient(G, max_latency)
        label = "Placement(GNN-PG)"
    elif choice == "5":
        result = place_pdcs_bruteforce(G, max_latency, flag_splitting)
        label = "Placement(Bruteforce)"

    elapsed = time.perf_counter() - start
    write_runtime(label, elapsed)
    print(f"⏱️ {label} time (algorithm only): {format_hms(elapsed)}")

    return result


# ================== Main Loop ==================

def main():

    os.makedirs(RUNTIME_DIR, exist_ok=True)

    if DEBUG_SKIP_DEPLOY:
        print("🧪 DEBUG MODE: deployer/applier will be skipped.")
        
    with open(RUNTIME_FILE, "w") as f:
        f.write("=== Runtime summary ===\n")

    print("🌐 Creating initial graph...\n")
    G = create_graph(num_candidates=5, num_pmus=3, seed=None)
    draw_graph(G)
        
    while True:
        print("\n🔄 Updating network conditions...")
        modify_latency(G)
        modify_edge_status(G)
        modify_bandwidth(G)

        print("\n⚙️ Running placement algorithm...")

        total_start = time.perf_counter()

        pdcs, path, max_latency = choose_algorithm(G)
        print("✅ PDCs assigned in clusters:", pdcs)
        # Draw updated graph
        draw_graph(G, pdcs=pdcs, paths=path, max_latency=max_latency)
        # Save result to output.json (to feed deployer/applier)
        import json
        paths_list = normalize_paths(path)

        with open(OUTPUT_JSON, "w") as f:
            json.dump(
                {
                    "path": path,                     
                    "paths": paths_list,               
                    "pdcs": sorted(list(pdcs)),
                    "max_latency": max_latency
                },
                f,
                indent=4
            )

        print(f"💾 Results saved to {OUTPUT_JSON}")

        # --- Run deployer and applier ---
        if not DEBUG_SKIP_DEPLOY:
            steps = [
                (["bash", str(DEPLOYER_SH), OUTPUT_JSON], "Deployer"),
                (["python3", "-u", str(APPLIER_PY), OUTPUT_JSON], "Applier"),
            ]

            for cmd, label in steps:
                print(f"\n🚀 Executing {label}: {' '.join(cmd)}\n")
                start = time.perf_counter()
                code = run_command(cmd, cwd=str(REPO_ROOT))
                end = time.perf_counter()
                elapsed = end - start
                write_runtime(label, elapsed)

                if code != 0:
                    print(f"❌ {label} failed with exit code {code}. Aborting this iteration.")
                    break

                print(f"✅ {label} completed successfully!")

        total_end = time.perf_counter()
        total_elapsed = total_end - total_start
        write_runtime("Total Iteration", total_elapsed)
        print(f"\n🕒 Total iteration time: {format_hms(total_elapsed)}")


        # Ask if user wants to continue
        cont = input("\n🔁 Repeat the process? (y/n): ").lower()
        if cont != 'y':
            print("👋 Exiting loop.")
            break


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(1))
    main()
