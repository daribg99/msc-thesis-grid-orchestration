#!/usr/bin/env python3
import json
import random
import re
import shutil
import subprocess
import time
import sys
#from test_functions.plotting import plot_time_vs_nodes,plot_box_plot_time_vs_nodes, plot_pdcs_vs_candidates_bar
from test_functions.plotting import plot_mode2_all_plots, plot_mode1_all_plots

from pathlib import Path
from typing import List, Tuple

import pexpect

# ---------------- CONFIG - 1 ----------------
RUNS = 3
TS_PER_RUN = 5                  # T0,T1,T2
ALGORITHMS = ["1", "2", "3"]     # bruteforce, greedy, random
CHANGES_PER_T = 1

SPLITTING = "n"
MAX_LATENCY = "80"

# change ranges
LAT_MIN, LAT_MAX = 10.0, 25.0
BW_MIN, BW_MAX = 50, 300
STATUS_CHOICES = ["down"]

# ---------------- CONFIG -2 ----------------

# ---- Mode 2 sweep (FIXED, no input) ----
MODE2_CANDIDATES_SEQ = [10, 20, 30, 40]
MODE2_PMUS_SEQ       = [1, 2, 3, 4]   

MODE2_P_EXTRA = 0.45
MODE2_CC_MIN_LINKS = 2
MODE2_PMU_LINKS = 1


# command (module)


RUN_DIR_RE = re.compile(r"Run directory:\s*(/.*)", re.IGNORECASE)

def build_cmd(
    *,
    skip_deploy=True,
    skip_delay=True,
    num_candidates=8,
    num_pmus=4,
    seed=None,
    p_extra=0.35,
    cc_min_links=2,
    cc_max_links=None,
    pmu_links=1,
):
    cmd = [
        "python3", "-u", "-m", "deploy_automation.autopdc_configurator"
    ]

    if not skip_deploy:
        cmd.append("--no-skip-deploy")
    if not skip_delay:
        cmd.append("--no-skip-delay")

    cmd += [
        "--num-candidates", str(num_candidates),
        "--num-pmus", str(num_pmus),
        "--p-extra", str(p_extra),
        "--cc-min-links", str(cc_min_links),
        "--pmu-links", str(pmu_links),
    ]

    if seed is not None:
        cmd += ["--seed", str(seed)]

    if cc_max_links is not None:
        cmd += ["--cc-max-links", str(cc_max_links)]

    return cmd

def _parse_time_to_ms(s: str) -> float | None:
    
    s = s.strip().replace("\r", "").replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)

    # "123.45 ms"
    m = re.fullmatch(r"([\d.]+)\s*ms", s)
    if m:
        return float(m.group(1))

    # "12.34s" or "12.34 s"
    m = re.fullmatch(r"([\d.]+)\s*s", s)
    if m:
        return float(m.group(1)) * 1000.0

    # "17m 40.11s"
    m = re.fullmatch(r"(\d+)\s*m\s*([\d.]+)\s*s", s)
    if m:
        minutes = int(m.group(1))
        seconds = float(m.group(2))
        return (minutes * 60.0 + seconds) * 1000.0

    # "1h 02m 03.45s"
    m = re.fullmatch(r"(\d+)\s*h\s*(\d+)\s*m\s*([\d.]+)\s*s", s)
    if m:
        hours = int(m.group(1))
        minutes = int(m.group(2))
        seconds = float(m.group(3))
        return (hours * 3600.0 + minutes * 60.0 + seconds) * 1000.0

    return None

