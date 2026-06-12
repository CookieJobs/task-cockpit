# Task Cockpit 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Claude Code skill：用户在对话里倒事，agent 拆解任务入库、维护只读看板回答"该先干啥"，并在每个任务完成时即时沉淀可用的成就陈述。

**Architecture:** 三层。`cockpit.py` 是纯 Python 数据层 + CLI（全部业务逻辑与单测都在此），agent 通过调用其子命令读写 `~/.task-cockpit/` 下的 JSON 文件。`server.py` 复用 `cockpit.py` 的读取与计算函数，在固定端口、仅监听 127.0.0.1、无闲置超时地托管看板与数据 API。`dashboard.html` 每 2 秒轮询数据 API 自渲染。`SKILL.md` 告诉 agent 识别意图并调用对应 CLI 命令。

**Tech Stack:** Python 3 标准库（`http.server`、`json`、`pathlib`、`argparse`、`unittest`）；零第三方依赖，保证可移植与将来 plugin 分发。

---

## 文件结构

开发目录设为一个独立 git 仓库（便于频繁提交，也契合用户"日后推 GitHub 分发"的目标）：`~/Documents/claudecodeWorkspace/task-cockpit/`。安装为 skill = 将该目录软链接到 `~/.claude/skills/task-cockpit`。

- `task-cockpit/cockpit.py` — 数据层库 + CLI 调度。职责：数据目录解析、读写三文件、增删改任务、确认草稿、完成/撤销、聚焦与计数计算。**所有业务逻辑集中于此，唯一被单测覆盖的文件。**
- `task-cockpit/server.py` — HTTP 服务。职责：`GET /` 返回看板、`GET /api/data` 返回组合快照（导入 cockpit 的读取+计算函数）、`GET /api/health` 健康检查；固定端口 7842，绑定 127.0.0.1，无闲置超时。
- `task-cockpit/dashboard.html` — 看板模板。职责：渲染顶部聚焦 + 按项目分块 + 草稿高亮 + 今日已完成可折叠区 + 累计计数；每 2s 轮询 `/api/data`。
- `task-cockpit/SKILL.md` — 工作流说明。职责：让 agent 识别"倒事/改任务/完成/问局势/总结成果"意图并调用对应 CLI。
- `task-cockpit/tests/test_cockpit.py` — `cockpit.py` 的 unittest 测试。

数据文件（运行时生成于用户家目录，不进仓库）：`~/.task-cockpit/{projects.json, tasks.json, achievements.jsonl, cv-exports/}`。

---

### Task 0: 初始化项目骨架

**Files:**
- Create: `task-cockpit/.gitignore`
- Create: `task-cockpit/tests/__init__.py` (空文件)

- [ ] **Step 1: 建目录与 git 仓库**

```bash
mkdir -p ~/Documents/claudecodeWorkspace/task-cockpit/tests
cd ~/Documents/claudecodeWorkspace/task-cockpit
git init
touch tests/__init__.py
```

- [ ] **Step 2: 写 .gitignore**

```
__pycache__/
*.pyc
.DS_Store
```

- [ ] **Step 3: 首次提交**

```bash
git add -A && git commit -m "chore: scaffold task-cockpit project"
```

---

### Task 1: 数据目录解析与读写基元

**Files:**
- Create: `task-cockpit/cockpit.py`
- Test: `task-cockpit/tests/test_cockpit.py`

- [ ] **Step 1: 写失败测试**

```python
import os, json, tempfile, unittest
from pathlib import Path
import importlib

class DataLayerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["TASK_COCKPIT_DIR"] = self.tmp
        import cockpit; importlib.reload(cockpit); self.c = cockpit

    def test_data_dir_respects_env(self):
        self.assertEqual(str(self.c.data_dir()), self.tmp)

    def test_load_missing_returns_default(self):
        self.assertEqual(self.c.load_json("projects.json", {}), {})

    def test_save_then_load_roundtrip(self):
        self.c.save_json("projects.json", {"p1": {"name": "X"}})
        self.assertEqual(self.c.load_json("projects.json", {})["p1"]["name"], "X")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd ~/Documents/claudecodeWorkspace/task-cockpit && python3 -m unittest tests.test_cockpit -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'cockpit'`）

