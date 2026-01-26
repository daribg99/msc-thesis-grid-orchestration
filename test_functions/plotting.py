# test_functions/plotting.py

import csv
import matplotlib.pyplot as plt
from pathlib import Path
import re
import numpy as np

#---------------------------------------JACCARD------------------------------------------------#

def plot_pdc_topology_jaccard(csv_path: Path, output_dir: Path | None = None):
   

    T, jaccard_dist = [], []

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            T.append(int(row["T"]))
            jaccard_dist.append(float(row["jaccard_distance"]))

    if not T:
        print("⚠️ No topology-change metrics to plot.")
        return

    plt.figure()
    plt.plot(T, jaccard_dist, marker="o", label="Jaccard distance")

    plt.xlabel("Topology change index (T)")
    plt.ylabel("Jaccard distance")
    plt.xticks(T)          # discrete topology-change events
    plt.ylim(0.0, 1.0)     # Jaccard distance is normalized
    plt.legend()
    plt.grid(True)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "pdc_topology_jaccard.png"
        plt.savefig(out, dpi=300, bbox_inches="tight")
        print(f"📊 PDC topology Jaccard plot saved to {out}")
    else:
        plt.show()

    plt.close()


#---------------------------------------HISTOGRAM------------------------------------------------#

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

def plot_runtime_stacked_per_iteration(runtime_csv: Path, output_dir: Path | None = None):
   

    placement_ms = []
    deployer_ms  = []
    applier_ms   = []

    # Regex robusti (trovano la label ovunque nella riga, anche se ci sono char strani prima)
    placement_re = re.compile(r".*\bPlacement\b.*?\s+(.+)$")
    deployer_re  = re.compile(r".*\bDeployer\b\s+(.+)$")
    applier_re   = re.compile(r".*\bApplier\b\s+(.+)$")

    with open(runtime_csv, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("==="):
                continue

            # Normalizza NBSP e spazi multipli
            line = line.replace("\u00a0", " ")
            line = " ".join(line.split())

            m = placement_re.match(line)
            if m:
                ms = _parse_time_to_ms(m.group(1))
                if ms is not None:
                    placement_ms.append(ms)
                continue

            m = deployer_re.match(line)
            if m:
                ms = _parse_time_to_ms(m.group(1))
                if ms is not None:
                    deployer_ms.append(ms)
                continue

            m = applier_re.match(line)
            if m:
                ms = _parse_time_to_ms(m.group(1))
                if ms is not None:
                    applier_ms.append(ms)
                continue

    n = min(len(placement_ms), len(deployer_ms), len(applier_ms))
    if n == 0:
        print("⚠️ No runtime data to plot (placement/deployer/applier not parsed).")
        print(f"DEBUG placement parsed: {len(placement_ms)}")
        print(f"DEBUG deployer parsed:  {len(deployer_ms)}")
        print(f"DEBUG applier parsed:   {len(applier_ms)}")
        print(f"DEBUG file: {runtime_csv}")
        return

    placement = np.array(placement_ms[:n]) / 1000.0
    deployer  = np.array(deployer_ms[:n])  / 1000.0
    applier   = np.array(applier_ms[:n])   / 1000.0

    T = np.arange(1, n + 1)

    plt.figure()
    plt.bar(T, placement, label="Placement")
    plt.bar(T, deployer,  bottom=placement, label="Deployer")
    plt.bar(T, applier,   bottom=placement + deployer, label="Applier")

    plt.xlabel("Topology change index (T)")
    plt.ylabel("Time (s)")
    plt.xticks(T)
    plt.legend()
    plt.grid(axis="y")

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "runtime_stacked_per_iteration.png"
        plt.savefig(out, dpi=300, bbox_inches="tight")
        print(f"⏱️ Stacked runtime plot saved to {out}")
    else:
        plt.show()

    plt.close()




def plot_total_iteration_boxplot_by_T(runs_dir: Path, output_dir: Path | None = None):
   

    runtime_files = sorted(runs_dir.glob("run_*/runtime.csv"))
    if not runtime_files:
        print(f"⚠️ No runtime.csv files found under {runs_dir}/run_*/")
        return

    total_re = re.compile(r"^\s*Total\s+Iteration\s+(.+?)\s*$")

    # list of sequences, one per run: [t0_ms, t1_ms, ...]
    totals_per_run: list[list[float]] = []

    for rf in runtime_files:
        seq = []
        with open(rf, "r") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("==="):
                    continue

                # normalize weird spaces
                line = line.replace("\u00a0", " ")
                line = " ".join(line.split())

                m = total_re.match(line)
                if m:
                    ms = _parse_time_to_ms(m.group(1))
                    if ms is not None:
                        seq.append(ms)

        if seq:
            totals_per_run.append(seq)

    if not totals_per_run:
        print("⚠️ No 'Total Iteration' samples found across runs.")
        return

    # number of T boxes = max length among runs
    max_T = max(len(seq) for seq in totals_per_run)

    # build box data: box_data[t] = list of samples at iteration t across runs
    box_data: list[list[float]] = []
    counts: list[int] = []

    for t in range(max_T):
        samples_t = [seq[t] for seq in totals_per_run if len(seq) > t]
        box_data.append([x / 1000.0 for x in samples_t])  # seconds (more readable)
        counts.append(len(samples_t))

    # If all empty (shouldn't happen), stop
    if all(len(b) == 0 for b in box_data):
        print("⚠️ No per-T samples available to plot.")
        return

    # X labels: T0, T1, ...
    labels = [f"T{t}" for t in range(max_T)]

    plt.figure(figsize=(max(8, max_T * 1.2), 6))
    plt.boxplot(box_data, tick_labels=labels, showfliers=True)

    plt.xlabel("Topology change index (T)")
    plt.ylabel("Total iteration time (s)")
    plt.grid(axis="y")

    # Optional: show how many runs contributed to each T
    # (helps when later T have fewer samples)
    for i, c in enumerate(counts, start=1):
        plt.text(i, plt.ylim()[1] * 0.98, f"n={c}", ha="center", va="top", fontsize=8)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "total_iteration_boxplot_by_T.png"
        plt.savefig(out, dpi=300, bbox_inches="tight")
        print(f"📦 Total Iteration boxplot-by-T saved to {out}")
    else:
        plt.show()

    plt.close()
