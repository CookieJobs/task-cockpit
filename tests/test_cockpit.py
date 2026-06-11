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
        self.assertTrue(t["draft"]); self.assertEqual(t["status"], "未开始"); self.assertEqual(t["priority"], "高")

    def test_update_task_changes_fields(self):
        pid = self.c.add_project("P"); tid = self.c.add_task(pid, "T")
        self.c.update_task(tid, due="2026-06-12", nextAction="等设计", blocked=True)
        t = self.c.load_json("tasks.json", {})[tid]
        self.assertEqual(t["due"], "2026-06-12"); self.assertTrue(t["blocked"])

    def test_confirm_drafts_clears_flag(self):
        pid = self.c.add_project("P"); tid = self.c.add_task(pid, "T")
        self.c.confirm_drafts()
        self.assertFalse(self.c.load_json("tasks.json", {})[tid]["draft"])

    def test_delete_task_removes_it(self):
        pid = self.c.add_project("P"); tid = self.c.add_task(pid, "T")
        self.c.delete_task(tid)
        self.assertNotIn(tid, self.c.load_json("tasks.json", {}))


class CompletionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["TASK_COCKPIT_DIR"] = self.tmp
        import cockpit; importlib.reload(cockpit); self.c = cockpit
        self.pid = self.c.add_project("App 改版")
        self.tid = self.c.add_task(self.pid, "登录页改稿")
        self.c.confirm_drafts()

    def test_complete_moves_task_to_achievements(self):
        aid = self.c.complete_task(self.tid, outcome="提测完成", reflection="早点对设计", cv="主导登录页改版", cv_status="ready")
        self.assertNotIn(self.tid, self.c.load_json("tasks.json", {}))
        items = self.c.read_achievements()
        self.assertEqual(len(items), 1); self.assertEqual(items[0]["id"], aid)
        self.assertEqual(items[0]["project"], "App 改版"); self.assertEqual(items[0]["cvStatus"], "ready")
        self.assertEqual(items[0]["date"], self.c._today())

    def test_pending_cv_status_preserved(self):
        self.c.complete_task(self.tid, outcome="做完了", cv="", cv_status="pending")
        self.assertEqual(self.c.read_achievements()[0]["cvStatus"], "pending")

    def test_update_achievement_cv_promotes_to_ready(self):
        aid = self.c.complete_task(self.tid, outcome="做完了", cv="", cv_status="pending")
        self.c.update_achievement_cv(aid, cv="影响 10w 用户", cv_status="ready")
        items = self.c.read_achievements()
        self.assertEqual(items[0]["cv"], "影响 10w 用户"); self.assertEqual(items[0]["cvStatus"], "ready")

    def test_undo_completion_restores_task(self):
        aid = self.c.complete_task(self.tid, outcome="x", cv="y", cv_status="ready")
        self.c.undo_completion(aid)
        self.assertEqual(len(self.c.read_achievements()), 0)
        tasks = self.c.load_json("tasks.json", {})
        self.assertIn(self.tid, tasks); self.assertEqual(tasks[self.tid]["status"], "进行中")


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
        for i in range(8): self.c.add_task(p, f"t{i}", priority="高")
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
