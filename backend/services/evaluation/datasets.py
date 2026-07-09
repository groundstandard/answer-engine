"""Golden evaluation datasets (PRD Phase 2 — 3 dataset types)."""
import json
from pathlib import Path
from typing import List

# backend/services/evaluation/datasets.py -> answer-engine/evaluation_datasets
_DIR = Path(__file__).resolve().parents[3] / "evaluation_datasets"


def list_datasets() -> List[str]:
    """Names of available golden datasets."""
    if not _DIR.exists():
        return []
    return sorted(p.stem for p in _DIR.glob("*.json"))


def load_dataset(name: str) -> dict:
    """Load a golden dataset by name. Raises FileNotFoundError if missing."""
    path = _DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Unknown dataset '{name}'. Available: {', '.join(list_datasets()) or 'none'}"
        )
    return json.loads(path.read_text(encoding="utf-8"))
