# test_functions/plotting.py

import csv
import matplotlib.pyplot as plt
from pathlib import Path
import re
import numpy as np

#---------------------------------------JACCARD------------------------------------------------#

def plot_pdc_topology_jaccard(
    csv_path: Path,
    output_dir: Path | None = None,
    *,
    num_algorithms: int = 3,
    skip_blocks: int = 1,
    K: int | None = None,
    metric_col: str = "jaccard_distance",
):
    # ---- Read rows ----
    rows = []
    alg_labels: list[str] = ["Bruteforce", "Greedy", "Random"]

    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("⚠️ Empty CSV.")
        return

    # ---- Compute available complete blocks ----
    total_blocks = len(rows) // num_algorithms
    if total_blocks == 0:
        print("⚠️ Not enough rows to form a single complete block.")
        return

    if skip_blocks >= total_blocks:
        print(
            f"⚠️ skip_blocks={skip_blocks} but only {total_blocks} block(s) available."
        )
        return

    # ---- Determine how many blocks to plot ----
    available_blocks = total_blocks - skip_blocks
    if K is None or K > available_blocks:
        K = available_blocks

    if K <= 0:
        print("⚠️ Nothing to plot after applying skip_blocks/K.")
        return

    # ---- Build series per algorithm (X = event index) ----
    algo_series = [{"X": [], "Y": []} for _ in range(num_algorithms)]

    for b in range(skip_blocks, skip_blocks + K):
        event_idx = b - skip_blocks  # 0,1,2,...

        block_rows = rows[
            b * num_algorithms : (b + 1) * num_algorithms
        ]

        # sicurezza extra (non dovrebbe servire, ma è robusto)
        if len(block_rows) < num_algorithms:
            break

        for algo_idx, r in enumerate(block_rows):
            try:
                y = float(r[metric_col])
            except (KeyError, ValueError):
                continue

            algo_series[algo_idx]["X"].append(event_idx)
            algo_series[algo_idx]["Y"].append(y)

    # ---- Plot ----

    # ---- Plot ----
    plt.figure()

    for i, s in enumerate(algo_series):
        if not s["X"]:
            continue

        # i = 0,1,2...
        if isinstance(alg_labels, (list, tuple)) and i < len(alg_labels):
            name = alg_labels[i]
        else:
            name = f"Algorithm {i+1}"

        plt.plot(s["X"], s["Y"], marker="o", label=name)



    xticks = list(range(K))
    plt.xticks(xticks, [str(i + 1) for i in xticks])  # eventi 1,2,3,...
    plt.xlabel("Topology change event index")
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
    # Regex: Placement-ALGO <time>
    placement_re = re.compile(r"^Placement-(Greedy|Bruteforce|Random)\s+(.+)$", re.IGNORECASE)
    deployer_re  = re.compile(r"^Deployer\s+(.+)$", re.IGNORECASE)
    applier_re   = re.compile(r"^Applier\s+(.+)$", re.IGNORECASE)

    # record completi in ordine file: (algo, placement_ms, deployer_ms, applier_ms)
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
                # se c'era un blocco incompleto, lo scarto e riparto
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

            # ignora Total Iteration e altre righe

    if not records:
        print("⚠️ No runtime data to plot (no complete blocks parsed).")
        print(f"DEBUG file: {runtime_csv}")
        return

    # ---- Raggruppo per algoritmo (file per-algoritmo) ----
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

    # ---- Robustezza: uso il minimo comune tra gli algoritmi presenti ----
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

    # ---- Matrici (K, nA) ----
    nA = len(present_algos)
    placement = np.zeros((K, nA), dtype=float)
    deployer  = np.zeros((K, nA), dtype=float)
    applier   = np.zeros((K, nA), dtype=float)

    for j, algo in enumerate(present_algos):
        series = per_algo[algo][skip_T:skip_T + K]
        placement[:, j] = [x[0] for x in series]
        deployer[:,  j] = [x[1] for x in series]
        applier[:,   j] = [x[2] for x in series]

    # ms -> s
    placement /= 1000.0
    deployer  /= 1000.0
    applier   /= 1000.0

    # Event index (0..K-1)
    T = np.arange(0, K)

    # x positions (nA bars per T)
    width = 0.25 if nA == 3 else min(0.25, 0.8 / max(nA, 1))
    offsets = (np.arange(nA) - (nA - 1) / 2.0) * width
    x = np.repeat(T, nA) + np.tile(offsets, K)

    placement_flat = placement.reshape(-1)
    deployer_flat  = deployer.reshape(-1)
    applier_flat   = applier.reshape(-1)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(x, placement_flat, width=width, label="Placement")
    ax.bar(x, deployer_flat,  width=width, bottom=placement_flat, label="Deployer")
    ax.bar(x, applier_flat,   width=width, bottom=placement_flat + deployer_flat, label="Applier")

    ax.set_xlabel("Topology change event index")
    ax.set_ylabel("Time (s)")
    ax.set_xticks(T)
    ax.set_xticklabels([str(t) for t in T])

    # ---- Etichette algoritmo sopra ogni colonna (dentro figura) ----
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
    required_T: int | None = None,   # se None: usa il minimo T comune tra le run valide
):
    """
    For each topology-change event index T (0..K-1), build 3 side-by-side boxplots
    (one per algorithm) of Total Iteration times across runs.

    Runtime file format is per-algorithm blocks:
        Placement-<Algo>
        Deployer
        Applier
        Total Iteration  <time>
        ... repeated for T
        then next algorithm, etc.

    If a run is missing any required Total Iteration block for any algorithm, the whole run is discarded.
    """

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

        # --- Validate this run: must have all algos and consistent lengths ---
        present_algos = [a for a in alg_order if len(per_algo_totals[a]) > 0]
        if len(present_algos) != len(alg_order):
            # manca un algoritmo -> scarta run
            continue

        lengths = [len(per_algo_totals[a]) for a in alg_order]
        if len(set(lengths)) != 1:
            # numero di T diverso tra algoritmi -> scarta run
            continue

        if lengths[0] == 0:
            continue

        valid_runs.append(per_algo_totals)

    if not valid_runs:
        print("⚠️ No valid runs found (missing blocks or inconsistent lengths).")
        return

    # Decide K (numero di T da considerare)
    K_per_run = [len(r[alg_order[0]]) for r in valid_runs]
    K_common = min(K_per_run)

    if required_T is None:
        K = K_common
    else:
        K = min(required_T, K_common)

    if K <= 0:
        print("⚠️ No T left to plot after applying required_T/min-common.")
        return

    # --- Build box data ---
    # For each T, for each algo -> list of samples across runs (seconds)
    box_data: list[list[float]] = []
    positions: list[float] = []

    # Layout: for each T, 3 boxes centered at T with small offsets
    nA = len(alg_order)
    base = np.arange(K)  # 0..K-1
    width = 0.22 if nA == 3 else min(0.22, 0.8 / max(nA, 1))
    offsets = (np.arange(nA) - (nA - 1) / 2.0) * width

    for t in range(K):
        for j, algo in enumerate(alg_order):
            samples = [run[algo][t] / 1000.0 for run in valid_runs]  # seconds
            box_data.append(samples)
            positions.append(base[t] + offsets[j])

    fig, ax = plt.subplots(figsize=(max(9, K * 1.4), 6))

    algo_colors = {
        "Bruteforce": "#1f77b4",  # blu
        "Greedy":     "#2ca02c",  # verde
        "Random":     "#d62728",  # rosso
    }

    bp = ax.boxplot(
        box_data,
        positions=positions,
        widths=width * 0.9,
        patch_artist=True,
        showfliers=True,
        manage_ticks=False,
    )

    # Tick principali: T0, T1, ...
    ax.set_xticks(base)
    ax.set_xticklabels([f"T{t}" for t in range(K)])
    ax.set_xlabel("Topology change index (T)")
    ax.set_ylabel("Total iteration time (s)")
    ax.grid(axis="y")

    # --- Colora i box per algoritmo ---
    for i, box in enumerate(bp["boxes"]):
        algo = alg_order[i % len(alg_order)]   # cicla B,G,R
        box.set_facecolor(algo_colors[algo])
        box.set_alpha(0.75)
        box.set_edgecolor("black")

    # Etichette algoritmo sopra ogni box (dentro figura)
    # --- Lettere B/G/R sopra ogni box (ancorate ai whisker) ---
    short = {"Bruteforce": "B", "Greedy": "G", "Random": "R"}

    # ogni box ha 2 whisker: prendiamo quello superiore
    whiskers = bp["whiskers"]

    box_idx = 0
    for t in range(K):
        for j, algo in enumerate(alg_order):
            # whisker superiore del box corrente
            w = whiskers[2 * box_idx + 1]
            y_top = max(w.get_ydata())

            ax.text(
                positions[box_idx],
                y_top * 1.03,   # leggermente sopra il box
                short[algo],
                ha="center",
                va="bottom",
                fontsize=9,
                color="0.25",
            )

            box_idx += 1


    fig.text(
        0.5, 0.96,
        f"n = {len(valid_runs)} runs completed successfully",
        ha="center",
        va="top",
        fontsize=9,
        color="0.35",
    )

    from matplotlib.patches import Patch

    algo_legend = [
        Patch(facecolor="none", edgecolor="none", label="B = Bruteforce"),
        Patch(facecolor="none", edgecolor="none", label="G = Greedy"),
        Patch(facecolor="none", edgecolor="none", label="R = Random"),
    ]

    ax.legend(
        handles=algo_legend,
        loc="upper right",
        frameon=False,
        fontsize=9,
    )


    fig.subplots_adjust(top=0.88, bottom=0.14)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "total_iteration_boxplot_by_T_and_algo.pdf"
        fig.savefig(out, bbox_inches="tight", pad_inches=0.2)
        print(f"📦 Total Iteration boxplot-by-T (per algo) saved to {out}")
    else:
        plt.show()

    plt.close(fig)

