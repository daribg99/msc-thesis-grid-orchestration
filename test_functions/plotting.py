# test_functions/plotting.py

import csv
import matplotlib.pyplot as plt
from pathlib import Path
import re
import numpy as np

#---------------------------------------JACCARD------------------------------------------------#

def plot_pdc_topology_jaccard(csv_path: Path, output_dir: Path | None = None):
    """
    Plot the Jaccard distance between consecutive PDC placements over time.

    Parameters
    ----------
    csv_path : Path
        Path to the topology_change.csv file.
    output_dir : Path | None
        If provided, the plot is saved to this directory.
        Otherwise, it is shown interactively.
    """

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
    s = s.strip()

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

def plot_runtime_histogram(runtime_csv: Path, output_dir: Path | None = None):
    """
    Vertical grouped bar chart per T:
      - Placement time
      - Total iteration time
    """

    placement_times_ms = []
    total_times_ms = []

    placement_re = re.compile(r"^Placement-.*\s+(.+)$")
    total_re = re.compile(r"^Total Iteration\s+(.+)$")

    with open(runtime_csv, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("==="):
                continue

            m1 = placement_re.match(line)
            if m1:
                ms = _parse_time_to_ms(m1.group(1))
                if ms is not None:
                    placement_times_ms.append(ms)

            m2 = total_re.match(line)
            if m2:
                ms = _parse_time_to_ms(m2.group(1))
                if ms is not None:
                    total_times_ms.append(ms)

    n = min(len(placement_times_ms), len(total_times_ms))
    if n == 0:
        print("⚠️ No runtime data to plot (placement/total not parsed).")
        print(f"DEBUG placement parsed: {len(placement_times_ms)}")
        print(f"DEBUG total parsed: {len(total_times_ms)}")
        return

    placement_times_ms = placement_times_ms[:n]
    total_times_ms = total_times_ms[:n]

    T = np.arange(1, n + 1)
    width = 0.35

    plt.figure()
    plt.bar(T - width / 2, placement_times_ms, width, label="Placement time")
    plt.bar(T + width / 2, total_times_ms, width, label="Total iteration time")

    plt.xlabel("Topology change index (T)")
    plt.ylabel("Time (ms)")
    plt.xticks(T)
    plt.legend()
    plt.grid(axis="y")

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "runtime_histogram.png"
        plt.savefig(out, dpi=300, bbox_inches="tight")
        print(f"⏱️ Runtime per iteration plot saved to {out}")
    else:
        plt.show()

    plt.close()
