# test_functions/plotting.py
from __future__ import annotations
import csv
import matplotlib.pyplot as plt
from pathlib import Path
import re
import numpy as np
from typing import Dict, List
from matplotlib.patches import Patch   
import json


#---------------DEFAULT COLORS AND SHORT LETTERS------------------#

ALGO_COLORS_UNIFIED = {
    "Bruteforce": "#1f77b4",  # blu
    "Greedy":     "#2ca02c",  # verde
    "Random":     "#d62728",  # rosso
}
SHORT_LETTER = {"Bruteforce": "B", "Greedy": "G", "Random": "R"}

def _add_letters_above_boxes(ax, bp, positions, box_algos, *, y_mult=1.03, fontsize=9, color="0.25"):
    """Place B/G/R above each box, anchored to its upper whisker."""
    whiskers = bp["whiskers"]
    for i, algo in enumerate(box_algos):
        w_upper = whiskers[2 * i + 1]              # upper whisker for i-th box
        y_top = max(w_upper.get_ydata())
        ax.text(
            positions[i],
            y_top * y_mult,
            SHORT_LETTER.get(algo, ""),
            ha="center",
            va="bottom",
            fontsize=fontsize,
            color=color,
        )


def _add_unified_legend(ax, *, alg_order, colors):
    """Legend like Jaccard: colored patches with plain algorithm names."""        
    handles = [
        Patch(facecolor=colors[a], edgecolor="black", label=a)
        for a in alg_order
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=9)



def clip_by_mad(vals, z_thresh=3.5):
    vals = np.array([v for v in vals if np.isfinite(v)])
    if len(vals) < 3:
        return vals.tolist()

    median = np.median(vals)
    abs_dev = np.abs(vals - median)
    mad = np.median(abs_dev)

    if mad == 0:
        return vals.tolist()

    # Modified Z-score
    modified_z = 0.6745 * (vals - median) / mad

    filtered = vals[np.abs(modified_z) <= z_thresh]
    return filtered.tolist()
    
#---------------------------------------JACCARD------------------------------------------------#


def plot_pdc_topology_jaccard(
    csv_path: Path,
    output_dir: Path | None = None,
    *,
    metric_col: str = "jaccard_distance",
    alg_labels: dict[str, str] | None = None,
):
    series_by_alg: dict[str, dict[int, float]] = {}
    all_t: set[int] = set()

    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            alg = (r.get("algorithm") or "").strip()
            alg = alg.removeprefix("Placement-")
            if not alg:
                continue

            try:
                t = int(float(r["T"]))
            except (KeyError, ValueError):
                continue

            if t == 0:
                continue

            try:
                y = float(r[metric_col])
            except (KeyError, ValueError):
                continue

            series_by_alg.setdefault(alg, {})[t] = y
            all_t.add(t)

    if not all_t:
        print("⚠️ No data to plot (after skipping T0).")
        return

    # --- Plot ---
    fig, ax = plt.subplots()

    alg_order = ["Bruteforce", "Greedy", "Random"]
    marker_map = {"Bruteforce": "o", "Greedy": "s", "Random": "^"}

    for alg in alg_order:
        if alg not in series_by_alg:
            continue

        t_to_y = series_by_alg[alg]
        X = sorted(t_to_y.keys())
        Y = [t_to_y[t] for t in X]

        ax.plot(
            X,
            Y,
            marker=marker_map.get(alg, "o"),
            markersize=6,
            linewidth=1.8,
            color=ALGO_COLORS_UNIFIED.get(alg, "0.8"),
            alpha=0.85,
            label=(alg_labels.get(alg, alg) if alg_labels else alg),
        )

    ax.set_title(
        f"Jaccard Distance vs Topology Change ( single run )",
        fontsize=12,
        pad=14,
    )
    
    xticks = sorted(all_t)
    ax.set_xticks(xticks)
    ax.set_xticklabels([f"T{t}" for t in xticks])

    ax.set_xlabel("Topology change index (T)")
    ax.set_ylabel(metric_col.replace("_", " ").title())
    ax.set_ylim(0.0, 1.0)
    ax.grid(True)

    _add_unified_legend(
        ax,
        alg_order=[a for a in alg_order if a in series_by_alg],
        colors=ALGO_COLORS_UNIFIED,
    )

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"pdc_topology_{metric_col}.pdf"
        fig.savefig(out, bbox_inches="tight")
        print(f"📊 Plot saved to {out}")
    else:
        plt.show()

    plt.close(fig)



