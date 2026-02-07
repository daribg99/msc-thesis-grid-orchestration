import os
import csv
from pathlib import Path

def append_metrics_csv(
    csv_path: Path,
    T: int,
    churn_val: float,
    jaccard_val: float,
    added: int,
    removed: int,
    *,
    algorithm: str = "",
    note: str = "",
):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()

    fieldnames = ["algorithm", "T", "churn", "jaccard_distance", "added", "removed", "note"]

    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            w.writeheader()

        w.writerow({
            "algorithm": algorithm,
            "T": T,
            "churn": f"{churn_val:.6f}",
            "jaccard_distance": f"{jaccard_val:.6f}",
            "added": added,
            "removed": removed,
            "note": note,
        })


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


