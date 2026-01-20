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
from test_functions.delay_applicator import apply_delay
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent          # .../TESI/deploy_automation
REPO_ROOT  = SCRIPT_DIR.parent                        # .../TESI

DEPLOY_DIR   = REPO_ROOT / "deploy_automation"
RUNTIME_DIR  = REPO_ROOT / "runtime_results"

RUNTIME_FILE = str(RUNTIME_DIR / "runtime.log")
OUTPUT_JSON  = str(RUNTIME_DIR / "output.json")

DEPLOYER_SH  = DEPLOY_DIR / "deployer.sh"
APPLIER_PY   = DEPLOY_DIR / "applier.py"

DEBUG_SKIP_DEPLOY = False  # Set to True to skip deployer/applier for debugging
DELAY_SKIP = True # Set to True to skip delay application for testing

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
    with open(RUNTIME_FILE, "a") as f:w
        f.write(f"{label:<20} {formatted}\n")



# ================== Placement Logic ==================

def choose_algorithm(G):
    print("\n📘 Choose a placement algorithm:")
    print("1. Bruteforce")
    print("2. Greedy")
    print("3. Random ")
    print("4. Q-Learning ( not available yet )")
    print("5. GNN + Policy Gradient ( not available yet )")
    print("6. Exit")

    choice = input("Enter your choice (1-6): ")
    if choice == "6":
        print("Exiting...")
        sys.exit(0)
    if choice == "4" or choice == "5":
        print("⚠️ This algorithm is not available yet. Please choose another one.")
        return choose_algorithm(G)
    elif choice not in ["1", "2", "3", "4", "5"]:
        print("Invalid choice. Please try again.")
        return choose_algorithm(G)

    flag_splitting = input("Enable cluster splitting? (y/n): ").lower() == 'y'
    max_latency = int(input("Enter maximum latency (ms): "))

    start = time.perf_counter()

    if choice == "1":
        result = place_pdcs_bruteforce(G, max_latency, flag_splitting)
        label = "Placement-Bruteforce"        
    elif choice == "2":
        result = place_pdcs_greedy(G, max_latency, flag_splitting)
        label = "Placement-Greedy"        
    elif choice == "3":
        seed = int(input("Enter seed (default=42): ") or 42)
        result = place_pdcs_random(G, max_latency, seed, flag_splitting)
        label = "Placement-Random"        
    elif choice == "4":
        result = q_learning_placement(G, max_latency)
        label = "Placement-Q-Learn"   
    elif choice == "5":
        result = train_with_policy_gradient(G, max_latency)
        label = "Placement-GNN-PG"
    
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
    G = create_graph(seed=None, p_extra=0.45)
    draw_graph(G)
        
    while True:
        print("\n🔄 Updating network conditions...")
        modify_latency(G)
        modify_edge_status(G)
        modify_bandwidth(G)

        print("\n⚙️ Running placement algorithm...")

        total_start = time.perf_counter()

        pdcs, path, max_latency = choose_algorithm(G)
        print(f"✅ PDCs assigned in clusters: {', '.join(pdcs)}, CC")
        # Draw updated graph
        draw_graph(G, pdcs=pdcs, paths=path, max_latency=max_latency)
        # Save result to output.json (to feed deployer/applier)
        import json

        with open(OUTPUT_JSON, "w") as f:
            json.dump(
                {
                    "path": path,                     
                    "pdcs": sorted(list(pdcs)) + ["CC"],
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

        # --- Apply network delays ---
        if not DELAY_SKIP:
            print("🧪 TESTING MODE: applying delay.")
            apply_delay(G, OUTPUT_JSON)
        else:
            print("🧪 DEPLOY MODE: skipping delay application.")

        # Ask if user wants to continue
        cont = input("\n🔁 Repeat the process? (y/n): ").lower()
        if cont != 'y':
            print("👋 Exiting loop.")
            break


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(1))
    main()
