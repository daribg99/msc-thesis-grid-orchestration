from pathlib import Path
from datetime import datetime
import json
import os

def load_iter(iter_file: Path) -> int:
    try:
        return int(iter_file.read_text().strip())
    except Exception:
        return 0

def save_iter(iter_file: Path, i: int):
    iter_file.write_text(str(i))

def save_snapshot(
    iteration: int,
    data: dict,
    snapshots_dir: Path
) -> Path:
    os.makedirs(snapshots_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = snapshots_dir / f"snapshot_{iteration:04d}_{ts}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    return path
