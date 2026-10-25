from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Dataset:
    key: str
    repo: str
    dir: Path


DATASETS = {
    "main": Dataset("main", "camelCase12/vpct-1", ROOT / "data"),
    "redux": Dataset("redux", "camelCase12/vpct-redux", ROOT / "data-redux"),
}


@dataclass(frozen=True)
class Problem:
    dataset: str
    id: int
    image: Path
    answer: int


def download(ds: Dataset) -> None:
    from huggingface_hub import snapshot_download

    ds.dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(ds.repo, repo_type="dataset", local_dir=str(ds.dir))


def load(key: str) -> list[Problem]:
    ds = DATASETS[key]
    probs = []
    for res in ds.dir.glob("sim_*_results.json"):
        sid = int(res.name.split("_")[1])
        img = ds.dir / f"sim_{sid}_initial.png"
        if img.exists():
            probs.append(Problem(key, sid, img, json.loads(res.read_text())["finalBucket"]))
    if not probs:
        raise SystemExit(f"no problems in {ds.dir} — run: python -m vpct download")
    return sorted(probs, key=lambda p: p.id)


def resolve(spec: str) -> list[str]:
    keys = list(DATASETS) if spec == "all" else [s.strip() for s in spec.split(",") if s.strip()]
    for k in keys:
        if k not in DATASETS:
            raise SystemExit(f"unknown dataset {k!r} (have {', '.join(DATASETS)})")
    return keys