# ---------------- RUN MODE 1 ----------------
def latest_snapshot_edges(run_dir: Path) -> List[Tuple[str, str]]:
    snaps_dir = run_dir / "snapshots"
    if not snaps_dir.exists():
        print(f"[DEBUG] snapshots dir missing: {snaps_dir}")
        return []

    snaps = list(snaps_dir.glob("snapshot_*.json"))
    if not snaps:
        print(f"[DEBUG] no snapshots found in: {snaps_dir}")
        return []

    # Ordina per indice nel nome (snapshot_0000_..., snapshot_0001_...)
    def snap_index(p: Path) -> int:
        m = re.search(r"snapshot_(\d+)", p.name)  # permissivo
        return int(m.group(1)) if m else -1

    snaps.sort(key=lambda p: (snap_index(p), p.stat().st_mtime))
    latest = snaps[-1]

    try:
        data = json.loads(latest.read_text())
    except Exception as e:
        print(f"[DEBUG] failed reading snapshot {latest}: {e}")
        return []

    paths = data.get("path", None)
    if not isinstance(paths, dict):
        print(f"[DEBUG] snapshot {latest.name} has no dict 'path' (type={type(paths)})")
        return []

    edges = set()
    for pmu, info in paths.items():
        nodes = (info or {}).get("path", [])
        if len(nodes) < 2:
            continue
        for i in range(len(nodes) - 1):
            if i == 0:
                continue  # skip PMU->first
            u, v = nodes[i], nodes[i + 1]
            edges.add(tuple(sorted((u, v))))

    print(f"[DEBUG] latest snapshot picked: {latest.name} | pmus={len(paths)} | edges={len(edges)}")
    return list(edges)



def build_ops(edges: List[Tuple[str, str]]) -> List[dict]:
    if not edges:
        return []
    k = min(CHANGES_PER_T, len(edges))
    chosen = random.sample(edges, k=k)
    ops = []
    for (u, v) in chosen:
        t = random.choice(["latency", "status", "bandwidth"])
        if t == "latency":
            val = round(random.uniform(LAT_MIN, LAT_MAX), 2)
        elif t == "bandwidth":
            val = random.randint(BW_MIN, BW_MAX)
        else:
            val = random.choice(STATUS_CHOICES)
        ops.append({"type": t, "u": u, "v": v, "value": val})
    return ops


def pop_ops(ops: List[dict], t: str):
    picked = [op for op in ops if op["type"] == t]
    rest = [op for op in ops if op["type"] != t]
    return picked, rest


def cleanup():
    print("\n🧹 Cleaning k3d clusters and kubeconfigs...")
    subprocess.run(["k3d", "cluster", "delete", "--all"], check=False)
    shutil.rmtree("deploy_automation/kubeconfigs", ignore_errors=True)
    print("🧼 Cleanup completed.\n")

def _find_snapshot_for_iter(run_dir: Path, it: int) -> Path | None:
    snaps_dir = run_dir / "snapshots"
    if not snaps_dir.exists():
        return None
    snaps = sorted(snaps_dir.glob(f"snapshot_{it:04d}_*.json"))
    return snaps[-1] if snaps else None


def _load_ops_applied(run_dir: Path, it: int) -> list[dict]:
    p = _find_snapshot_for_iter(run_dir, it)
    if p is None:
        return []
    try:
        data = json.loads(p.read_text())
    except Exception:
        return []
    ops = data.get("ops_applied", [])
    return ops if isinstance(ops, list) else []


def build_undo_last_T(run_dir: Path, last_done_iter: int) -> list[dict]:
    k = TS_PER_RUN - 1
    if last_done_iter <= 0 or k <= 0:
        return []

    # loaded ops from snapshot: [last_done_iter, last_done_iter-1, ..., last_done_iter-(k-1)]
    start_it = last_done_iter - (k - 1)
    if start_it < 1:
        start_it = 1  # T0 has not modification

    ops: list[dict] = []
    for it in range(start_it, last_done_iter + 1):
        ops.extend(_load_ops_applied(run_dir, it))

    undo: list[dict] = []
    for op in reversed(ops):
        try:
            undo.append({
                "type": op["type"],   # latency/status/bandwidth
                "u": op["u"],
                "v": op["v"],
                "value": op["before"],  
            })
        except Exception:
            continue

    return undo