- [ ] **Step 3: 实现 cockpit.py 数据基元**

```python
import json, os
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_cockpit -v`
Expected: PASS（3 测试）

- [ ] **Step 5: 提交**

```bash
git add cockpit.py tests/test_cockpit.py && git commit -m "feat: data dir resolution and json read/write primitives"
```

---

### Task 2: 项目与任务增改（含草稿）

**Files:**
- Modify: `task-cockpit/cockpit.py`
- Test: `task-cockpit/tests/test_cockpit.py`

- [ ] **Step 1: 追加失败测试**

```python
class TaskOpsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["TASK_COCKPIT_DIR"] = self.tmp
        import cockpit; importlib.reload(cockpit); self.c = cockpit

    def test_add_project_returns_id(self):
        pid = self.c.add_project("App 改版")
        self.assertTrue(pid.startswith("proj_"))
        self.assertEqual(self.c.load_json("projects.json", {})[pid]["name"], "App 改版")

    def test_add_task_defaults_to_draft(self):
        pid = self.c.add_project("App 改版")
        tid = self.c.add_task(pid, "登录页改稿", priority="高")
        t = self.c.load_json("tasks.json", {})[tid]
        self.assertTrue(t["draft"])
        self.assertEqual(t["status"], "未开始")
        self.assertEqual(t["priority"], "高")

    def test_update_task_changes_fields(self):
        pid = self.c.add_project("P")
        tid = self.c.add_task(pid, "T")
        self.c.update_task(tid, due="2026-06-12", nextAction="等设计", blocked=True)
        t = self.c.load_json("tasks.json", {})[tid]
        self.assertEqual(t["due"], "2026-06-12")
        self.assertTrue(t["blocked"])

    def test_confirm_drafts_clears_flag(self):
        pid = self.c.add_project("P")
        tid = self.c.add_task(pid, "T")
        self.c.confirm_drafts()
        self.assertFalse(self.c.load_json("tasks.json", {})[tid]["draft"])

    def test_delete_task_removes_it(self):
        pid = self.c.add_project("P")
        tid = self.c.add_task(pid, "T")
        self.c.delete_task(tid)
        self.assertNotIn(tid, self.c.load_json("tasks.json", {}))
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_cockpit.TaskOpsTest -v`
Expected: FAIL（`AttributeError: module 'cockpit' has no attribute 'add_project'`）

- [ ] **Step 3: 实现（追加到 cockpit.py）**

```python
import time

def _new_id(prefix):
    return f"{prefix}_{int(time.time()*1000)%10_000_000:07d}"

def _today():
    return time.strftime("%Y-%m-%d")

def add_project(name):
    projects = load_json("projects.json", {})
    pid = _new_id("proj")
    projects[pid] = {"name": name, "createdAt": _today(), "archived": False}
    save_json("projects.json", projects)
    return pid

def add_task(project, title, priority="中", due="", nextAction="", blocked=False):
    tasks = load_json("tasks.json", {})
    tid = _new_id("task")
    tasks[tid] = {"project": project, "title": title, "status": "未开始",
                  "priority": priority, "due": due, "nextAction": nextAction,
                  "blocked": blocked, "draft": True, "createdAt": _today()}
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_cockpit -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add cockpit.py tests/test_cockpit.py && git commit -m "feat: project/task create, update, confirm-drafts, delete"
```

---

### Task 3: 完成任务（沉淀成就）与撤销

**Files:**
- Modify: `task-cockpit/cockpit.py`
- Test: `task-cockpit/tests/test_cockpit.py`

完成任务时：从 `tasks.json` 移除该任务，向 `achievements.jsonl` 追加一条记录（含成果、复盘、CV 陈述、CV 状态、所属项目名）。撤销时：从成就库移除该条，任务恢复回 `tasks.json`（状态置"进行中"）。成就记录自带 `projectId` 与原任务快照，使撤销可无损还原。

- [ ] **Step 1: 追加失败测试**

