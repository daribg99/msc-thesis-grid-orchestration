# test_functions/plotting.py
from __future__ import annotations
import csv
import matplotlib.pyplot as plt
from pathlib import Path
import re
import numpy as np
from typing import Dict, List
from matplotlib.patches import Patch   


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
#---------------------------------------JACCARD------------------------------------------------#


def plot_pdc_topology_jaccard(
    csv_path: Path,
    output_dir: Path | None = None,
    *,
    metric_col: str = "jaccard_distance",
    alg_labels: dict[str, str] | None = None,  
):
    # --- Read + group ---
    series_by_alg: dict[str, dict[int, float]] = {}
    all_t: set[int] = set()

    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            alg = (r.get("algorithm") or "").strip()
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
    plt.figure()

    for alg in sorted(series_by_alg.keys()):
        t_to_y = series_by_alg[alg]
        X = sorted(t_to_y.keys())     
        Y = [t_to_y[t] for t in X]

        label = alg_labels.get(alg, alg) if alg_labels else alg
        plt.plot(X, Y, marker="o", markersize=8, alpha=0.7, label=label)

    xticks = sorted(all_t)            
    plt.xticks(xticks, [f"T{t}" for t in xticks])
    plt.xlabel("Topology change index (T)")
    plt.ylabel(metric_col.replace("_", " ").title())
    plt.ylim(0.0, 1.0)
    plt.legend()
    plt.grid(True)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"pdc_topology_{metric_col}.pdf"
        plt.savefig(out, bbox_inches="tight")
        print(f"📊 Plot saved to {out}")
    else:
        plt.show()

    plt.close()


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

    fig.text(
        0.5, 0.96,
        f"n = {len(filtered_runs)} runs completed successfully",
        ha="center",
        va="top",
        fontsize=9,
        color="0.35",
    )

    fig.subplots_adjust(top=0.88, bottom=0.14)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "jaccard_boxplot_by_T_and_algo.pdf"
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

    fig.text(
        0.5, 0.96,
        f"n = {len(valid_runs)} runs completed successfully",
        ha="center",
        va="top",
        fontsize=9,
        color="0.35",
    )

    _add_unified_legend(ax, alg_order=alg_order, colors=ALGO_COLORS_UNIFIED)

    ax.set_xticks(base)
    ax.set_xticklabels([f"T{t}" for t in range(K)])

    ax.set_xlabel("Topology change index (T)")
    ax.set_ylabel("Time (s)")

    ax.grid(axis="y")
    
    fig.subplots_adjust(top=0.88, bottom=0.14)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "total_iteration_boxplot_by_T_and_algo.pdf"
        fig.savefig(out, bbox_inches="tight", pad_inches=0.2)
        print(f"📦 Total Iteration boxplot-by-T (per algo) saved to {out}")
    else:
        plt.show()

    plt.close(fig)
    
    
def plot_time_vs_nodes(results: list[dict]):
    

    SCRIPT_DIR = Path(__file__).resolve().parent          # .../TESI/test_functions
    REPO_ROOT  = SCRIPT_DIR.parent                        # .../TESI
    RUNTIME_ROOT  = REPO_ROOT / "runtime_results"
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

    THRESHOLD = 3 * 60 * 60  

    x = [r["nodes"] for r in results]
    yB_raw = [r["Bruteforce"] for r in results]
    yG_raw = [r["Greedy"] for r in results]
    yR_raw = [r["Random"] for r in results]

    all_raw = yB_raw + yG_raw + yR_raw
    finite_vals = [v for v in all_raw if v < THRESHOLD and np.isfinite(v)]

    if finite_vals:
        Y_MAX_VIS = max(finite_vals) * 1.30
    else:
        Y_MAX_VIS = float(THRESHOLD)

    def clamp(values):
        out = []
        for v in values:
            if (not np.isfinite(v)) or (v >= THRESHOLD):
                out.append(Y_MAX_VIS)
            else:
                out.append(float(v))
        return out

    yB = clamp(yB_raw)
    yG = clamp(yG_raw)
    yR = clamp(yR_raw)

    def jitter(values, factor):
        return [v * factor for v in values]

    yB_plot = jitter(yB, 1.00)  # reference
    yG_plot = jitter(yG, 1.03)  # +3%
    yR_plot = jitter(yR, 0.97)  # -3%

    # --- Plot ---
    plt.figure(figsize=(9, 5))
    plt.plot(x, yB_plot, marker="o", label="Bruteforce")
    plt.plot(x, yG_plot, marker="s", label="Greedy")
    plt.plot(x, yR_plot, marker="^", label="Random")

    plt.xlabel("Number of nodes (CC + candidates + PMUs)")

    nodes_sorted = sorted(set(x))
    plt.xticks(nodes_sorted, [str(n) for n in nodes_sorted])

    plt.ylabel("Algorithm time (s) [log scale]")
    plt.yscale("log")

    y_min = 1e-3
    plt.ylim(y_min, Y_MAX_VIS)

    plt.grid(True, which="both")
    plt.legend()

    y_anno = Y_MAX_VIS * 1.05

    def annotate_timeouts(y_raw):
        for xi, v in zip(x, y_raw):
            if v >= THRESHOLD or not np.isfinite(v):
                plt.annotate(
                    "Timeout ≥ 3h ↑",
                    (xi, y_anno),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    color="0.25",
                    clip_on=False,
                )

    annotate_timeouts(yB_raw)
    annotate_timeouts(yG_raw)
    annotate_timeouts(yR_raw)

    out = RUNTIME_ROOT / "time_vs_nodes_by_algorithm.pdf"
    plt.savefig(out, bbox_inches="tight", dpi=300)
    plt.close()
    print(f"📈 Final plot saved to {out}")


    