def run_one_main_run(
    *,
    skip_deploy=True,
    skip_delay=True,
    num_candidates=8,
    num_pmus=4,
    seed=None,
    p_extra=0.35,
    pmu_links=1,
):
    global_iter = 0   

    cmd = build_cmd(
        skip_deploy=skip_deploy,
        skip_delay=skip_delay,
        num_candidates=num_candidates,
        num_pmus=num_pmus,
        seed=seed,
        p_extra=p_extra,
        pmu_links=pmu_links,
    )

    #print(f"[DEBUG] spawning: {' '.join(cmd)}")

    #child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", timeout=None)
    #child.logfile_read = sys.stdout
    child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", timeout=None)
    child.logfile_read = None


    run_dir = None

    T = 0
    algo_idx = 0
    pending_ops: List[dict] = []  

    def send(line: str):
        child.sendline(line)

    while True:
        idx = child.expect([
            r"📁 Run directory: [^\r\n]+\r?\n",                         # 0
            r"Do you want to modify a latency\? \(y/n\):\s*",            # 1
            r"Do you want to modify the status of an edge\? \(y/n\):\s*",# 2
            r"Do you want to modify a bandwidth\? \(y/n\):\s*",          # 3
            r"Enter your choice \(1-6\):\s*",                            # 4
            r"Enable cluster splitting\?.*\s*",                          # 5
            r"Enter maximum latency.*\s*",                              # 6
            r"Enter seed \(default=42\):\s*",                            # 7
            r"Repeat the process\?.*\s*",                                # 8
            pexpect.EOF,                                                 # 9
        ])

        if idx == 0:
            # child.after contains the matched line
            line = child.after.strip()

            marker = "Run directory:"
            if marker in line:
                path_str = line.split(marker, 1)[1].strip()
                run_dir = Path(path_str).expanduser()
                print(f"[DEBUG] run_dir set to: {run_dir}")
            else:
                print(f"[DEBUG] failed to parse run_dir from line: {repr(line)}")
            continue

        if idx == 1:  # latency
            picked, pending_ops = pop_ops(pending_ops, "latency")
            if not picked:
                send("n")
            else:
                for op in picked:
                    send("y")
                    child.expect(r"Node 1:\s*")
                    send(op["u"])
                    child.expect(r"Node 2:\s*")
                    send(op["v"])
                    child.expect(r"Enter new latency.*:")
                    send(str(op["value"]))
                child.expect(r"Do you want to modify a latency\? \(y/n\):\s*")
                send("n")
            continue

        if idx == 2:  # status
            picked, pending_ops = pop_ops(pending_ops, "status")
            if not picked:
                send("n")
            else:
                for op in picked:
                    send("y")
                    child.expect(r"Node 1:\s*")
                    send(op["u"])
                    child.expect(r"Node 2:\s*")
                    send(op["v"])
                    child.expect(r"Enter new status.*:")
                    send(str(op["value"]))
                child.expect(r"Do you want to modify the status of an edge\? \(y/n\):\s*")
                send("n")
            continue

        if idx == 3:  # bandwidth
            picked, pending_ops = pop_ops(pending_ops, "bandwidth")
            if not picked:
                send("n")
            else:
                for op in picked:
                    send("y")
                    child.expect(r"Node 1:\s*")
                    send(op["u"])
                    child.expect(r"Node 2:\s*")
                    send(op["v"])
                    child.expect(r"Enter new bandwidth.*:")
                    send(str(op["value"]))
                child.expect(r"Do you want to modify a bandwidth\? \(y/n\):\s*")
                send("n")
            continue

        if idx == 4:  # choice (algorithm)
            print(f"\n🧠 Starting ALG={ALGORITHMS[algo_idx]} at T={T}\n")
            send(ALGORITHMS[algo_idx])
            continue

        if idx == 5:  # splitting
            send(SPLITTING)
            continue

        if idx == 6:  # max latency
            send(MAX_LATENCY)
            continue

        if idx == 7:  # seed 
            if ALGORITHMS[algo_idx] == "3":
                send("")  # empty -> default 42
            else:
                send("")  # safe
            continue

        if idx == 8:  # repeat
            # Finish one global iteration
            global_iter += 1

            # Finish one T of the current algorithm
            T += 1

            if T < TS_PER_RUN:
                # Changes for next T
                if run_dir is not None:
                    edges = []
                    for _ in range(10):  # ~2 sec
                        edges = latest_snapshot_edges(run_dir)
                        if edges:
                            break
                        time.sleep(0.2)
                    pending_ops = build_ops(edges)
                else:
                    pending_ops = []

                print(f"\n🔧 Planned ops for next T={T} (ALG={ALGORITHMS[algo_idx]}): {pending_ops}\n")
                send("y")
                continue

            # next algorithm
            algo_idx += 1


            if algo_idx < len(ALGORITHMS):
                undo_ops: List[dict] = []

                # undo
                if run_dir is not None and global_iter >= 2:
                    last_done = global_iter - 1
                    undo_ops = build_undo_last_T(run_dir, last_done)
                    print(f"\n↩️ Prepared UNDO from snapshots (last_done={last_done}): {undo_ops}\n")
                else:
                    print("\n↩️ UNDO skipped (not enough history yet)\n")

                cleanup()

                # Reset run_dir and T for the next algorithm
                T = 0
                pending_ops = undo_ops
                print(f"\n➡️ Switching to ALG={ALGORITHMS[algo_idx]} (reset T=0)\n")
                send("y")
                continue

            send("n")
            continue



        if idx == 9:  # EOF
            break

    child.close()
    return child.exitstatus if child.exitstatus is not None else 0

