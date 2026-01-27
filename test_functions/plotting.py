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
    # Ordine fisso per le 3 colonne per ogni T
    alg_order = ["Greedy", "Bruteforce", "Random"]

    # Regex: Placement-ALGO <time>
    placement_re = re.compile(r".*\bPlacement-(Greedy|Bruteforce|Random)\b\s+(.+)$", re.IGNORECASE)
    deployer_re  = re.compile(r".*\bDeployer\b\s+(.+)$", re.IGNORECASE)
    applier_re   = re.compile(r".*\bApplier\b\s+(.+)$", re.IGNORECASE)

    # raccoglie record completi: (algo, placement_ms, deployer_ms, applier_ms)
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

            # Normalizza NBSP e spazi multipli
            line = line.replace("\u00a0", " ")
            line = " ".join(line.split())

            m = placement_re.match(line)
            if m:
                # se per qualche motivo era rimasto un blocco incompleto, lo scartiamo e ripartiamo
                cur_algo = m.group(1).capitalize()
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

            # ignora Total Iteration e qualsiasi altra riga

    if not records:
        print("⚠️ No runtime data to plot (no complete algo blocks parsed).")
        print(f"DEBUG file: {runtime_csv}")
        return

    # Raggruppa per T: ogni T deve avere 3 record (uno per alg in alg_order)
    groups = []
    i = 0
    while i + 2 < len(records):
        chunk = records[i:i+3]
        # verifica che ci siano tutti e 3 gli algoritmi
        chunk_algos = [a for (a, _, _, _) in chunk]
        # se l’ordine non è garantito nel file, riordiniamo
        chunk_map = {a: (p, d, ap) for (a, p, d, ap) in chunk}
        if all(a in chunk_map for a in alg_order):
            groups.append([chunk_map[a] for a in alg_order])  # [(p,d,ap) greedy, bruteforce, random]
            i += 3
        else:
            # se il chunk non è “pulito”, prova a scorrere di 1 (fallback robusto)
            i += 1

    nT = len(groups)
    if nT == 0:
        print("⚠️ Parsed algo blocks, but could not form any complete T group of 3 algos.")
        print(f"DEBUG records parsed: {len(records)} -> {records[:5]} ...")
        return

    # Costruisci matrici shape (nT, 3)
    placement = np.array([[g[j][0] for j in range(3)] for g in groups], dtype=float) / 1000.0
    deployer  = np.array([[g[j][1] for j in range(3)] for g in groups], dtype=float) / 1000.0
    applier   = np.array([[g[j][2] for j in range(3)] for g in groups], dtype=float) / 1000.0

    T = np.arange(1, nT + 1)

    # Posizioni: 3 barre per ogni T
    width = 0.25
    offsets = np.array([-width, 0.0, width])
    x = np.repeat(T, 3) + np.tile(offsets, nT)

    placement_flat = placement.reshape(-1)
    deployer_flat  = deployer.reshape(-1)
    applier_flat   = applier.reshape(-1)

    plt.figure()

    # Barre stacked (stesso colore per componente; non separiamo per algoritmo via colore, ma via posizione)
    plt.bar(x, placement_flat, width=width, label="Placement")
    plt.bar(x, deployer_flat,  width=width, bottom=placement_flat, label="Deployer")
    plt.bar(x, applier_flat,   width=width, bottom=placement_flat + deployer_flat, label="Applier")

    # Ticks centrati su ogni T
    plt.xlabel("Topology change index (T)")
    plt.ylabel("Time (s)")
    plt.xticks(T, [str(t) for t in T])

    # Legenda componenti
    plt.legend()
    plt.grid(axis="y")

    width = 0.25
    offsets = np.array([-width, 0.0, width])
    x = np.repeat(T, 3) + np.tile(offsets, nT)

    placement_flat = placement.reshape(-1)
    deployer_flat  = deployer.reshape(-1)
    applier_flat   = applier.reshape(-1)

    plt.figure()

    # Barre stacked
    plt.bar(x, placement_flat, width=width, label="Placement")
    plt.bar(x, deployer_flat,  width=width, bottom=placement_flat, label="Deployer")
    plt.bar(x, applier_flat,   width=width, bottom=placement_flat + deployer_flat, label="Applier")

    # Tick principali: solo i T (centrati)
    plt.xlabel("Topology change index (T)")
    plt.ylabel("Time (s)")
    plt.xticks(T, [str(t) for t in T])

    # ---- Etichette algoritmo sotto ogni gruppo ----
    algo_labels = ["G", "B", "R"]  # oppure ["Greedy", "Bruteforce", "Random"]

    for i, t in enumerate(T):
        base_x = t
        for j, lbl in enumerate(algo_labels):
            plt.text(
                base_x + offsets[j],
                -0.02 * (placement + deployer + applier).max(),  # leggermente sotto l'asse
                lbl,
                ha="center",
                va="top",
                fontsize=9,
                rotation=0
            )

    # Linea separatrice leggera sotto l'asse
    plt.axhline(0, linewidth=0.8)

    # Legenda componenti
    plt.legend()
    plt.grid(axis="y")

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "runtime_stacked_per_iteration_3algos.png"
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