def plot_jaccard_boxplot_by_T(
    runs_dir: Path,
    output_dir: Path | None = None,
    *,
    alg_order: list[str] = ["Bruteforce", "Greedy", "Random"],  
    required_T: int | None = None,
    metric_col: str = "jaccard_distance",
    t_col: str = "T",
    algo_col: str = "algorithm",
    note_col: str = "note",
):
    metrics_name = "topology_change.csv"

    def _to_plain_alg(name: str) -> str:
        """Accepts 'Placement-X' or 'X' and returns plain 'X'."""
        s = (name or "").strip()
        if s.lower().startswith("placement-"):
            s = s.split("-", 1)[1].strip()
        low = s.lower()
        if low == "bruteforce":
            return "Bruteforce"
        if low == "greedy":
            return "Greedy"
        if low == "random":
            return "Random"
        return s  

    run_dirs = sorted([p for p in runs_dir.glob("run_*") if p.is_dir()])
    if not run_dirs:
        print(f"⚠️ No run_* directories found under {runs_dir}")
        return

    metrics_files = [rd / metrics_name for rd in run_dirs if (rd / metrics_name).exists()]
    if not metrics_files:
        print(f"⚠️ No {metrics_name} found under {runs_dir}/run_*/")
        return

    valid_runs: list[dict[str, dict[int, float]]] = []

    for mf in metrics_files:
        run_vals: dict[str, dict[int, float]] = {a: {} for a in alg_order}

        with open(mf, "r", newline="") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                continue
            if algo_col not in reader.fieldnames or t_col not in reader.fieldnames or metric_col not in reader.fieldnames:
                continue

            ok = True
            for r in reader:
                alg_raw = (r.get(algo_col) or "").strip()
                alg = _to_plain_alg(alg_raw)
                if alg not in run_vals:
                    continue

                note = (r.get(note_col) or "").strip()
                try:
                    t = int(float(r[t_col]))
                except Exception:
                    ok = False
                    break

                if t == 0:
                    continue
                if note:
                    continue

                try:
                    y = float(r[metric_col])
                except Exception:
                    ok = False
                    break

                run_vals[alg][t] = y

        if not ok:
            continue

        if any(len(run_vals[a]) == 0 for a in alg_order):
            continue

        valid_runs.append(run_vals)

    if not valid_runs:
        print("⚠️ No valid runs found.")
        return

    def max_t_for_run(run_vals: dict[str, dict[int, float]]) -> int:
        return min(max(run_vals[a].keys()) for a in alg_order)

    K_common = min(max_t_for_run(r) for r in valid_runs)
    K = K_common if required_T is None else min(required_T, K_common)
    if K <= 0:
        print("⚠️ No T left to plot.")
        return

    filtered_runs = []
    for r in valid_runs:
        if all(all(t in r[a] for t in range(1, K + 1)) for a in alg_order):
            filtered_runs.append(r)

    if not filtered_runs:
        print("⚠️ No runs have complete data for common K.")
        return

    box_data: list[list[float]] = []
    box_algos: list[str] = []
    positions: list[float] = []

    nA = len(alg_order)
    base = np.arange(K)  
    width = 0.24 if nA == 3 else min(0.24, 0.8 / max(nA, 1))
    offsets = (np.arange(nA) - (nA - 1) / 2.0) * width

    for idx_t in range(K):
        t = idx_t + 1
        for j, alg in enumerate(alg_order):
            samples = [run[alg][t] for run in filtered_runs]
            box_data.append(samples)
            box_algos.append(alg)                 
            positions.append(base[idx_t] + offsets[j])

    fig, ax = plt.subplots(figsize=(max(9, K * 1.4), 6))

    bp = ax.boxplot(
        box_data,
        positions=positions,
        widths=width * 0.9,
        patch_artist=True,
        showfliers=True,
        manage_ticks=False,
    )

    for box, alg in zip(bp["boxes"], box_algos):
        box.set_facecolor(ALGO_COLORS_UNIFIED.get(alg, "0.8"))
        box.set_edgecolor("black")
        box.set_alpha(0.85)

    _add_letters_above_boxes(ax, bp, positions, box_algos)

    ax.set_xticks(base)
    ax.set_xticklabels([f"T{t}" for t in range(1, K + 1)])
    ax.set_xlabel("Topology change index (T)")
    ax.set_ylabel("Jaccard distance")
    ax.set_ylim(0.0, 1.0)
    ax.grid(axis="y")

    _add_unified_legend(ax, alg_order=alg_order, colors=ALGO_COLORS_UNIFIED)

    
    ax.set_title(
        f"Distribution of Jaccard Distance vs Topology Change (n = {len(filtered_runs)} runs)",
        fontsize=12,
        pad=14,
    )
    
    fig.subplots_adjust(top=0.88, bottom=0.14)

    if output_dir is not None:
        summary_dir = output_dir / "summarymode1"
        summary_dir.mkdir(parents=True, exist_ok=True)

        out = summary_dir / "jaccard_boxplot_by_T_and_algo.pdf"
        fig.savefig(out, bbox_inches="tight", pad_inches=0.2)
        print(f"📦 Jaccard boxplot-by-T saved to {out}")
    else:
        plt.show()


    plt.close(fig)





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