```python
class CompletionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["TASK_COCKPIT_DIR"] = self.tmp
        import cockpit; importlib.reload(cockpit); self.c = cockpit
        self.pid = self.c.add_project("App 改版")
        self.tid = self.c.add_task(self.pid, "登录页改稿")
        self.c.confirm_drafts()

    def test_complete_moves_task_to_achievements(self):
        aid = self.c.complete_task(self.tid, outcome="提测完成",
                                   reflection="早点对设计", cv="主导登录页改版",
                                   cv_status="ready")
        self.assertNotIn(self.tid, self.c.load_json("tasks.json", {}))
        items = self.c.read_achievements()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], aid)
        self.assertEqual(items[0]["project"], "App 改版")
        self.assertEqual(items[0]["cvStatus"], "ready")
        self.assertEqual(items[0]["date"], self.c._today())

    def test_pending_cv_status_preserved(self):
        self.c.complete_task(self.tid, outcome="做完了", cv="", cv_status="pending")
        self.assertEqual(self.c.read_achievements()[0]["cvStatus"], "pending")

    def test_update_achievement_cv_promotes_to_ready(self):
        aid = self.c.complete_task(self.tid, outcome="做完了", cv="", cv_status="pending")
        self.c.update_achievement_cv(aid, cv="影响 10w 用户", cv_status="ready")
        items = self.c.read_achievements()
        self.assertEqual(items[0]["cv"], "影响 10w 用户")
        self.assertEqual(items[0]["cvStatus"], "ready")

    def test_undo_completion_restores_task(self):
        aid = self.c.complete_task(self.tid, outcome="x", cv="y", cv_status="ready")
        self.c.undo_completion(aid)
        self.assertEqual(len(self.c.read_achievements()), 0)
        tasks = self.c.load_json("tasks.json", {})
        self.assertIn(self.tid, tasks)
        self.assertEqual(tasks[self.tid]["status"], "进行中")
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_cockpit.CompletionTest -v`
Expected: FAIL（`AttributeError: ... 'complete_task'`）

- [ ] **Step 3: 实现（追加到 cockpit.py）**

```python
def read_achievements():
    p = data_dir() / "achievements.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

def _write_achievements(items):
    p = data_dir() / "achievements.jsonl"
    p.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")

def complete_task(tid, outcome="", reflection="", cv="", cv_status="ready"):
    tasks = load_json("tasks.json", {})
    task = tasks.pop(tid)
    save_json("tasks.json", tasks)
    projects = load_json("projects.json", {})
    pname = projects.get(task["project"], {}).get("name", task["project"])
    aid = _new_id("done")
    items = read_achievements()
    items.append({"id": aid, "date": _today(), "projectId": task["project"],
                  "project": pname, "title": task["title"], "outcome": outcome,
                  "reflection": reflection, "cv": cv, "cvStatus": cv_status,
                  "_task": task})
    _write_achievements(items)
    return aid

def update_achievement_cv(aid, cv=None, cv_status=None):
    items = read_achievements()
    for it in items:
        if it["id"] == aid:
            if cv is not None: it["cv"] = cv
            if cv_status is not None: it["cvStatus"] = cv_status
    _write_achievements(items)

def undo_completion(aid):
    items = read_achievements()
    target = next(it for it in items if it["id"] == aid)
    items = [it for it in items if it["id"] != aid]
    _write_achievements(items)
    tasks = load_json("tasks.json", {})
    task = target["_task"]; task["status"] = "进行中"; task["draft"] = False
    tasks[aid.replace("done", "task")] = task
    save_json("tasks.json", tasks)
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_cockpit -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add cockpit.py tests/test_cockpit.py && git commit -m "feat: complete task into achievements, update CV, undo completion"
```

---

### Task 4: 聚焦计算与看板数据快照

**Files:**
- Modify: `task-cockpit/cockpit.py`
- Test: `task-cockpit/tests/test_cockpit.py`

`build_snapshot()` 产出看板所需的全部数据：聚焦清单（跨项目，按优先级 → 截止日排序，上限 5）、按项目分组的任务、今日已完成、累计计数。聚焦排序规则：优先级 高>中>低；同级按截止日升序（无截止日排最后）；被阻塞的任务标 `flagged=True` 但仍参与（供看板提示"等待中"）。

- [ ] **Step 1: 追加失败测试**

