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


# --- ID generation ---

_id_counter = 0

def _new_id(prefix):
    global _id_counter
    _id_counter += 1
    return f"{prefix}_{int(time.time()*1000)%10_000_000:07d}{_id_counter:03d}"


def _today():
    return time.strftime("%Y-%m-%d")


# --- Projects ---

def add_project(name):
    projects = load_json("projects.json", {})
    pid = _new_id("proj")
    projects[pid] = {"name": name, "createdAt": _today(), "archived": False}
    save_json("projects.json", projects)
    return pid


# --- Tasks ---

def add_task(project, title, priority="中", due="", nextAction="", blocked=False):
    tasks = load_json("tasks.json", {})
    tid = _new_id("task")
    tasks[tid] = {
        "project": project, "title": title, "status": "未开始",
        "priority": priority, "due": due, "nextAction": nextAction,
        "blocked": blocked, "draft": True, "createdAt": _today()
    }
    save_json("tasks.json", tasks)
    return tid


def update_task(tid, **fields):
    tasks = load_json("tasks.json", {})
    tasks[tid].update({k: v for k, v in fields.items() if v is not None})
    save_json("tasks.json", tasks)


def confirm_drafts():
    tasks = load_json("tasks.json", {})
    for t in tasks.values():
        t["draft"] = False
    save_json("tasks.json", tasks)


def delete_task(tid):
    tasks = load_json("tasks.json", {})
    tasks.pop(tid, None)
    save_json("tasks.json", tasks)