def plot_runtime_stacked_per_iteration(
    runtime_csv: Path,
    output_dir: Path | None = None,
    *,
    alg_order: list[str] = ["Bruteforce", "Greedy", "Random"],
    num_algorithms: int = 3,
    skip_T: int = 0,
    K: int | None = None,
):
    placement_re = re.compile(r"^Placement-(Greedy|Bruteforce|Random)\s+(.+)$", re.IGNORECASE)
    deployer_re  = re.compile(r"^Deployer\s+(.+)$", re.IGNORECASE)
    applier_re   = re.compile(r"^Applier\s+(.+)$", re.IGNORECASE)

    records: list[tuple[str, float, float, float]] = []

    cur_algo = None
    cur_place = None
    cur_dep = None
    cur_app = None

    def _flush_if_complete():
        nonlocal cur_algo, cur_place, cur_dep, cur_app
        if cur_algo is not None and cur_place is not None and cur_dep is not None and cur_app is not None:
            records.append((cur_algo, cur_place, cur_dep, cur_app))
        cur_algo = None
        cur_place = None
        cur_dep = None
        cur_app = None

    with open(runtime_csv, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("==="):
                continue

            line = line.replace("\u00a0", " ")
            line = " ".join(line.split())

            m = placement_re.match(line)
            if m:
                cur_algo  = m.group(1).capitalize()
                cur_place = _parse_time_to_ms(m.group(2))
                cur_dep = None
                cur_app = None
                continue

            m = deployer_re.match(line)
            if m and cur_algo is not None:
                cur_dep = _parse_time_to_ms(m.group(1))
                continue

            m = applier_re.match(line)
            if m and cur_algo is not None:
                cur_app = _parse_time_to_ms(m.group(1))
                _flush_if_complete()
                continue


    if not records:
        print("⚠️ No runtime data to plot (no complete blocks parsed).")
        print(f"DEBUG file: {runtime_csv}")
        return

    per_algo: dict[str, list[tuple[float, float, float]]] = {a: [] for a in alg_order}
    for algo, p, d, ap in records:
        if algo in per_algo:
            per_algo[algo].append((p, d, ap))

    present_algos = [a for a in alg_order if len(per_algo[a]) > 0]
    if not present_algos:
        print("⚠️ No known algorithms found in runtime file.")
        return

    if len(present_algos) != num_algorithms:
        print(f"⚠️ Expected {num_algorithms} algorithms, found {len(present_algos)}: {present_algos}")

    nT_total = min(len(per_algo[a]) for a in present_algos)
    if nT_total == 0:
        print("⚠️ Not enough data to form any T.")
        return

    if skip_T < 0:
        skip_T = 0
    if skip_T >= nT_total:
        print(f"⚠️ skip_T={skip_T} but only {nT_total} T available (min across algos).")
        return

    nT_avail = nT_total - skip_T
    if K is None or K > nT_avail:
        K = nT_avail
    if K <= 0:
        print("⚠️ K=0 -> nothing to plot.")
        return

    nA = len(present_algos)
    placement = np.zeros((K, nA), dtype=float)
    deployer  = np.zeros((K, nA), dtype=float)
    applier   = np.zeros((K, nA), dtype=float)

    for j, algo in enumerate(present_algos):
        series = per_algo[algo][skip_T:skip_T + K]
        placement[:, j] = [x[0] for x in series]
        deployer[:,  j] = [x[1] for x in series]
        applier[:,   j] = [x[2] for x in series]

    placement /= 1000.0
    deployer  /= 1000.0
    applier   /= 1000.0

    T = np.arange(0, K)
  
    group_width_max = 0.8          
    gap_ratio = 0.10              

    width_target = 0.25 if nA == 3 else min(0.25, group_width_max / max(nA, 1))

    gap = gap_ratio * width_target

    den = nA + (nA - 1) * gap_ratio
    width = min(0.25, group_width_max / den)

    gap = gap_ratio * width

    effective_step = width + gap
    offsets = (np.arange(nA) - (nA - 1) / 2.0) * effective_step
    x = np.repeat(T, nA) + np.tile(offsets, K)



    placement_flat = placement.reshape(-1)
    deployer_flat  = deployer.reshape(-1)
    applier_flat   = applier.reshape(-1)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(x, placement_flat, width=width, label="Placement")
    ax.bar(x, deployer_flat,  width=width, bottom=placement_flat, label="Deployer")
    ax.bar(x, applier_flat,   width=width, bottom=placement_flat + deployer_flat, label="Applier")

    ax.set_title(
        f"Runtime vs Topology Change ( single run )",
        fontsize=12,
        pad=14,
    )
    
    ax.set_xlabel("Topology change index (T)")
    ax.set_ylabel("Time (s)")
    ax.set_xticks(T)
    ax.set_xticklabels([f"T{t}" for t in T])

    short = {"Greedy": "G", "Bruteforce": "B", "Random": "R"}
    total_height = placement + deployer + applier
    y_offset = 0.015 * total_height.max()

    for i_t, t in enumerate(T):
        for j, algo in enumerate(present_algos):
            ax.text(
                t + offsets[j],
                total_height[i_t, j] + y_offset,
                short.get(algo, algo[0].upper()),
                ha="center",
                va="bottom",
                fontsize=9,
                color="0.25",
                clip_on=False,
            )

    ax.axhline(0, linewidth=0.8)
    ax.legend(loc="upper right")
    ax.grid(axis="y")

    fig.subplots_adjust(top=0.92, bottom=0.14)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "runtime_stacked_per_iteration.pdf"
        fig.savefig(out, bbox_inches="tight", pad_inches=0.2)
        print(f"⏱️ Stacked runtime plot saved to {out}")
    else:
        plt.show()

    plt.close(fig)


def plot_total_iteration_boxplot_by_T(
    runs_dir: Path,
    output_dir: Path | None = None,
    *,
    alg_order: list[str] = ["Bruteforce", "Greedy", "Random"],
    required_T: int | None = None,   
):
    

    runtime_files = sorted(runs_dir.glob("run_*/runtime.csv"))
    if not runtime_files:
        print(f"⚠️ No runtime.csv files found under {runs_dir}/run_*/")
        return

    placement_re = re.compile(r"^Placement-(Greedy|Bruteforce|Random)\s+(.+)$", re.IGNORECASE)
    total_re     = re.compile(r"^Total\s+Iteration\s+(.+?)\s*$", re.IGNORECASE)

    # Each valid run contributes:
    #   per_algo_totals[algo] = [t0_ms, t1_ms, ...]
    valid_runs: list[dict[str, list[float]]] = []

    for rf in runtime_files:
        per_algo_totals: dict[str, list[float]] = {a: [] for a in alg_order}
        cur_algo: str | None = None

        with open(rf, "r") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("==="):
                    continue

                line = line.replace("\u00a0", " ")
                line = " ".join(line.split())

                m = placement_re.match(line)
                if m:
                    cur_algo = m.group(1).capitalize()
                    continue

                m = total_re.match(line)
                if m and cur_algo is not None:
                    ms = _parse_time_to_ms(m.group(1))
                    if ms is not None and cur_algo in per_algo_totals:
                        per_algo_totals[cur_algo].append(ms)

        present_algos = [a for a in alg_order if len(per_algo_totals[a]) > 0]
        if len(present_algos) != len(alg_order):
            continue

        lengths = [len(per_algo_totals[a]) for a in alg_order]
        if len(set(lengths)) != 1:
            continue

        if lengths[0] == 0:
            continue

        valid_runs.append(per_algo_totals)

    if not valid_runs:
        print("⚠️ No valid runs found (missing blocks or inconsistent lengths).")
        return

    K_per_run = [len(r[alg_order[0]]) for r in valid_runs]
    K_common = min(K_per_run)
    K = K_common if required_T is None else min(required_T, K_common)

    if K <= 0:
        print("⚠️ No T left to plot after applying required_T/min-common.")
        return

    box_data: list[list[float]] = []
    box_algos: list[str] = []
    positions: list[float] = []

    nA = len(alg_order)
    base = np.arange(K)
    width = 0.22 if nA == 3 else min(0.22, 0.8 / max(nA, 1))
    offsets = (np.arange(nA) - (nA - 1) / 2.0) * width

    for t in range(K):
        for j, algo in enumerate(alg_order):
            samples = [run[algo][t] / 1000.0 for run in valid_runs]
            samples = clip_by_mad(samples, z_thresh=3.5)
            box_data.append(samples)
            box_algos.append(algo)
            positions.append(base[t] + offsets[j])

    fig, ax = plt.subplots(figsize=(max(9, K * 1.4), 6))

    bp = ax.boxplot(
        box_data,
        positions=positions,
        widths=width * 0.9,
        patch_artist=True,
        showfliers=True,
        manage_ticks=False,
    )

    for box, algo in zip(bp["boxes"], box_algos):
        box.set_facecolor(ALGO_COLORS_UNIFIED.get(algo, "0.8"))
        box.set_edgecolor("black")
        box.set_alpha(0.85)

    _add_letters_above_boxes(ax, bp, positions, box_algos)


    ax.set_title(
        f"Distribution of Algorithm Runtime vs Topology Change (n = {len(valid_runs)} runs)",
        fontsize=12,
        pad=14,
    )
    
    _add_unified_legend(ax, alg_order=alg_order, colors=ALGO_COLORS_UNIFIED)

    ax.set_xticks(base)
    ax.set_xticklabels([f"T{t}" for t in range(K)])

    ax.set_xlabel("Topology change index (T)")
    ax.set_ylabel("Time (s)")

    ax.grid(axis="y")
    
    fig.subplots_adjust(top=0.88, bottom=0.14)

    if output_dir is not None:
        summary_dir = output_dir / "summarymode1"
        summary_dir.mkdir(parents=True, exist_ok=True)

        out = summary_dir / "total_iteration_boxplot_by_T_and_algo.pdf"
        fig.savefig(out, bbox_inches="tight", pad_inches=0.2)
        print(f"📦 Total Iteration boxplot-by-T (per algo) saved to {out}")
    else:
        plt.show()

    plt.close(fig)

# ---------------------------------------TIME VS NODES------------------------------------------------#
 


# ===== MODE2 CONFIG (replicata qui per rendere plotting autonomo) =====
MODE2_CANDIDATES_SEQ = [10, 20, 30, 40]
MODE2_PMUS_SEQ       = [0, 1, 2, 3]   # PMU8 aggiunta internamente
MODE2_BLOCK_SIZE     = 4

# ===== ROOTS =====
def _repo_root() -> Path:
    # plotting.py sta in .../TESI/test_functions/plotting.py
    return Path(__file__).resolve().parent.parent

def _runs_root() -> Path:
    # .../TESI/runtime_results/runs
    return _repo_root() / "runtime_results" / "runs"

def _summary_mode2_dir() -> Path:
    d = _repo_root() / "runtime_results" / "summarymode2"
    d.mkdir(parents=True, exist_ok=True)
    return d

def discover_run_dirs() -> list[Path]:
    runs_dir = _runs_root()
    if not runs_dir.exists():
        return []
    run_dirs = [p for p in runs_dir.iterdir() if p.is_dir() and p.name.startswith("run_")]
    return sorted(run_dirs, key=lambda p: p.name)

def group_run_dirs(run_dirs: list[Path], block_size: int = MODE2_BLOCK_SIZE) -> list[list[Path]]:
    blocks = []
    for i in range(0, len(run_dirs), block_size):
        blk = run_dirs[i:i + block_size]
        if len(blk) == block_size:
            blocks.append(blk)
    return blocks

# ===== runtime.csv parsing =====
def _parse_time_to_ms(s: str) -> float | None:
    s = s.strip().replace("\r", "").replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)

    m = re.fullmatch(r"([\d.]+)\s*ms", s)
    if m: return float(m.group(1))

    m = re.fullmatch(r"([\d.]+)\s*s", s)
    if m: return float(m.group(1)) * 1000.0

    m = re.fullmatch(r"(\d+)\s*m\s*([\d.]+)\s*s", s)
    if m:
        minutes = int(m.group(1))
        seconds = float(m.group(2))
        return (minutes * 60.0 + seconds) * 1000.0

    m = re.fullmatch(r"(\d+)\s*h\s*(\d+)\s*m\s*([\d.]+)\s*s", s)
    if m:
        hours = int(m.group(1))
        minutes = int(m.group(2))
        seconds = float(m.group(3))
        return (hours * 3600.0 + minutes * 60.0 + seconds) * 1000.0

    return None