```python
class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["TASK_COCKPIT_DIR"] = self.tmp
        import cockpit; importlib.reload(cockpit); self.c = cockpit

    def test_focus_orders_by_priority_then_due(self):
        p = self.c.add_project("P")
        self.c.add_task(p, "low", priority="低", due="2026-06-12")
        self.c.add_task(p, "high-late", priority="高", due="2026-06-20")
        self.c.add_task(p, "high-soon", priority="高", due="2026-06-12")
        self.c.confirm_drafts()
        titles = [f["title"] for f in self.c.build_snapshot()["focus"]]
        self.assertEqual(titles[:3], ["high-soon", "high-late", "low"])

    def test_focus_capped_at_five(self):
        p = self.c.add_project("P")
        for i in range(8):
            self.c.add_task(p, f"t{i}", priority="高")
        self.c.confirm_drafts()
        self.assertEqual(len(self.c.build_snapshot()["focus"]), 5)

    def test_snapshot_groups_by_project_and_counts(self):
        p = self.c.add_project("P")
        tid = self.c.add_task(p, "t"); self.c.confirm_drafts()
        self.c.complete_task(tid, outcome="x", cv="y", cv_status="ready")
        self.c.add_task(p, "t2", priority="低")
        snap = self.c.build_snapshot()
        self.assertEqual(snap["projects"][0]["name"], "P")
        self.assertEqual(len(snap["doneToday"]), 1)
        self.assertEqual(snap["counts"]["achievementsReady"], 1)

    def test_counts_track_pending(self):
        p = self.c.add_project("P")
        tid = self.c.add_task(p, "t"); self.c.confirm_drafts()
        self.c.complete_task(tid, outcome="x", cv="", cv_status="pending")
        self.assertEqual(self.c.build_snapshot()["counts"]["achievementsPending"], 1)
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_cockpit.SnapshotTest -v`
Expected: FAIL（`AttributeError: ... 'build_snapshot'`）

- [ ] **Step 3: 实现（追加到 cockpit.py）**

```python
_PRIORITY_RANK = {"高": 0, "中": 1, "低": 2}

def _focus_key(t):
    return (_PRIORITY_RANK.get(t.get("priority"), 1), t.get("due") or "9999-99-99")

def build_snapshot():
    projects = load_json("projects.json", {})
    tasks = load_json("tasks.json", {})
    enriched = [dict(id=tid, **t) for tid, t in tasks.items()]
    ordered = sorted(enriched, key=_focus_key)
    focus = [{**t, "flagged": bool(t.get("blocked"))} for t in ordered[:5]]
    grouped = []
    for pid, p in projects.items():
        if p.get("archived"): continue
        pts = [t for t in enriched if t["project"] == pid]
        grouped.append({"id": pid, "name": p["name"], "tasks": pts})
    ach = read_achievements()
    done_today = [a for a in ach if a["date"] == _today()]
    counts = {"achievementsReady": sum(1 for a in ach if a["cvStatus"] == "ready"),
              "achievementsPending": sum(1 for a in ach if a["cvStatus"] == "pending")}
    return {"focus": focus, "projects": grouped, "doneToday": done_today, "counts": counts}
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_cockpit -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add cockpit.py tests/test_cockpit.py && git commit -m "feat: focus ranking and dashboard snapshot"
```

---

### Task 5: CLI 调度层

**Files:**
- Modify: `task-cockpit/cockpit.py`
- Test: `task-cockpit/tests/test_cockpit.py`

agent 通过 `python3 cockpit.py <子命令> --json '<参数>'` 操作数据。每个子命令读取 `--json` 参数（一个 JSON 串），执行后把结果以 JSON 打印到 stdout。这样 agent 用一种统一、可解析的方式调用，避免直接手改文件。

子命令：`add-project`、`add-task`、`update-task`、`confirm-drafts`、`complete-task`、`update-cv`、`undo`、`delete-task`、`snapshot`、`achievements`（按可选 project/since 过滤，供 CV 重组）。

- [ ] **Step 1: 追加失败测试**

