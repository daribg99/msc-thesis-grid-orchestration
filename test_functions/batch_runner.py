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
MAX_LATENCY = "400"

# change ranges
LAT_MIN, LAT_MAX = 2.0, 25.0
BW_MIN, BW_MAX = 50, 1000
STATUS_CHOICES = ["up", "down"]

# command (module)
CMD = "python3 -u -m deploy_automation.autopdc_configurator"

RUN_DIR_RE = re.compile(r"📁 Run directory:\s*(.+)\s*$")


def latest_snapshot_edges(run_dir: Path) -> List[Tuple[str, str]]:
    snaps_dir = run_dir / "snapshots"
    if not snaps_dir.exists():
        return []
    snaps = sorted(snaps_dir.glob("snapshot_*.json"), key=lambda p: p.stat().st_mtime)
    if not snaps:
        return []
    data = json.loads(snaps[-1].read_text())
    edges = set()
    for _, info in data.get("path", {}).items():
        nodes = info.get("path", [])
        for i in range(len(nodes) - 1):
            u, v = nodes[i], nodes[i + 1]
            edges.add(tuple(sorted((u, v))))
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
    pending_ops: List[dict] = []  # T0: vuoto

    def send(line: str):
        child.sendline(line)

    while True:
        # aspettiamo uno tra i prompt / righe importanti
        idx = child.expect([
            r"📁 Run directory: .+\r?\n",                               # 0
            r"Do you want to modify a latency\? \(y/n\):\s*",            # 1
            r"Do you want to modify the status of an edge\? \(y/n\):\s*",# 2
            r"Do you want to modify a bandwidth\? \(y/n\):\s*",          # 3
            r"Enter your choice \(1-6\):\s*",                            # 4
            r"Enable cluster splitting\? \(y/n\):\s*",                   # 5
            r"Enter maximum latency.*:\s*",                              # 6  <-- QUESTO
            r"Enter seed \(default=42\):\s*",                             # 7
            r"Repeat the process\? \(y/n\):\s*",                         # 8
            pexpect.EOF,                                                 # 9
        ])


        #print(f"\n[DEBUG] matched idx={idx}\n")


        if idx == 0:
            # parse run_dir
            m = RUN_DIR_RE.search(child.after)
            if m:
                run_dir = Path(m.group(1)).expanduser()
            continue

        if idx == 1:  # latency
            picked, pending_ops = pop_ops(pending_ops, "latency")
            if not picked:
                send("n")
            else:
                for op in picked:
                    send("y")
                    child.expect(r"Node 1:\s*")
                    print(child.before + child.after, end="")
                    send(op["u"])
                    child.expect(r"Node 2:\s*")
                    print(child.before + child.after, end="")
                    send(op["v"])
                    child.expect(r"Enter new latency.*:")
                    print(child.before + child.after, end="")
                    send(str(op["value"]))
                # torna al loop interno e chiudi
                child.expect(r"Do you want to modify a latency\? \(y/n\):\s*")
                print(child.before + child.after, end="")
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
                    print(child.before + child.after, end="")
                    send(op["u"])
                    child.expect(r"Node 2:\s*")
                    print(child.before + child.after, end="")
                    send(op["v"])
                    child.expect(r"Enter new status.*:")
                    print(child.before + child.after, end="")
                    send(str(op["value"]))
                child.expect(r"Do you want to modify the status of an edge\? \(y/n\):\s*")
                print(child.before + child.after, end="")
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
                    print(child.before + child.after, end="")
                    send(op["u"])
                    child.expect(r"Node 2:\s*")
                    print(child.before + child.after, end="")
                    send(op["v"])
                    child.expect(r"Enter new bandwidth.*:")
                    print(child.before + child.after, end="")
                    send(str(op["value"]))
                child.expect(r"Do you want to modify a bandwidth\? \(y/n\):\s*")
                print(child.before + child.after, end="")
                send("n")
            continue

        if idx == 4:  # choice
            send(ALGORITHMS[algo_idx])
            continue

        if idx == 5:  # splitting
            send(SPLITTING)
            continue

        if idx == 6:  # max latency
            send(MAX_LATENCY)
            continue

        if idx == 7:  # seed (only when random)
            if ALGORITHMS[algo_idx] == "3":
                send("")  # invio vuoto -> default 42
            else:
                send("")  # safe
            continue

        if idx == 8:  # repeat
            algo_idx += 1

            if algo_idx < len(ALGORITHMS):
                send("y")  # prossimo algoritmo stesso T
                continue

            algo_idx = 0
            T += 1

            if T < TS_PER_RUN:
                # prepara cambi per il prossimo T (basati su snapshot appena scritto)
                if run_dir is not None:
                    edges = latest_snapshot_edges(run_dir)
                    pending_ops = build_ops(edges)
                else:
                    pending_ops = []
                send("y")
            else:
                send("n")
            continue

        if idx == 9:  # EOF
            break

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