def parse_total_iteration_per_algo(runtime_csv: Path) -> dict[str, float]:
    placement_re = re.compile(r"^Placement-(Greedy|Bruteforce|Random)\s+(.+?)\s*$", re.IGNORECASE)
    totals_ms: dict[str, float] = {}

    for raw in runtime_csv.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("==="):
            continue
        line = " ".join(line.replace("\u00a0", " ").split())

        m = placement_re.match(line)
        if not m:
            continue
        algo = m.group(1).capitalize()
        if algo in totals_ms:
            continue

        ms = _parse_time_to_ms(m.group(2))
        if ms is not None:
            totals_ms[algo] = ms

    required = ["Bruteforce", "Greedy", "Random"]
    if not all(a in totals_ms for a in required):
        raise ValueError(f"Missing placement times in {runtime_csv}: found={totals_ms}")

    return {k: v / 1000.0 for k, v in totals_ms.items()}  # seconds

# ===== snapshots PDC count =====
def _read_snapshot_pdcs_count(snapshots_dir: Path, prefix: str) -> int:
    files = sorted(snapshots_dir.glob(f"{prefix}_*.json"))
    if not files:
        raise FileNotFoundError(f"Missing {prefix}_*.json in {snapshots_dir}")

    snap_path = files[0]
    data = json.loads(snap_path.read_text(encoding="utf-8"))

    pdcs = data.get("pdcs", [])
    if not isinstance(pdcs, list):
        raise ValueError(f"Invalid 'pdcs' in {snap_path}")

    count = len(pdcs)
    if "CC" not in pdcs:
        count += 1
    return count

