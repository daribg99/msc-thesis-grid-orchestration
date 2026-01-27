#!/usr/bin/env python3
import subprocess
import sys
import signal
import os
import time
import json
from datetime import datetime
from pathlib import Path

from modelling_algorithms.modules.graph_model import (
    create_graph,
    modify_latency,
    modify_edge_status,
    modify_bandwidth,
)
from modelling_algorithms.modules.visualizer import draw_graph
from modelling_algorithms.modules.placement_pdc import (
    place_pdcs_greedy,
    place_pdcs_random,
    place_pdcs_bruteforce,
    q_learning_placement,
)
from modelling_algorithms.modules.gnn import train_with_policy_gradient

from test_functions.delay_applicator import apply_delay
from test_functions.snapshot import save_snapshot
from test_functions.metrics import (
    pdcs_set,
    churn,
    jaccard_distance,
    append_metrics_csv,
)
from test_functions.plotting import plot_pdc_topology_jaccard, plot_runtime_stacked_per_iteration, plot_total_iteration_boxplot_by_T


# ================== Paths ==================

SCRIPT_DIR = Path(__file__).resolve().parent          # .../TESI/deploy_automation
REPO_ROOT  = SCRIPT_DIR.parent                        # .../TESI

DEPLOY_DIR    = REPO_ROOT / "deploy_automation"
RUNTIME_ROOT  = REPO_ROOT / "runtime_results"
RUNS_DIR      = RUNTIME_ROOT / "runs"

DEPLOYER_SH   = DEPLOY_DIR / "deployer.sh"
APPLIER_PY    = DEPLOY_DIR / "applier.py"


# ================== Flags ==================

SKIP_DEPLOY = False   # True: skip deployer/applier
SKIP_DELAY = True   # True: skip delay application


# ================== Utility Functions ==================

def run_command(cmd, cwd=None):
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in process.stdout:
        print(line, end="")
    process.wait()
    return process.returncode


