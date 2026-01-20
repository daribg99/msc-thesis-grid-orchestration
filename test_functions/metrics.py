import os

def pdcs_set(data: dict, exclude_cc: bool = True) -> set:
    s = set(data.get("pdcs", []))
    if exclude_cc:
        s.discard("CC")
    return s

def churn(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 0.0
    return (len(a - b) + len(b - a)) / len(union)

def jaccard_distance(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 0.0
    return 1.0 - (len(a & b) / len(union))

def append_metrics_csv(
    csv_path,
    t: int,
    churn_v: float,
    jdist_v: float,
    added: int,
    removed: int
):
    header = "T,churn,jaccard_distance,added,removed\n"
    line = f"{t},{churn_v:.6f},{jdist_v:.6f},{added},{removed}\n"

    if not os.path.exists(csv_path):
        with open(csv_path, "w") as f:
            f.write(header)

    with open(csv_path, "a") as f:
        f.write(line)