# ===== build MODE2 results from a block =====
def build_mode2_results_from_block(run_dirs_block: list[Path], *, main_run_idx: int) -> tuple[list[dict], list[dict]]:
    if len(run_dirs_block) != MODE2_BLOCK_SIZE:
        raise ValueError("MODE2 block must have exactly 4 run dirs.")

    results: list[dict] = []
    results_pdcs: list[dict] = []

    for i, run_dir in enumerate(run_dirs_block):
        num_candidates = MODE2_CANDIDATES_SEQ[i]
        num_pmus = MODE2_PMUS_SEQ[i] + 1  # include PMU8
        nodes_total = 1 + num_candidates + num_pmus + 1  # CC + candidates + PMUs(incl PMU8) + CC? -> replico la tua formula

        runtime_csv = run_dir / "runtime.csv"
        snapshots_dir = run_dir / "snapshots"

        totals = parse_total_iteration_per_algo(runtime_csv)

        row = {
            "nodes": nodes_total,
            "candidates": num_candidates,
            "pmus": num_pmus,
            "Bruteforce": totals["Bruteforce"],
            "Greedy": totals["Greedy"],
            "Random": totals["Random"],
            "run": main_run_idx,
            "run_dir": str(run_dir),
        }
        results.append(row)

        pdcs_counts = {
            "Bruteforce": _read_snapshot_pdcs_count(snapshots_dir, "snapshot_0000"),
            "Greedy": _read_snapshot_pdcs_count(snapshots_dir, "snapshot_0001"),
            "Random": _read_snapshot_pdcs_count(snapshots_dir, "snapshot_0002"),
        }

        row_pdcs = {
            "nodes": nodes_total,
            "candidates": num_candidates,
            "pmus": num_pmus,
            "Bruteforce": pdcs_counts["Bruteforce"],
            "Greedy": pdcs_counts["Greedy"],
            "Random": pdcs_counts["Random"],
            "run": main_run_idx,
            "run_dir": str(run_dir),
        }
        results_pdcs.append(row_pdcs)

    return results, results_pdcs
 
 
    
def plot_time_vs_nodes(results: list[dict], *, out_name: str = "time_vs_nodes_by_algorithm.pdf"):
    
    SCRIPT_DIR = Path(__file__).resolve().parent          # .../TESI/test_functions
    REPO_ROOT  = SCRIPT_DIR.parent                        # .../TESI
    

    THRESHOLD = 1 * 60 * 60  

    x = [r["nodes"] for r in results]
    yB_raw = [r["Bruteforce"] for r in results]
    yG_raw = [r["Greedy"] for r in results]
    yR_raw = [r["Random"] for r in results]

    all_raw = yB_raw + yG_raw + yR_raw
    finite_vals = [v for v in all_raw if np.isfinite(v) and v < THRESHOLD]


    if finite_vals:
        Y_MAX_VIS = max(finite_vals) * 1.30
    else:
        Y_MAX_VIS = float(THRESHOLD)

    def mask_threshold(values):
        out = []
        for v in values:
            if (not np.isfinite(v)) or (v >= THRESHOLD):
                out.append(np.nan)   # ← non viene disegnato
            else:
                out.append(float(v))
        return out


    yB = mask_threshold(yB_raw)
    yG = mask_threshold(yG_raw)
    yR = mask_threshold(yR_raw)


    def jitter(values, factor):
        return [v * factor for v in values]

    yB_plot = jitter(yB, 1.00)  # reference
    yG_plot = jitter(yG, 1.03)  # +3%
    yR_plot = jitter(yR, 0.97)  # -3%

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(9, 5))

    ax.set_title(
        f"Algorithm Runtime vs Network Size ( single run)",
        fontsize=12,
        pad=14,
    )
    
    alg_order = ["Bruteforce", "Greedy", "Random"]

    ax.plot(
        x, yB_plot,
        marker="o",
        color=ALGO_COLORS_UNIFIED["Bruteforce"],
        label="Bruteforce",
    )

    ax.plot(
        x, yG_plot,
        marker="s",
        color=ALGO_COLORS_UNIFIED["Greedy"],
        label="Greedy",
    )

    ax.plot(
        x, yR_plot,
        marker="^",
        color=ALGO_COLORS_UNIFIED["Random"],
        label="Random",
    )

    ax.set_xlabel("Number of nodes (CC + candidates + PMUs)")

    nodes_sorted = sorted(set(x))
    ax.set_xticks(nodes_sorted)
    ax.set_xticklabels([str(n) for n in nodes_sorted])

    ax.set_ylabel("Algorithm time (s) [log scale]")
    ax.set_yscale("log")

    y_min = 1e-3
    ax.set_ylim(y_min, Y_MAX_VIS)

    ax.grid(True, which="both")

    _add_unified_legend(
        ax,
        alg_order=alg_order,
        colors=ALGO_COLORS_UNIFIED,
    )


    y_anno = Y_MAX_VIS * 1.05

    def annotate_timeouts(y_raw):
        already_annotated = False

        for xi, v in zip(x, y_raw):
            if not already_annotated and (v >= THRESHOLD or not np.isfinite(v)):
                plt.annotate(
                    "Timeout ≥ 3h ↑",
                    (xi, y_anno),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    color="0.25",
                    clip_on=False,
                )
                already_annotated = True


    annotate_timeouts(yB_raw)
    annotate_timeouts(yG_raw)
    annotate_timeouts(yR_raw)

   
    out_dir = _summary_mode2_dir()   # usa helper sopra
    out = out_dir / out_name
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)

    print(f"📈 Final plot saved to {out}")