def plot_box_plot_time_vs_nodes(
    results: list[dict],
    output_dir: "Path | None" = None,
    *,
    alg_order: list[str] = ["Bruteforce", "Greedy", "Random"],
    threshold_s: float = 3 * 60 * 60,   # 3 ore
):
   

    SCRIPT_DIR = Path(__file__).resolve().parent          # .../TESI/test_functions
    REPO_ROOT  = SCRIPT_DIR.parent                        # .../TESI
    RUNTIME_ROOT  = REPO_ROOT / "runtime_results"
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

    nodes_sorted = sorted({int(r["nodes"]) for r in results})
    if not nodes_sorted:
        print("⚠️ No data to plot (empty results).")
        return

    def collect_for_nodes(algo_key: str):
        data: list[list[float]] = []
        timeout_counts: list[int] = []
        for n in nodes_sorted:
            vals_raw = [float(r[algo_key]) for r in results if int(r["nodes"]) == n]
            vals_ok = [v for v in vals_raw if np.isfinite(v) and v < threshold_s]
            timeouts = sum(1 for v in vals_raw if (not np.isfinite(v)) or (v >= threshold_s))
            data.append(vals_ok)
            timeout_counts.append(timeouts)
        return data, timeout_counts

    data_by_algo: dict[str, list[list[float]]] = {}
    timeouts_by_algo: dict[str, list[int]] = {}

    for algo in alg_order:
        data_by_algo[algo], timeouts_by_algo[algo] = collect_for_nodes(algo)

    all_ok = []
    for algo in alg_order:
        for group in data_by_algo[algo]:
            all_ok.extend([v for v in group if np.isfinite(v)])
    Y_MAX_VIS = (max(all_ok) * 1.30) if all_ok else float(threshold_s)

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

    num_nodes = len({r["nodes"] for r in results})
    num_runs = len(results) // num_nodes if num_nodes > 0 else 0

    fig.text(
        0.5, 0.96,
        f"n = {num_runs} runs completed successfully",
        ha="center",
        va="top",
        fontsize=9,
        color="0.35",
    )

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
    ax.set_xticklabels([str(n) for n in nodes_sorted])
    ax.set_xlabel("Number of nodes (CC + candidates + PMUs)")

    ax.set_yscale("log")
    ax.set_ylim(1e-3, Y_MAX_VIS)   
    ax.set_ylabel("Algorithm time (s) [log scale]")

    ax.grid(True, axis="y")

    _add_unified_legend(ax, alg_order=alg_order, colors=ALGO_COLORS_UNIFIED)

    y_anno = Y_MAX_VIS * 1.01
    for i_node in range(K):
        parts = []
        for algo in alg_order:
            c = timeouts_by_algo[algo][i_node]
            if c > 0:
                parts.append(f"{SHORT_LETTER.get(algo, algo[0])}: {c} timeout")
        if parts:
            ax.text(
                base[i_node],
                y_anno,
                "  ".join(parts),
                ha="center",
                va="bottom",
                fontsize=8,
                color="0.25",
                clip_on=False,
            )

    fig.subplots_adjust(top=0.88, bottom=0.16)

    if output_dir is None:
        out_dir = RUNTIME_ROOT
    else:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    out = out_dir / "time_vs_nodes_boxplot_by_algorithm.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"📦 Boxplot saved to {out}")

