import json, os, time
from pathlib import Path


def data_dir() -> Path:
    d = os.environ.get("TASK_COCKPIT_DIR")
    base = Path(d) if d else Path.home() / ".task-cockpit"
    base.mkdir(parents=True, exist_ok=True)
    (base / "cv-exports").mkdir(exist_ok=True)
    return base


def load_json(name, default):
    p = data_dir() / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8") or "null") or default


def save_json(name, obj):
    p = data_dir() / name
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