def plot_mode2_all_plots(
    *,
    threshold_s: float = 1 * 60 * 60,
    timeout_value_pdcs: int = 1,
):
    run_dirs = discover_run_dirs()
    blocks = group_run_dirs(run_dirs, block_size=MODE2_BLOCK_SIZE)

    if not blocks:
        print("❌ No complete MODE2 blocks (4 runs) found in runtime_results/runs.")
        return

    all_results: list[dict] = []
    all_results_pdcs: list[dict] = []

    # ---------- per-main-run plots ----------
    for main_idx, blk in enumerate(blocks):
        try:
            results, results_pdcs = build_mode2_results_from_block(blk, main_run_idx=main_idx)
            all_results.extend(results)
            all_results_pdcs.extend(results_pdcs)

            plot_time_vs_nodes(results, out_name=f"time_vs_nodes_by_algorithm_run{main_idx}.pdf")
            plot_pdcs_vs_candidates_bar(results_pdcs, run_index=main_idx)
        except Exception as e:
            print(f"⚠️ Skipping MAIN RUN {main_idx}: {e}")

    # ---------- final TIME boxplot ----------
    try:
        if not all_results:
            raise RuntimeError("No valid data for TIME boxplot.")

        nodes_sorted = sorted({int(rr["nodes"]) for rr in all_results})
        counts_per_node = [sum(1 for rr in all_results if int(rr["nodes"]) == n) for n in nodes_sorted]
        runs_completed_per_topology = min(counts_per_node) if counts_per_node else 0

        if runs_completed_per_topology >= 2:
            plot_box_plot_time_vs_nodes(all_results, threshold_s=threshold_s)
        else:
            print(f"⚠️ Not enough MAIN RUNs per topology for TIME boxplot (min={runs_completed_per_topology}).")
    except Exception as e:
        print(f"⚠️ Skipping final TIME boxplot: {e}")

    # ---------- final PDC boxplot ----------
    try:
        # se vuoi tenerla com’è, ok chiamare la funzione “finale”
        plot_mode2_final_pdcs_boxplot(timeout_value=timeout_value_pdcs)

        # alternativa (se un giorno vuoi evitare anche qui il re-parse):
        # plot_pdcs_boxplot_from_results(all_results_pdcs, timeout_value=timeout_value_pdcs)
    except Exception as e:
        print(f"⚠️ Skipping final PDC boxplot: {e}")

    