# ---------------- RUN MODE 2 ----------------

def parse_total_iteration_per_algo(runtime_csv: Path) -> dict[str, float]:
   
    placement_re = re.compile(
        r"^Placement-(Greedy|Bruteforce|Random)\s+(.+?)\s*$",
        re.IGNORECASE
    )

    totals_ms: dict[str, float] = {}

    with open(runtime_csv, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("==="):
                continue

            line = line.replace("\u00a0", " ")
            line = " ".join(line.split())

            m = placement_re.match(line)
            if not m:
                continue

            algo = m.group(1).capitalize()
            if algo in totals_ms:
                continue  

            time_str = m.group(2)  
            ms = _parse_time_to_ms(time_str)
            if ms is not None:
                totals_ms[algo] = ms

    required = ["Bruteforce", "Greedy", "Random"]
    if not all(a in totals_ms for a in required):
        raise ValueError(f"Missing placement times in {runtime_csv}: found={totals_ms}")

    return {k: v / 1000.0 for k, v in totals_ms.items()}  # seconds



def run_one_size_no_changes(*, num_candidates: int, num_pmus: int):
    cmd = build_cmd(
        skip_deploy=True,
        skip_delay=True,
        num_candidates=num_candidates,
        num_pmus=num_pmus,
        p_extra=0.30,
        cc_min_links=2,
        pmu_links=1,
        seed=None,
    )

    print(f"[DEBUG] spawning: {' '.join(cmd)}")
    child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", timeout=None)
    child.logfile_read = sys.stdout

    run_dir: Path | None = None
    algo_idx = 0  # 0..2

    def send(x: str):
        child.sendline(x)

    while True:
        idx = child.expect([
            r"📁 Run directory:\s*[^\r\n]+\r?\n",                               # 0
            r"Do you want to modify a latency\? \(y/n\):\s*",                  # 1
            r"Do you want to modify the status of an edge\? \(y/n\):\s*",      # 2
            r"Do you want to modify a bandwidth\? \(y/n\):\s*",                # 3
            r"Enter your choice \(1-6\):\s*",                                  # 4
            r"Enable cluster splitting\?.*\s*",                         # 5
            r"Enter maximum latency.*\s*",                                    # 6
            r"Enter seed \(default=42\):\s*",                                  # 7
            r"Repeat the process\?.*\s*",                               # 8
            pexpect.EOF,                                                       # 9
        ])

        if idx == 0:
            line = child.after.strip()
            marker = "Run directory:"
            if marker in line:
                run_dir = Path(line.split(marker, 1)[1].strip()).expanduser()
                print(f"[DEBUG] run_dir set to: {run_dir}")
            continue

        if idx in (1, 2, 3):
            send("n")
            continue

        if idx == 4:  
            send(ALGORITHMS[algo_idx])  
            continue

        if idx == 5:  # splitting
            send(SPLITTING)  
            continue

        if idx == 6:  # max latency
            send(MAX_LATENCY)  
            continue

        if idx == 7:  
            send("")  
            continue

        if idx == 8:  # repeat
            algo_idx += 1
            if algo_idx < len(ALGORITHMS):               
                send("y")
            else:
                send("n")
            continue

        if idx == 9:
            break

    child.close()

    if run_dir is None:
        raise RuntimeError("Could not parse run directory from configurator output.")
    return run_dir

# ---------------- MODES ----------------

def run_mode_topology_changes(num_runs: int):
    random.seed()

    for r in range(num_runs):
        print("\n==============================")
        print(f"🚀 MAIN RUN {r+1}/{num_runs}")
        print("==============================\n")

        code = run_one_main_run(
            skip_deploy=False,
            skip_delay=True,
            num_candidates=15,
            num_pmus=4,
            p_extra=0.25,
            pmu_links=1,
        )

        print(f"\n✅ MAIN RUN {r+1}/{num_runs} finished with exit code {code}\n")
        cleanup()
        time.sleep(1)

    plot_mode1_all_plots(
        runs_dir=Path("runtime_results/runs"),
        runtime_root=Path("runtime_results"),
    )

                

                
def _read_snapshot_pdcs_count(snapshots_dir: Path, prefix: str) -> int:
    files = sorted(snapshots_dir.glob(f"{prefix}_*.json"))
    if not files:
        raise FileNotFoundError(f"Missing {prefix}_*.json in {snapshots_dir}")

    snap_path = files[0]  
    with open(snap_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pdcs = data.get("pdcs", [])
    if not isinstance(pdcs, list):
        raise ValueError(f"Invalid 'pdcs' in {snap_path}")

    count = len(pdcs)

    if "CC" not in pdcs:
        count += 1

    return count                


def run_mode_increasing_nodes(num_runs: int):
    sweep = list(zip(MODE2_CANDIDATES_SEQ, MODE2_PMUS_SEQ))

    for r in range(num_runs):
        print(f"\n🔁 MODE 2 | MAIN RUN {r+1}/{num_runs}\n")
        for i, (num_candidates, num_pmus) in enumerate(sweep):
            print(f"Step {i+1}/{len(sweep)} | candidates={num_candidates}, pmus={num_pmus}")
            run_one_size_no_changes(num_candidates=num_candidates, num_pmus=num_pmus)
    
    plot_mode2_all_plots(threshold_s=1*60*60, timeout_value_pdcs=1)




def run_mode_custom():
    print("\n🧩 Mode 'custom' has to be implemented.")
    return

def read_int(prompt: str, default: int) -> int:
    s = input(prompt).strip()
    if not s:
        return default
    try:
        v = int(s)
        return v if v > 0 else default
    except ValueError:
        return default


def menu():
    print("\n====================================")
    print(" AutoPDC Experiment Runner (MENU)")
    print("====================================")
    print("1) Topology changes")
    print("2) Increase topology nodes")
    print("3) Other mode not implemented yet")
    print("0) Exit\n")

    choice = input("Select an option (0-3): ").strip()
    return choice


def main():
    choice = menu()

    if choice == "0":
        print("👋 Exit.")
        return

    if choice == "1":
        num_runs = read_int("How many main runs? (default=3): ", default=3)
        run_mode_topology_changes(num_runs)
    elif choice == "2":
        num_runs = read_int("How many main runs? (default=1): ", default=1)
        run_mode_increasing_nodes(num_runs)
    elif choice == "3":
        run_mode_custom()
    else:
        print("❌ Invalid choice.")
        return
    
    print("👋✅ Test completed. See the result in the runtime_result folder!  \n")    
    
    return


if __name__ == "__main__":
    main()