```python
import subprocess, sys
class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = {**os.environ, "TASK_COCKPIT_DIR": self.tmp}
        self.script = str(Path(__file__).resolve().parent.parent / "cockpit.py")

    def run_cmd(self, *args):
        out = subprocess.check_output([sys.executable, self.script, *args], env=self.env)
        return json.loads(out)

    def test_cli_add_project_and_snapshot(self):
        res = self.run_cmd("add-project", "--json", json.dumps({"name": "P"}))
        self.assertTrue(res["id"].startswith("proj_"))
        snap = self.run_cmd("snapshot")
        self.assertEqual(snap["projects"][0]["name"], "P")

    def test_cli_add_task_flow(self):
        pid = self.run_cmd("add-project", "--json", json.dumps({"name": "P"}))["id"]
        tid = self.run_cmd("add-task", "--json",
                           json.dumps({"project": pid, "title": "T", "priority": "高"}))["id"]
        self.run_cmd("confirm-drafts")
        snap = self.run_cmd("snapshot")
        self.assertEqual(snap["focus"][0]["title"], "T")
        self.assertFalse(snap["focus"][0]["draft"])
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_cockpit.CliTest -v`
Expected: FAIL（CLI 无输出 / 非 0 退出）

- [ ] **Step 3: 实现 CLI（追加到 cockpit.py 末尾）**

```python
import argparse, sys

def _cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--json", default="{}")
    args = parser.parse_args()
    a = json.loads(args.json)
    cmd = args.command
    if cmd == "add-project":
        out = {"id": add_project(a["name"])}
    elif cmd == "add-task":
        out = {"id": add_task(a["project"], a["title"], a.get("priority", "中"),
                              a.get("due", ""), a.get("nextAction", ""), a.get("blocked", False))}
    elif cmd == "update-task":
        update_task(a.pop("id"), **a); out = {"ok": True}
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
        if a.get("project"): items = [i for i in items if i["project"] == a["project"]]
        if a.get("since"): items = [i for i in items if i["date"] >= a["since"]]
        out = {"items": items}
    else:
        out = {"error": f"unknown command {cmd}"}
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    _cli()
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_cockpit -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add cockpit.py tests/test_cockpit.py && git commit -m "feat: CLI dispatch for all data operations"
```

---

### Task 6: 本地看板服务

**Files:**
- Create: `task-cockpit/server.py`
- Test: `task-cockpit/tests/test_server.py`

固定端口 7842，绑定 127.0.0.1，无闲置超时。路由：`GET /` → `dashboard.html`；`GET /api/data` → `cockpit.build_snapshot()` 的 JSON；`GET /api/health` → `{"ok": true}`。服务进程独立运行，靠固定端口实现"被关后下次自动拉起、URL 不变"。

- [ ] **Step 1: 写失败测试**

```python
import os, json, tempfile, unittest, threading, urllib.request, importlib
from pathlib import Path

class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["TASK_COCKPIT_DIR"] = self.tmp
        import cockpit; importlib.reload(cockpit); self.c = cockpit
        import server; importlib.reload(server); self.server_mod = server
        self.httpd = server.make_server(0)  # port 0 = 任意空闲端口
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, r.read().decode()

    def test_health(self):
        status, body = self._get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_api_data_returns_snapshot(self):
        pid = self.c.add_project("P"); self.c.add_task(pid, "T"); self.c.confirm_drafts()
        status, body = self._get("/api/data")
        self.assertEqual(json.loads(body)["projects"][0]["name"], "P")

    def test_root_serves_dashboard_html(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("<html", body.lower())
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_server -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'server'`）

- [ ] **Step 3: 实现 server.py**

```python
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import cockpit

PORT = 7842
HTML = Path(__file__).resolve().parent / "dashboard.html"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
    def do_GET(self):
        if self.path == "/api/health":
            self._send(200, json.dumps({"ok": True}), "application/json")
        elif self.path == "/api/data":
            self._send(200, json.dumps(cockpit.build_snapshot(), ensure_ascii=False),
                       "application/json; charset=utf-8")
        elif self.path == "/" or self.path.startswith("/?"):
            html = HTML.read_text(encoding="utf-8") if HTML.exists() else "<html><body>dashboard.html missing</body></html>"
            self._send(200, html, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

def make_server(port=PORT):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)

if __name__ == "__main__":
    srv = make_server()
    print(json.dumps({"url": f"http://127.0.0.1:{PORT}", "port": PORT}))
    srv.serve_forever()
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_server -v`
Expected: PASS（3 测试）

- [ ] **Step 5: 提交**

```bash
git add server.py tests/test_server.py && git commit -m "feat: localhost dashboard server with data api"
```