def plot_box_plot_time_vs_nodes(
    results: list[dict],
    output_dir: "Path | None" = None,
    *,
    alg_order: list[str] = ["Bruteforce", "Greedy", "Random"],
    threshold_s: float = 3 * 60 * 60,   # 3 ore
):
    from pathlib import Path
    import numpy as np
    import matplotlib.pyplot as plt

    SCRIPT_DIR = Path(__file__).resolve().parent          # .../TESI/test_functions
    REPO_ROOT  = SCRIPT_DIR.parent                        # .../TESI

    # output
    out_dir = (REPO_ROOT / "runtime_results" / "summarymode2") if output_dir is None else output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes_sorted = sorted({int(r["nodes"]) for r in results})
    if not nodes_sorted:
        print("⚠️ No data to plot (empty results).")
        return

    def collect_for_nodes(algo_key: str):
        data: list[list[float]] = []
        timeout_counts: list[int] = []
        timeout_mask: list[bool] = []

        for n in nodes_sorted:
            vals_raw = [float(r[algo_key]) for r in results if int(r["nodes"]) == n]
            vals_ok  = [v for v in vals_raw if np.isfinite(v) and v < threshold_s]
            timeouts = sum(1 for v in vals_raw if (not np.isfinite(v)) or (v >= threshold_s))

            data.append(vals_ok)
            timeout_counts.append(timeouts)

            # vero timeout quando NON hai box (tutte le run sono timeout)
            timeout_mask.append(len(vals_ok) == 0)

        return data, timeout_counts, timeout_mask

    data_by_algo: dict[str, list[list[float]]] = {}
    timeouts_by_algo: dict[str, list[int]] = {}
    timeout_mask_by_algo: dict[str, list[bool]] = {}

    for algo in alg_order:
        d, c, m = collect_for_nodes(algo)
        data_by_algo[algo] = d
        timeouts_by_algo[algo] = c
        timeout_mask_by_algo[algo] = m

    # y-limits (robusti, ma includi max)
    all_ok: list[float] = []
    for algo in alg_order:
        for group in data_by_algo[algo]:
            all_ok.extend([v for v in group if np.isfinite(v)])

    if all_ok:
        p95 = float(np.percentile(all_ok, 95))
        Y_MAX_VIS = max(float(max(all_ok)), p95 * 1.8)
    else:
        print("⚠️ All values are timeouts; nothing to plot.")
        return

    K = len(nodes_sorted)
    base = np.arange(K)

    nA = len(alg_order)
    width = 0.22 if nA == 3 else min(0.22, 0.8 / max(nA, 1))
    offsets = (np.arange(nA) - (nA - 1) / 2.0) * width

    box_data: list[list[float]] = []
    box_algos: list[str] = []
    positions: list[float] = []

    for i_node in range(K):
        for j, algo in enumerate(alg_order):
            box_data.append(data_by_algo[algo][i_node])
            box_algos.append(algo)
            positions.append(float(base[i_node] + offsets[j]))

    fig, ax = plt.subplots(figsize=(max(10, K * 1.8), 5.5))

    # n = runs (stima semplice: assume results completi)
    num_nodes = len({int(r["nodes"]) for r in results})
    num_runs = (len(results) // num_nodes) if num_nodes > 0 else 0
    

    bp = ax.boxplot(
        box_data,
        positions=positions,
        widths=width * 0.9,
        patch_artist=True,
        showfliers=False,
        manage_ticks=False,
    )
    ax.set_title(
        f"Distribution of Algorithm Runtime vs Network Size (n = {num_runs} runs)",
        fontsize=12,
        pad=14,
    )


    # ---- style lines ----
    for med in bp["medians"]:
        med.set_color("black"); med.set_linewidth(1.6)
    for w in bp["whiskers"]:
        w.set_color("black"); w.set_linewidth(1.2)
    for c in bp["caps"]:
        c.set_color("black"); c.set_linewidth(1.2)

    # ---- styling + timeout labels at "box slot" ----
    # posizione y del testo: metà della scala log (stabile)
    y_lo = 1e-3
    y_hi = Y_MAX_VIS
    y_text_fixed = 10 ** (0.5 * (np.log10(y_lo) + np.log10(y_hi)))

    for i, (box, algo) in enumerate(zip(bp["boxes"], box_algos)):
        i_node = i // nA
        c_to = timeouts_by_algo[algo][i_node]
        vals_ok = data_by_algo[algo][i_node]

        if len(vals_ok) == 0:
            # tutto timeout: nascondi box e metti scritta
            box.set_visible(False)
            ax.text(
                positions[i],
                y_text_fixed,
                f"Timeout×{c_to}",
                rotation=90,
                ha="center",
                va="center",
                fontsize=9,
                fontweight="bold",
                color=ALGO_COLORS_UNIFIED.get(algo, "0.25"),
                alpha=0.90,
                clip_on=True,
                zorder=5,
            )
        else:
            box.set_facecolor(ALGO_COLORS_UNIFIED.get(algo, "0.8"))
            box.set_edgecolor("black")

            if c_to > 0:
                # timeout parziali: rendi box trasparente + scritta
                box.set_alpha(0.18)
                ax.text(
                    positions[i],
                    y_text_fixed,
                    f"Timeout×{c_to}",
                    rotation=90,
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color=ALGO_COLORS_UNIFIED.get(algo, "0.25"),
                    alpha=0.90,
                    clip_on=True,
                    zorder=5,
                )
            else:
                box.set_alpha(0.85)

    # ---- letters above boxes (B/G/R) ----
    _add_letters_above_boxes(ax, bp, positions, box_algos)

    # ---- axes ----
    ax.set_xticks(base)
    ax.set_xticklabels([str(n) for n in nodes_sorted])
    ax.set_xlabel("Number of nodes (CC + candidates + PMUs)")
    ax.set_ylabel("Algorithm time (s) [log scale]")

    ax.set_yscale("log")
    ax.set_ylim(y_lo, y_hi)

    ax.grid(True, axis="y", which="major", alpha=0.20)
    ax.grid(False, axis="y", which="minor")

    # ---- legend (keep it) ----
    _add_unified_legend(ax, alg_order=alg_order, colors=ALGO_COLORS_UNIFIED)

    fig.subplots_adjust(top=0.86, bottom=0.16)

    out = out_dir / "time_vs_nodes_boxplot_by_algorithm.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"📦 Boxplot saved to {out}")



def plot_pdcs_vs_candidates_bar(run_results_pdcs: list[dict], run_index: int):
    """
    Bar plot:
    X = number of candidate nodes
    Y = number of PDCs (including CC)
    3 barre: Bruteforce, Greedy, Random

    Salva in runtime_results/summarymode2.
    """

    if not run_results_pdcs:
        return

    alg_order = ["Bruteforce", "Greedy", "Random"]

    # Ordina per candidates
    run_results_pdcs.sort(key=lambda x: int(x["candidates"]))

    candidates = [int(x["candidates"]) for x in run_results_pdcs]
    series = {
        "Bruteforce": [int(x["Bruteforce"]) for x in run_results_pdcs],
        "Greedy":     [int(x["Greedy"]) for x in run_results_pdcs],
        "Random":     [int(x["Random"]) for x in run_results_pdcs],
    }

    x = np.arange(len(candidates))
    width = 0.25
    offsets = (np.arange(len(alg_order)) - (len(alg_order) - 1) / 2.0) * width

    fig, ax = plt.subplots()
    ax.set_title(
        f"Number of PDCs vs Candidates ( single run )",
        fontsize=12,
        pad=14,
    )
    # Barre + etichette B/G/R sopra
    for j, algo in enumerate(alg_order):
        xpos = x + offsets[j]
        vals = series[algo]

        bars = []
        for xi, val in zip(xpos, vals):

            if val == 1:
                # Timeout → niente barra
                ax.text(
                    xi,
                    0.3,                  # altezza fissa bassa
                    "Timeout",
                    ha="center",
                    va="bottom",
                    fontsize=10,
                    fontweight="bold",
                    rotation=90,
                    color=ALGO_COLORS_UNIFIED.get(algo, "black"),
                )
                bars.append(None)
            else:
                bar = ax.bar(
                    xi,
                    val,
                    width=width,
                    color=ALGO_COLORS_UNIFIED.get(algo, "0.8"),
                    edgecolor="black",
                    linewidth=0.8,
                )
                bars.append(bar[0])


        # Lettera sopra ogni barra (B/G/R)
        letter = SHORT_LETTER.get(algo, "")
        for rect in bars:
            if rect is None:
                continue
            h = rect.get_height()
            ax.text(
                rect.get_x() + rect.get_width() / 2.0,
                h + 0.05,               # piccolo offset verticale
                letter,
                ha="center",
                va="bottom",
                fontsize=9,
                color="0.25",
                clip_on=False,
            )

    #ax.set_title("Number of PDCs vs Candidates (CC included)")
    ax.set_xlabel("Number of candidate nodes")
    ax.set_ylabel("Number of PDCs (including CC)")
    ax.set_xticks(x)
    ax.set_xticklabels([str(c) for c in candidates])

    handles = [
        Patch(facecolor=ALGO_COLORS_UNIFIED[a], edgecolor="black", label=a)
        for a in alg_order
    ]

    ax.legend(
        handles=handles,
        loc="upper left",   # ← dentro, in alto a sinistra
        frameon=False,
        fontsize=9,
    )
    ax.grid(True, axis="y", alpha=0.25)
    plt.tight_layout()

    # Salvataggio in summarymode2
    plots_dir = _summary_mode2_dir()
    plots_dir.mkdir(parents=True, exist_ok=True)

    out_path = plots_dir / f"pdcs_vs_candidates_run{run_index}.pdf"
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print(f"✅ Saved PDC bar plot to: {out_path}")

def plot_mode2_final_pdcs_boxplot(*, timeout_value: int = 1):

    run_dirs = discover_run_dirs()
    blocks = group_run_dirs(run_dirs, block_size=MODE2_BLOCK_SIZE)

    all_pdcs: list[dict] = []
    for main_idx, blk in enumerate(blocks):
        try:
            _, results_pdcs = build_mode2_results_from_block(blk, main_run_idx=main_idx)
            all_pdcs.extend(results_pdcs)
        except Exception as e:
            print(f"⚠️ Skipping block {main_idx}: {e}")

    if not all_pdcs:
        print("❌ No valid data for PDC boxplot.")
        return

    alg_order = ["Bruteforce", "Greedy", "Random"]
    candidates_sorted = sorted({int(r["candidates"]) for r in all_pdcs})
    if not candidates_sorted:
        print("⚠️ No candidates to plot.")
        return

    # ---- collect per candidate + algo ----
    def collect_for_candidates(algo_key: str):
        data: list[list[float]] = []
        timeout_mask: list[bool] = []

        for c in candidates_sorted:
            vals_raw = [int(r[algo_key]) for r in all_pdcs if int(r["candidates"]) == c]
            vals_ok = [float(v) for v in vals_raw if v != timeout_value]

            if len(vals_ok) == 0:
                data.append([])        # niente box
                timeout_mask.append(True)
            else:
                data.append(vals_ok)
                timeout_mask.append(False)

        return data, timeout_mask

    data_by_algo = {}
    timeout_mask_by_algo = {}

    for algo in alg_order:
        d, m = collect_for_candidates(algo)
        data_by_algo[algo] = d
        timeout_mask_by_algo[algo] = m

    # y-limits
    all_ok = [v for algo in alg_order for group in data_by_algo[algo] for v in group]
    if not all_ok:
        print("⚠️ All values are timeouts; nothing to plot.")
        return

    Y_MAX_VIS = max(all_ok) * 1.30
    Y_MIN_VIS = 0.0

    # --- positions ---
    K = len(candidates_sorted)
    base = np.arange(K)

    nA = len(alg_order)
    width = 0.22
    offsets = (np.arange(nA) - (nA - 1) / 2.0) * width

    box_data = []
    box_algos = []
    positions = []

    for i_cand in range(K):
        for j, algo in enumerate(alg_order):
            box_data.append(data_by_algo[algo][i_cand])
            box_algos.append(algo)
            positions.append(float(base[i_cand] + offsets[j]))

    fig, ax = plt.subplots(figsize=(max(10, K * 1.8), 5.5))

    ax.set_title(
        f"Distribution of Algorithm Runtime vs Network Size (n = {len(blocks)} runs)",
        fontsize=12,
        pad=14,
    )
    
    bp = ax.boxplot(
        box_data,
        positions=positions,
        widths=width * 0.9,
        patch_artist=True,
        showfliers=True,
        manage_ticks=False,
    )

    # ---- styling + Timeout vertical text ----
    for i, (box, algo) in enumerate(zip(bp["boxes"], box_algos)):

        is_timeout = timeout_mask_by_algo[algo][i // nA]

        if is_timeout:
            # Nascondi box
            box.set_visible(False)

            ax.text(
                positions[i],
                Y_MAX_VIS * 0.5,
                "Timeout",
                rotation=90,
                ha="center",
                va="center",
                fontsize=10,
                fontweight="bold",
                color=ALGO_COLORS_UNIFIED.get(algo, "black"),
                alpha=0.85,
            )
        else:
            box.set_facecolor(ALGO_COLORS_UNIFIED.get(algo, "0.8"))
            box.set_edgecolor("black")
            box.set_alpha(0.85)

    for med in bp["medians"]:
        med.set_color("black")
        med.set_linewidth(1.6)

    for w in bp["whiskers"]:
        w.set_color("black")
        w.set_linewidth(1.2)

    for c in bp["caps"]:
        c.set_color("black")
        c.set_linewidth(1.2)

    _add_letters_above_boxes(ax, bp, positions, box_algos)

    ax.set_xticks(base)
    ax.set_xticklabels([str(c) for c in candidates_sorted])
    ax.set_xlabel("Number of candidate nodes")
    ax.set_ylabel("Number of PDCs (including CC)")
    ax.set_ylim(Y_MIN_VIS, Y_MAX_VIS)

    ax.grid(True, axis="y")

    handles = [
        Patch(facecolor=ALGO_COLORS_UNIFIED[a], edgecolor="black", label=a)
        for a in alg_order
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=9)

    fig.subplots_adjust(top=0.88, bottom=0.14)

    out_dir = _summary_mode2_dir()
    out = out_dir / "pdcs_vs_candidates_boxplot_by_algorithm.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)

    print(f"📦 PDC boxplot saved to {out}")



