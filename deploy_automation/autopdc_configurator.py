#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple

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
    q_learning_placement,          # unused for now
)
from modelling_algorithms.modules.gnn import train_with_policy_gradient  # unused for now

from test_functions.delay_applicator import apply_delay
from test_functions.snapshot import save_snapshot
from test_functions.metrics import (
    pdcs_set,
    churn,
    jaccard_distance,
    append_metrics_csv,
)
from test_functions.plotting import (
    plot_jaccard_singlerun,
    plot_runtime_singlerun,
    plot_runtime_boxplot,
    plot_jaccard_boxplot,
)

# ================== Paths ==================
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT  = SCRIPT_DIR.parent

DEPLOY_DIR    = REPO_ROOT / "deploy_automation"
RUNTIME_ROOT  = REPO_ROOT / "runtime_results"
RUNS_DIR      = RUNTIME_ROOT / "runs"

DEPLOYER_SH   = DEPLOY_DIR / "deployer.sh"
APPLIER_PY    = DEPLOY_DIR / "applier.py"


# ================== Utilities ==================

def run_command(cmd: list[str], cwd: Optional[str] = None) -> int:
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
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
    if minutes > 0:
        return f"{minutes}m {secs:05.2f}s"
    return f"{secs * 1000:.2f} ms"


def write_runtime(runtime_file: Path, label: str, seconds: float) -> None:
    with open(runtime_file, "a") as f:
        f.write(f"{label:<20} {format_hms(seconds)}\n")


@dataclass(frozen=True)
class PlacementResult:
    pdcs: set
    paths: list
    max_latency: int
    alg_label: str