---

### Task 7: 看板 HTML（C 布局）

**Files:**
- Create: `task-cockpit/dashboard.html`

纯前端，每 2 秒 `fetch('/api/data')` 并重渲染。无单测（属客户端展示）；以浏览器冒烟验证。布局：顶部"今日聚焦"红框（上限 5）、下方按项目分块、草稿黄色虚线高亮、"今天已完成 ✅"可折叠区、顶部累计成就计数。

- [ ] **Step 1: 写 dashboard.html（骨架 + 样式 + 轮询）**

先写到 `<body>` 的容器与脚本框架（渲染函数下一步填充）：

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Task Cockpit</title>
<style>
  body{font-family:-apple-system,system-ui,sans-serif;background:#f5f6f8;margin:0;padding:20px;color:#222}
  .topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
  .counts{font-size:13px;color:#666}
  .focus{background:#fff;border:2px solid #e74c3c;border-radius:10px;padding:14px 16px;margin-bottom:16px}
  .focus h2{font-size:13px;color:#e74c3c;margin:0 0 10px}
  .focus-grid{display:flex;gap:10px;flex-wrap:wrap}
  .focus-card{flex:1;min-width:220px;background:#fff8f8;border:1px solid #f3d0d0;border-radius:8px;padding:10px}
  .cols{display:flex;gap:12px;flex-wrap:wrap}
  .col{flex:1;min-width:260px;background:#fff;border-radius:10px;padding:14px}
  .col h3{font-size:14px;border-bottom:1px solid #eee;padding-bottom:8px;margin:0 0 8px}
  .task{padding:8px;border-radius:6px;font-size:13px;margin-bottom:6px}
  .task.draft{background:#fffbe6;border:1px dashed #f0c000}
  .meta{font-size:11px;color:#999;margin-top:2px}
  .badge{background:#f0c000;color:#fff;font-size:10px;padding:1px 6px;border-radius:8px;margin-left:4px}
  details.done{margin-top:16px;background:#fff;border-radius:10px;padding:12px}
  summary{cursor:pointer;font-size:13px;font-weight:600}
  .muted{color:#bbb;font-size:11px;text-align:center;margin-top:14px}
</style>
</head>
<body>
<div class="topbar">
  <strong>Task Cockpit</strong>
  <span class="counts" id="counts"></span>
</div>
<div id="focus"></div>
<div class="cols" id="cols"></div>
<div id="done"></div>
<div class="muted">○ 未开始　◐ 进行中　|　每 2 秒自动刷新</div>
<script>
const ICON = {"未开始":"○","进行中":"◐"};
function esc(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
async function tick(){
  try{ const d = await (await fetch('/api/data')).json(); render(d); }
  catch(e){ /* 服务可能重启中，下次再试 */ }
}
setInterval(tick, 2000); tick();
</script>
</body>
</html>
```

- [ ] **Step 2: 填充 render() 函数（在 `tick` 定义之前插入）**

```javascript
function pmeta(t){
  const bits=[];
  if(t.priority) bits.push({"高":"🔴高","中":"🟡中","低":"⚪低"}[t.priority]||t.priority);
  if(t.due) bits.push("⏰"+t.due);
  if(t.nextAction) bits.push("▶ "+esc(t.nextAction));
  if(t.blocked) bits.push('<span style="color:#e67e22">⏳等待中</span>');
  return bits.join(" · ");
}
function render(d){
  document.getElementById('counts').innerHTML =
    `本期已沉淀 ${d.counts.achievementsReady} 条成就 · ${d.counts.achievementsPending} 条待补充`;
  document.getElementById('focus').innerHTML = d.focus.length ? `
    <div class="focus"><h2>🔥 今日聚焦 · agent 按优先级+截止日算出</h2>
    <div class="focus-grid">${d.focus.map(t=>`
      <div class="focus-card"><div><b>${esc(t.title)}</b></div>
      <div class="meta">${pmeta(t)}</div></div>`).join("")}</div></div>` : "";
  document.getElementById('cols').innerHTML = d.projects.map(p=>`
    <div class="col"><h3>📁 ${esc(p.name)} <span style="color:#aaa;font-weight:400">${p.tasks.length} 任务</span></h3>
    ${p.tasks.map(t=>`<div class="task ${t.draft?'draft':''}">
      ${ICON[t.status]||"○"} ${esc(t.title)}
      ${t.draft?'<span class="badge">草稿待确认</span>':''}
      <div class="meta">${pmeta(t)}</div></div>`).join("") || '<div class="meta">暂无任务</div>'}
    </div>`).join("");
  document.getElementById('done').innerHTML = d.doneToday.length ? `
    <details class="done"><summary>✅ 今天已完成（${d.doneToday.length}）</summary>
    ${d.doneToday.map(a=>`<div class="task">● ${esc(a.title)}
      <div class="meta">${esc(a.cv)||esc(a.outcome)} ${a.cvStatus==='pending'?'<span class="badge">CV待补充</span>':''}</div>
    </div>`).join("")}</details>` : "";
}
```

- [ ] **Step 3: 浏览器冒烟验证**

```bash
cd ~/Documents/claudecodeWorkspace/task-cockpit
TASK_COCKPIT_DIR=/tmp/tc-smoke python3 cockpit.py add-project --json '{"name":"演示项目"}'
# 用上一步返回的 id 加任务（替换 PROJ_ID）
TASK_COCKPIT_DIR=/tmp/tc-smoke python3 cockpit.py add-task --json '{"project":"PROJ_ID","title":"试一下","priority":"高","due":"2026-06-12"}'
TASK_COCKPIT_DIR=/tmp/tc-smoke python3 server.py
```
浏览器开 `http://127.0.0.1:7842`，确认看到：今日聚焦含"试一下"、项目块"演示项目"、草稿黄色高亮。Ctrl-C 停服务。
Expected: 页面正确渲染，2 秒自动刷新生效。

- [ ] **Step 4: 提交**

```bash
git add dashboard.html && git commit -m "feat: read-only dashboard with focus, projects, drafts, done-today"
```

---

### Task 8: SKILL.md 工作流说明

**Files:**
- Create: `task-cockpit/SKILL.md`

让 agent 识别意图、调用 CLI、管理服务生命周期。这是把数据层"教"给 agent 的地方。

- [ ] **Step 1: 写 SKILL.md 头部与服务管理**

```markdown
---
name: task-cockpit
description: 个人任务驾驶舱。用户用自然语言倒事，你拆成任务入库、维护只读看板回答"该先干啥"，并在每个任务完成时即时沉淀可用的成就陈述。当用户提到要管理任务、规划待办、说某事做完了、问现在该干什么、或要总结成果/述职/周报时使用。
---

# Task Cockpit

你是用户的个人任务管理后台。所有数据操作都通过调用 `cockpit.py` 的 CLI 完成，**不要手改 JSON 文件**。

## 启动看板服务

每次会话首次涉及任务操作时，先确保看板服务在运行：

\`\`\`bash
curl -s http://127.0.0.1:7842/api/health || (cd <skill 目录> && nohup python3 server.py >/dev/null 2>&1 &)
\`\`\`

告诉用户看板地址：http://127.0.0.1:7842 。服务无闲置超时，被关后下次按此法自动拉起，端口固定不变。

## 调用数据层

格式：`python3 <skill目录>/cockpit.py <命令> --json '<JSON参数>'`，输出为 JSON。
\`\`\`
add-project   {"name": "..."}                          → {"id": "proj_..."}
add-task      {"project","title","priority","due","nextAction","blocked"} → {"id":"task_..."}
update-task   {"id", 及任意要改字段}                       → {"ok":true}
confirm-drafts {}                                        → {"ok":true}
complete-task {"id","outcome","reflection","cv","cv_status"} → {"id":"done_..."}
update-cv     {"id","cv","cv_status"}                    → {"ok":true}
undo          {"id":"done_..."}                          → {"ok":true}
delete-task   {"id"}                                     → {"ok":true}
snapshot      {}                                         → 看板数据
achievements  {"project"?, "since"?}                     → {"items":[...]}
\`\`\`
```

- [ ] **Step 2: 追加三条工作流说明**

```markdown
## 工作流

### ① 倒事 → 拆解 → 确认
1. 理解用户描述，识别项目（不存在则 add-project）与任务。
2. 用 add-task 写入（默认 draft=true，会在看板高亮）。priority 先按你的判断给建议值。
3. 在终端复述拆解结果，请用户调整。用户要改就用 update-task / delete-task。
4. 用户说"确认"后调 confirm-drafts，草稿高亮消失。

### ② 推进 → 完成（沉淀成就）
1. 用户说某任务做完了，找到对应 task id。
2. 先替用户拟一句 outcome，问是否修改、是否记 reflection（复盘可选，不强制）。
3. 基于 outcome+reflection+任务上下文生成成就陈述 cv：
   - 素材充分 → complete-task 带 cv_status="ready"，告知"✨ 已沉淀进成就库"。
   - 素材太单薄（缺具体成果/影响）→ complete-task 带 cv_status="pending"，并追问可补充的影响/量化。
4. pending 的条目，在用户后续补充后用 update-cv 转 ready。

### ③ 问局势 → 主动建议
用户问"该干啥"，调 snapshot，依据 focus 列表给建议：最该动的、被阻塞可暂搁的、有空可推进的。

## 成果 / CV 总结
用户要述职/周报/复盘材料时，调 achievements（按 project/since 过滤），筛 cvStatus=ready 的条目，按用途重组：
- 述职/答辩：成果导向，STAR 式，强调影响与推动力。
- 周报/日报：平铺直叙，按项目分组，简洁。
- 复盘/成长：调取 reflection，讲教训与改进。

**底线：只用 achievements 里真实记录的内容，绝不编造未发生的事。** 素材不足就提示用户补充。输出为 markdown 供取用，默认不入库；用户要存档可写入 ~/.task-cockpit/cv-exports/。
```

- [ ] **Step 3: 提交**

```bash
git add SKILL.md && git commit -m "docs: SKILL.md workflow for intent recognition and CLI usage"
```

---

### Task 9: 安装、全量测试与冒烟

**Files:**
- Create: `task-cockpit/README.md`

- [ ] **Step 1: 跑全部单测**

Run: `cd ~/Documents/claudecodeWorkspace/task-cockpit && python3 -m unittest discover tests -v`
Expected: 全部 PASS。

- [ ] **Step 2: 写 README（安装说明）**

```markdown
# Task Cockpit

个人任务驾驶舱（Claude Code skill）。详见设计文档 docs/superpowers/specs/2026-06-11-task-cockpit-design.md。

## 安装
将本目录软链接为 skill：
\`\`\`bash
ln -s "$(pwd)" ~/.claude/skills/task-cockpit
\`\`\`
数据存于 ~/.task-cockpit/（首次使用自动创建）。需要 Python 3。

## 团队分发
日后套 plugin、自建 git marketplace 即可分享给同事，各自数据独立。
```

- [ ] **Step 3: 安装为 skill 并端到端冒烟**

```bash
ln -s ~/Documents/claudecodeWorkspace/task-cockpit ~/.claude/skills/task-cockpit
```
在新的 Claude Code 会话里说"我有个新项目叫测试项目，要做 A 和 B 两件事"，确认：agent 调用 add-project/add-task、看板出现两条草稿高亮、确认后高亮消失、说"A 做完了"能沉淀成就。
Expected: 全流程跑通。

- [ ] **Step 4: 提交**

```bash
git add README.md && git commit -m "docs: README with install and distribution notes"
```

---

## 自审

- **规格覆盖**：数据层三文件(Task1-4)✓；倒事/拆解/确认(Task2,5,8)✓；完成沉淀+pending+撤销(Task3,8)✓；C布局看板含聚焦上限5/草稿高亮/已完成区/计数(Task4,7)✓；CV三模板+真实性底线(Task8)✓；固定端口/127.0.0.1/无闲置超时/自动拉起(Task6,8)✓；不写死个人路径——用 `Path.home()` 与 `TASK_COCKPIT_DIR`(Task1)✓；plugin分发路径(README,Task9)✓。
- **占位符**：无 TBD/TODO；每步含完整代码或命令。
- **类型一致**：`build_snapshot` 返回的 `focus/projects/doneToday/counts` 在 dashboard.html 中字段名一致；CLI 命令名与 SKILL.md 表格一致；`cv_status`(CLI/函数参数) 对应数据中的 `cvStatus`(已在 complete_task 内转换)。