def format_hms(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {secs:05.2f}s"
    elif minutes > 0:
        return f"{minutes}m {secs:05.2f}s"
    else:
        return f"{secs*1000:.2f} ms"


def write_runtime(label: str, seconds: float, runtime_file: Path):
    """
    Append a runtime entry to the runtime_file of the current run.
    """
    formatted = format_hms(seconds)
    with open(runtime_file, "a") as f:
        f.write(f"{label:<20} {formatted}\n")


# ================== Placement Logic ==================

def choose_algorithm(G, runtime_file: Path):
    print("\n📘 Choose a placement algorithm:")
    print("1. Bruteforce")
    print("2. Greedy")
    print("3. Random")
    print("4. Q-Learning (not available yet)")
    print("5. GNN + Policy Gradient (not available yet)")
    print("6. Exit")

    choice = input("Enter your choice (1-6): ")
    if choice == "6":
        print("Exiting...")
        sys.exit(0)

    if choice in ("4", "5"):
        print("⚠️ This algorithm is not available yet. Please choose another one.")
        return choose_algorithm(G, runtime_file)

    if choice not in ("1", "2", "3"):
        print("Invalid choice. Please try again.")
        return choose_algorithm(G, runtime_file)

    flag_splitting = input("Enable cluster splitting? (y/n): ").lower() == "y"
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
    else:
        # unreachable due to checks, but keep safe
        print("Invalid choice.")
        return choose_algorithm(G, runtime_file)

    elapsed = time.perf_counter() - start
    write_runtime(label, elapsed, runtime_file)
    print(f"⏱️ {label} time (algorithm only): {format_hms(elapsed)}")

    return result


# ================== Main Loop ==================

def main():
    # --- Create a new run directory to keep history across executions ---
    os.makedirs(RUNS_DIR, exist_ok=True)
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    RUN_DIR = RUNS_DIR / run_id

    # Per-run directories
    snapshots_dir = RUN_DIR / "snapshots"
    plots_dir     = RUN_DIR / "plots"

    os.makedirs(RUN_DIR, exist_ok=True)
    os.makedirs(snapshots_dir, exist_ok=True)
    os.makedirs(plots_dir, exist_ok=True)

    # Per-run files
    metrics_csv  = RUN_DIR / "topology_change.csv"
    runtime_file = RUN_DIR / "runtime.csv"
    output_json  = RUN_DIR / "output.json"

    # Fresh runtime log for THIS run only
    with open(runtime_file, "w") as f:
        f.write("=== Runtime summary ===\n")

    if SKIP_DEPLOY:
        print("🧪 DEBUG MODE: deployer/applier will be skipped.")
    print(f"📁 Run directory: {RUN_DIR}")

    # --- topology monitoring state ---
    iteration = 0
    prev_pdcs = None

    print("🌐 Creating initial graph...\n")
    G = create_graph(seed=None, p_extra=0.45)
    draw_graph(G, output_path=plots_dir / "graph_initial.png")


    while True:
        print("\n🔄 Updating network conditions...")
        modify_latency(G)
        modify_edge_status(G)
        modify_bandwidth(G)

        print("\n⚙️ Running placement algorithm...")

        total_start = time.perf_counter()

        pdcs, path, max_latency = choose_algorithm(G, runtime_file)
        print(f"✅ PDCs assigned in clusters: {', '.join(pdcs)}, CC")

        # Draw updated graph (your draw_graph likely saves under runtime_results;
        # if you want it under RUN_DIR, extend draw_graph with an output_dir arg)
        graph_out = plots_dir / f"graph_T{iteration:03d}.png"
        draw_graph(G, pdcs=pdcs, paths=path, max_latency=max_latency, output_path=graph_out)
        print(f"🖼️ Graph saved to {graph_out}")


        # Build output dict once
        data = {
            "path": path,
            "pdcs": sorted(list(pdcs)) + ["CC"],
            "max_latency": max_latency,
        }

        # Save result to output.json (to feed deployer/applier)
        with open(output_json, "w") as f:
            json.dump(data, f, indent=4)
        print(f"💾 Results saved to {output_json}")

        # --- Save snapshot for this iteration ---
        snap_path = save_snapshot(iteration, data, snapshots_dir)
        print(f"🧾 Snapshot saved to {snap_path}")

        # --- Compute topology-change metrics (PDC set) ---
        curr_pdcs = pdcs_set(data, exclude_cc=True)

        if prev_pdcs is not None:
            c = churn(prev_pdcs, curr_pdcs)
            jd = jaccard_distance(prev_pdcs, curr_pdcs)
            added = len(curr_pdcs - prev_pdcs)
            removed = len(prev_pdcs - curr_pdcs)

            append_metrics_csv(
                metrics_csv,
                iteration,
                c,
                jd,
                added,
                removed,
            )

            print(
                f"📈 Change metric @T={iteration}: churn={c:.3f}, "
                f"jaccard_distance={jd:.3f} | +{added} -{removed}"
            )

        prev_pdcs = curr_pdcs
        iteration += 1

        # --- Run deployer and applier ---
        if not SKIP_DEPLOY:
            steps = [
                (["bash", str(DEPLOYER_SH), str(output_json)], "Deployer"),
                (["python3", "-u", str(APPLIER_PY), str(output_json)], "Applier"),
            ]

            for cmd, label in steps:
                print(f"\n🚀 Executing {label}: {' '.join(cmd)}\n")
                start = time.perf_counter()
                code = run_command(cmd, cwd=str(REPO_ROOT))
                end = time.perf_counter()
                elapsed = end - start
                write_runtime(label, elapsed, runtime_file)

                if code != 0:
                    print(f"❌ {label} failed with exit code {code}. Aborting this iteration.")
                    break

                print(f"✅ {label} completed successfully!")

        total_elapsed = time.perf_counter() - total_start
        write_runtime("Total Iteration", total_elapsed, runtime_file)
        print(f"\n🕒 Total iteration time: {format_hms(total_elapsed)}")

        # --- Apply network delays ---
        if not SKIP_DELAY:
            print("🧪 TESTING MODE: applying delay.")
            apply_delay(G, str(output_json))
        else:
            print("🧪 DEPLOY MODE: skipping delay application.")

        # Ask if user wants to continue
        cont = input("\n🔁 Repeat the process? (y/n): ").lower()
        if cont != "y":
            print("👋 Exiting loop.")

            # --- Plots for THIS run ---
            if not SKIP_DEPLOY:
                if metrics_csv.exists():
                    plot_pdc_topology_jaccard(metrics_csv, output_dir=plots_dir)

                if runtime_file.exists():
                    plot_runtime_stacked_per_iteration(runtime_file, output_dir=plots_dir)
                    plot_total_iteration_boxplot_by_T(RUNS_DIR, output_dir=RUNTIME_ROOT)

            break


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(1))
    main()
