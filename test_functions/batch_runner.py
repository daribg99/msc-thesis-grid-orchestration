#!/usr/bin/env python3
import json
import random
import re
import shutil
import subprocess
import time
import sys

from pathlib import Path
from typing import List, Tuple

import pexpect

# ---------------- CONFIG ----------------
RUNS = 3
TS_PER_RUN = 3                  # T0,T1,T2
ALGORITHMS = ["1", "2", "3"]     # bruteforce, greedy, random
CHANGES_PER_T = 1

SPLITTING = "n"
MAX_LATENCY = "80"

# change ranges
LAT_MIN, LAT_MAX = 2.0, 25.0
BW_MIN, BW_MAX = 50, 1000
STATUS_CHOICES = ["up", "down"]

# command (module)
CMD = "python3 -u -m deploy_automation.autopdc_configurator"

RUN_DIR_RE = re.compile(r"Run directory:\s*(/.*)", re.IGNORECASE)


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


def run_one_main_run():
    child = pexpect.spawn(CMD, encoding="utf-8", timeout=None)
    child.logfile_read = sys.stdout

    run_dir = None

    T = 0
    algo_idx = 0
    pending_ops: List[dict] = []  # a T0: vuoto (no changes)

    def send(line: str):
        child.sendline(line)

    while True:
        idx = child.expect([
            r"📁 Run directory: [^\r\n]+\r?\n",                               # 0
            r"Do you want to modify a latency\? \(y/n\):\s*",            # 1
            r"Do you want to modify the status of an edge\? \(y/n\):\s*",# 2
            r"Do you want to modify a bandwidth\? \(y/n\):\s*",          # 3
            r"Enter your choice \(1-6\):\s*",                            # 4
            r"Enable cluster splitting\? \(y/n\):\s*",                   # 5
            r"Enter maximum latency.*:\s*",                              # 6
            r"Enter seed \(default=42\):\s*",                            # 7
            r"Repeat the process\? \(y/n\):\s*",                         # 8
            pexpect.EOF,                                                 # 9
        ])

        if idx == 0:
            # child.after contiene la riga matchata da expect (Run directory ...)
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

        if idx == 4:  # choice (algoritmo)
            print(f"\n🧠 Starting ALG={ALGORITHMS[algo_idx]} at T={T}\n")
            send(ALGORITHMS[algo_idx])
            continue

        if idx == 5:  # splitting
            send(SPLITTING)
            continue

        if idx == 6:  # max latency
            send(MAX_LATENCY)
            continue

        if idx == 7:  # seed (solo per Random)
            if ALGORITHMS[algo_idx] == "3":
                send("")  # invio vuoto -> default 42
            else:
                send("")  # safe
            continue

        if idx == 8:  # repeat
            # abbiamo finito un T per l'algoritmo corrente
            T += 1

            if T < TS_PER_RUN:
                # pianifica cambi per il prossimo T basandoti sullo snapshot appena scritto
                if run_dir is not None:
                    edges = []
                    # retry breve: aspetta che lo snapshot "ultimo" contenga davvero i path
                    for _ in range(10):  # ~2 secondi
                        edges = latest_snapshot_edges(run_dir)
                        if edges:
                            break
                        time.sleep(0.2)

                    pending_ops = build_ops(edges)
                else:
                    edges = []
                    pending_ops = []

                print(f"\n🔧 Planned ops for next T={T} (ALG={ALGORITHMS[algo_idx]}): {pending_ops}\n")
                send("y")
                continue

            # finiti T0,T1,T2 per questo algoritmo -> cleanup e passa al prossimo algoritmo
            algo_idx += 1

            if algo_idx < len(ALGORITHMS):
                cleanup()
                T = 0
                pending_ops = []
                print(f"\n➡️ Switching to ALG={ALGORITHMS[algo_idx]} (reset T=0)\n")
                send("y")
                continue

            # finiti tutti gli algoritmi
            send("n")
            continue


    child.close()
    return child.exitstatus if child.exitstatus is not None else 0


def main():
    random.seed()
    for r in range(RUNS):
        print("\n==============================")
        print(f"🚀 MAIN RUN {r+1}/{RUNS}")
        print("==============================\n")
        code = run_one_main_run()
        print(f"\n✅ MAIN RUN {r+1}/{RUNS} finished with exit code {code}\n")
        cleanup()
        time.sleep(1)


if __name__ == "__main__":
    main()