def prompt_yes_no(msg: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    ans = input(msg + suffix).strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


def prompt_int(msg: str, default: Optional[int] = None) -> int:
    while True:
        raw = input(f"{msg}" + (f" (default={default}): " if default is not None else ": ")).strip()
        if not raw and default is not None:
            return default
        try:
            return int(raw)
        except ValueError:
            print("Invalid integer, try again.")


# ================== Placement Logic ==================

def choose_algorithm(G, runtime_file: Path) -> PlacementResult:
    menu = (
        "\n📘 Choose a placement algorithm:\n"
        "1. Bruteforce\n"
        "2. Greedy\n"
        "3. Random\n"
        "4. Q-Learning (not available yet)\n"
        "5. GNN + Policy Gradient (not available yet)\n"
        "6. Exit\n"
    )

    while True:
        print(menu)
        choice = input("Enter your choice (1-6): ").strip()

        if choice == "6":
            print("Exiting...")
            sys.exit(0)

        if choice in ("4", "5"):
            print("⚠️ This algorithm is not available yet. Please choose another one.")
            continue

        if choice not in ("1", "2", "3"):
            print("Invalid choice. Please try again.")
            continue

        flag_splitting = prompt_yes_no("Enable cluster splitting?", default=False)
        max_latency = prompt_int("Enter maximum latency (ms)")

        start = time.perf_counter()

        if choice == "1":
            pdcs, paths, Lmax = place_pdcs_bruteforce(G, max_latency, flag_splitting)
            label = "Placement-Bruteforce"
        elif choice == "2":
            pdcs, paths, Lmax = place_pdcs_greedy(G, max_latency, flag_splitting)
            label = "Placement-Greedy"
        else:  # "3"
            seed = prompt_int("Enter seed", default=42)
            pdcs, paths, Lmax = place_pdcs_random(G, max_latency, seed, flag_splitting)
            label = "Placement-Random"

        elapsed = time.perf_counter() - start
        write_runtime(runtime_file, label, elapsed)
        print(f"⏱️ {label} time (algorithm only): {format_hms(elapsed)}")

        return PlacementResult(pdcs=set(pdcs), paths=paths, max_latency=Lmax, alg_label=label)


# ================== Main ==================

def main(
    *,
    skip_deploy: bool = True,
    skip_delay: bool = True,
    # create_graph params
    num_candidates: int = 15,
    num_pmus: int = 3,
    seed: int | None = None,
    p_extra: float = 0.25,
    cc_min_links: int = 2,
    cc_max_links: int | None = None,
    pmu_links: int = 1,
    plots: bool = False,
) -> None:
    os.makedirs(RUNS_DIR, exist_ok=True)
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id

    snapshots_dir = run_dir / "snapshots"
    plots_dir     = run_dir / "plots"
    os.makedirs(snapshots_dir, exist_ok=True)
    os.makedirs(plots_dir, exist_ok=True)

    metrics_csv  = run_dir / "topology_change.csv"
    runtime_file = run_dir / "runtime.csv"

    with open(runtime_file, "w") as f:
        f.write("=== Runtime summary ===\n")

    if skip_deploy:
        print("🧪 DEBUG MODE: deployer/applier will be skipped.")
    if skip_delay:
        print("🧪 DEBUG MODE: delay application will be skipped.")
    print(f"📁 Run directory: {run_dir}")

    # --- block metrics state (per algorithm) ---
    current_alg: Optional[str] = None
    prev_pdcs_block: Optional[set] = None
    block_T = 0

    iteration = 0

    print("🌐 Creating initial graph...\n")
    G = create_graph(
        num_candidates=num_candidates,
        num_pmus=num_pmus,
        seed=seed,
        p_extra=p_extra,
        cc_min_links=cc_min_links,
        cc_max_links=cc_max_links,
        pmu_links=pmu_links,
    )
    draw_graph(G, output_path=plots_dir / "graph_initial.png")

    while True:
        print("\n🔄 Updating network conditions...")
        lat_ops = modify_latency(G)
        st_ops  = modify_edge_status(G)
        bw_ops  = modify_bandwidth(G)
        ops_applied = lat_ops + st_ops + bw_ops

        print("\n⚙️ Running placement algorithm...")
        total_start = time.perf_counter()

        placement = choose_algorithm(G, runtime_file)
        print(f"✅ PDCs assigned in clusters: {', '.join(sorted(placement.pdcs))}, CC")

        graph_out = plots_dir / f"graph_T{iteration:03d}.png"
        draw_graph(G, pdcs=placement.pdcs, paths=placement.paths, max_latency=placement.max_latency, output_path=graph_out)
        print(f"🖼️ Graph saved to {graph_out}")

        data = {
            "path": placement.paths,
            "pdcs": sorted(list(placement.pdcs)) + ["CC"],
            "max_latency": placement.max_latency,
            "ops_applied": ops_applied,
            "topology_seed": seed,
        }

        snap_path = save_snapshot(iteration, data, snapshots_dir)
        print(f"🧾 Snapshot saved to {snap_path}")

        curr_pdcs = pdcs_set(data, exclude_cc=True)

        if current_alg != placement.alg_label:
            current_alg = placement.alg_label
            prev_pdcs_block = curr_pdcs
            block_T = 0
            append_metrics_csv(
                metrics_csv,
                block_T,
                0.0,
                0.0,
                0,
                0,
                algorithm=current_alg,
                note=f"first iteration for {current_alg}",
            )
        else:
            assert prev_pdcs_block is not None
            block_T += 1
            c = churn(prev_pdcs_block, curr_pdcs) # not used
            jd = jaccard_distance(prev_pdcs_block, curr_pdcs)
            added = len(curr_pdcs - prev_pdcs_block)
            removed = len(prev_pdcs_block - curr_pdcs)

            append_metrics_csv(
                metrics_csv,
                block_T,
                c,
                jd,
                added,
                removed,
                algorithm=current_alg,
                note="",
            )
            prev_pdcs_block = curr_pdcs

        iteration += 1

        # --- deployer + applier ---
        if not skip_deploy:
            steps = [
                (["bash", str(DEPLOYER_SH), str(snap_path)], "Deployer"),
                (["python3", "-u", str(APPLIER_PY), str(snap_path)], "Applier"),
            ]
            for cmd, label in steps:
                print(f"\n🚀 Executing {label}: {' '.join(cmd)}\n")
                start = time.perf_counter()
                code = run_command(cmd, cwd=str(REPO_ROOT))
                elapsed = time.perf_counter() - start
                write_runtime(runtime_file, label, elapsed)

                if code != 0:
                    print(f"❌ {label} failed with exit code {code}. Aborting this iteration.")
                    break
                print(f"✅ {label} completed successfully!")

        total_elapsed = time.perf_counter() - total_start
        write_runtime(runtime_file, "Total Iteration", total_elapsed)
        print(f"\n🕒 Total iteration time: {format_hms(total_elapsed)}")

        # --- delay application ---
        if not skip_delay:
            print("🧪 TESTING MODE: applying delay.")
            apply_delay(G, str(snap_path))
        else:
            print("🧪 DEPLOY MODE: skipping delay application.")

        if not prompt_yes_no("\n🔁 Repeat the process?", default=False):
            print("👋 Exiting loop.")            
            break


def parse_args():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--skip-deploy", action="store_true", default=True)
    p.add_argument("--no-skip-deploy", dest="skip_deploy", action="store_false")
    p.add_argument("--skip-delay", action="store_true", default=True)
    p.add_argument("--no-skip-delay", dest="skip_delay", action="store_false")

    p.add_argument("--num-candidates", type=int, default=15)
    p.add_argument("--num-pmus", type=int, default=3)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--p-extra", type=float, default=0.25)
    p.add_argument("--cc-min-links", type=int, default=2)
    p.add_argument("--cc-max-links", type=int, default=None)
    p.add_argument("--pmu-links", type=int, default=1)
    return p.parse_args()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(1))
    args = parse_args()

    main(
        skip_deploy=args.skip_deploy,
        skip_delay=args.skip_delay,
        num_candidates=args.num_candidates,
        num_pmus=args.num_pmus,
        seed=args.seed,
        p_extra=args.p_extra,
        cc_min_links=args.cc_min_links,
        cc_max_links=args.cc_max_links,
        pmu_links=args.pmu_links,
    )
