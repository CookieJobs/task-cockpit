import json, os, time, uuid
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
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return default
    return json.loads(text)


def save_json(name, obj):
    p = data_dir() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


# --- ID generation ---

def _new_id(prefix):
    return f"{prefix}_{int(time.time()*1000):013d}{uuid.uuid4().hex[:6]}"


def _today():
    return time.strftime("%Y-%m-%d")


# --- Projects ---

def add_project(name):
    projects = load_json("projects.json", {})
    pid = _new_id("proj")
    projects[pid] = {"name": name, "createdAt": _today(), "archived": False}
    save_json("projects.json", projects)
    return pid


def update_project(pid, **fields):
    projects = load_json("projects.json", {})
    projects[pid].update({k: v for k, v in fields.items() if v is not None})
    save_json("projects.json", projects)


def delete_project(pid):
    projects = load_json("projects.json", {})
    projects.pop(pid, None)
    save_json("projects.json", projects)
    # Also delete all tasks belonging to this project
    tasks = load_json("tasks.json", {})
    tasks = {tid: t for tid, t in tasks.items() if t.get("project") != pid}
    save_json("tasks.json", tasks)


# --- Tasks ---

def add_task(project, title, priority="中", due="", nextAction="", blocked=False, checklist=None):
    tasks = load_json("tasks.json", {})
    tid = _new_id("task")
    tasks[tid] = {
        "project": project, "title": title, "status": "未开始",
        "priority": priority, "due": due, "nextAction": nextAction,
        "blocked": blocked, "draft": True, "createdAt": _today(),
        "checklist": checklist or [],
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


# --- Achievements ---

def read_achievements():
    p = data_dir() / "achievements.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_achievements(items):
    p = data_dir() / "achievements.jsonl"
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    os.replace(tmp, p)


def complete_task(tid, outcome="", reflection="", cv="", cv_status="ready"):
    tasks = load_json("tasks.json", {})
    task = tasks[tid]
    projects = load_json("projects.json", {})
    pname = projects.get(task["project"], {}).get("name", task["project"])
    aid = _new_id("done")
    items = read_achievements()
    items.append({
        "id": aid, "date": _today(), "taskId": tid,
        "projectId": task["project"], "project": pname,
        "title": task["title"], "outcome": outcome,
        "reflection": reflection, "cv": cv, "cvStatus": cv_status,
        "_task": task
    })
    # Write achievement FIRST — crash here leaves a duplicate, not a lost item
    _write_achievements(items)
    tasks.pop(tid)
    save_json("tasks.json", tasks)
    return aid


def update_achievement_cv(aid, cv=None, cv_status=None):
    items = read_achievements()
    for it in items:
        if it["id"] == aid:
            if cv is not None:
                it["cv"] = cv
            if cv_status is not None:
                it["cvStatus"] = cv_status
    _write_achievements(items)


def undo_completion(aid):
    items = read_achievements()
    target = next(it for it in items if it["id"] == aid)
    remaining = [it for it in items if it["id"] != aid]
    # Restore task FIRST — crash here leaves a recoverable duplicate
    tasks = load_json("tasks.json", {})
    task = target["_task"]
    task["status"] = "进行中"
    task["draft"] = False
    tasks[target["taskId"]] = task
    save_json("tasks.json", tasks)
    _write_achievements(remaining)


# --- Snapshot / focus ranking ---

_PRIORITY_RANK = {"高": 0, "中": 1, "低": 2}


def _focus_key(t):
    blocked = 1 if t.get("blocked") else 0
    return (blocked, _PRIORITY_RANK.get(t.get("priority"), 1), t.get("due") or "9999-99-99")


def build_snapshot():
    projects = load_json("projects.json", {})
    tasks = load_json("tasks.json", {})
    enriched = [dict(id=tid, **t) for tid, t in tasks.items()]

    # Item 1: exclude drafts from focus; Item 2: blocked sorts after non-blocked
    focus_candidates = [t for t in enriched if not t.get("draft")]
    ordered = sorted(focus_candidates, key=_focus_key)
    # Item 3: no 'flagged' key — dashboard reads t.blocked directly
    focus = [dict(t) for t in ordered[:5]]

    grouped = []
    known_pids = set()
    for pid, p in projects.items():
        # Item 5: always add pid to known_pids (archived or not), so their
        # tasks don't leak into "未分组"
        known_pids.add(pid)
        if p.get("archived"):
            continue
        pts = [t for t in enriched if t["project"] == pid]
        grouped.append({"id": pid, "name": p["name"], "tasks": pts})

    # Only tasks with a truly unknown project id go to "未分组"
    orphans = [t for t in enriched if t["project"] not in known_pids]
    if orphans:
        grouped.append({"id": None, "name": "未分组", "tasks": orphans})

    # Item 7: defensive reads — malformed achievement lines use .get() with defaults
    ach = read_achievements()
    today = _today()
    done_today = [a for a in ach if a.get("date", "") == today]
    counts = {
        "achievementsReady": sum(1 for a in ach if a.get("cvStatus") == "ready"),
        "achievementsPending": sum(1 for a in ach if a.get("cvStatus") == "pending"),
    }
    return {"focus": focus, "projects": grouped, "doneToday": done_today, "counts": counts}


# --- CLI ---

import argparse


def _cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--json", default="{}")
    args = parser.parse_args()
    try:
        a = json.loads(args.json)
        cmd = args.command
        if cmd == "add-project":
            out = {"id": add_project(a["name"])}
        elif cmd == "add-task":
            out = {"id": add_task(a["project"], a["title"], a.get("priority", "中"),
                                  a.get("due", ""), a.get("nextAction", ""), a.get("blocked", False))}
        elif cmd == "update-task":
            update_task(a.pop("id"), **a); out = {"ok": True}
        elif cmd == "update-project":
            update_project(a.pop("id"), **a); out = {"ok": True}
        elif cmd == "confirm-drafts":
            confirm_drafts(); out = {"ok": True}
        elif cmd == "complete-task":
            out = {"id": complete_task(a["id"], a.get("outcome", ""), a.get("reflection", ""),
                                       a.get("cv", ""), a.get("cv_status", "ready"))}
        elif cmd == "update-cv":
            update_achievement_cv(a["id"], a.get("cv"), a.get("cv_status")); out = {"ok": True}
        elif cmd == "undo":
            undo_completion(a["id"]); out = {"ok": True}
        elif cmd == "delete-task":
            delete_task(a["id"]); out = {"ok": True}
        elif cmd == "snapshot":
            out = build_snapshot()
        elif cmd == "achievements":
            items = read_achievements()
            if a.get("project"):
                items = [i for i in items if i["project"] == a["project"]]
            if a.get("since"):
                items = [i for i in items if i["date"] >= a["since"]]
            out = {"items": items}
        else:
            out = {"error": f"unknown command {cmd}"}
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
