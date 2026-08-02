from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "buzz_buildroom_controller.py"


def load_module():
    spec = importlib.util.spec_from_file_location("buzz_buildroom_controller", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load controller module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BuzzBuildroomControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.json"
        self.state_path = self.root / "state.json"
        self.log_path = self.root / "calls.jsonl"
        self.hermes = self.root / "hermes"
        self.buzz = self.root / "buzz"
        self._write_fake_cli(self.hermes, "hermes")
        self._write_fake_cli(self.buzz, "buzz")
        self._write_config()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_fake_cli(self, path: Path, kind: str) -> None:
        script = r'''#!/usr/bin/env python3
import hashlib, json, os, sys
from pathlib import Path
log = Path(os.environ["FAKE_CALL_LOG"])
kind = Path(sys.argv[0]).name
stdin = sys.stdin.read() if "--content" in sys.argv and "-" in sys.argv else ""
with log.open("a", encoding="utf-8") as f:
    f.write(json.dumps({"kind": kind, "argv": sys.argv[1:], "stdin": stdin}) + "\n")
if kind == "hermes":
    if "list" in sys.argv:
        status = sys.argv[sys.argv.index("--status") + 1]
        tasks = json.loads(os.environ.get("FAKE_TASKS", "[]"))
        print(json.dumps([x for x in tasks if x["status"] == status]))
    elif "show" in sys.argv:
        task_id = sys.argv[sys.argv.index("show") + 1]
        tasks = json.loads(os.environ.get("FAKE_TASKS", "[]"))
        print(json.dumps({"task": next(x for x in tasks if x["id"] == task_id), "latest_summary": "not exported"}))
    else:
        print("{}")
else:
    if sys.argv[1:3] == ["channels", "search"]:
        existing = os.environ.get("FAKE_EXISTING_CHANNEL") == "1"
        previous = []
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                previous.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        created = any(row.get("argv", [])[:2] == ["channels", "create"] for row in previous)
        kickoff_sent = any(row.get("argv", [])[:2] == ["messages", "send"] for row in previous)
        query = sys.argv[sys.argv.index("--query") + 1]
        if os.environ.get("FAKE_CLOSURE_VISIBILITY_PUBLIC") == "1" and kickoff_sent:
            visibility = "public"
        else:
            visibility = None if os.environ.get("FAKE_VISIBILITY_MISSING") == "1" else "private"
        channel_id = "wrong-channel" if os.environ.get("FAKE_BAD_READBACK") == "1" and created else ("chan-recovered" if existing else "chan-1")
        binding = hashlib.sha256(b"t_feature1").hexdigest()[:24]
        about = os.environ.get("FAKE_CHANNEL_ABOUT", f"Ephemeral collaboration room for Hermes Kanban task t_feature1; binding={binding}")
        terminal = any(task.get("status") == "done" for task in json.loads(os.environ.get("FAKE_TASKS", "[]")))
        rows = [{"channel_id":channel_id,"name":query,"visibility":visibility,"archived":False,"about":about}] if existing or created or terminal else []
        print(json.dumps(rows))
    elif sys.argv[1:3] == ["channels", "create"]:
        print(json.dumps({"status":"ok","channel_id":"chan-1","members_added":[],"member_failures":[]}))
    elif sys.argv[1:3] == ["messages", "send"]:
        print(json.dumps({"accepted": True, "event_id":"evt-kickoff"}))
    elif sys.argv[1:3] == ["channels", "get"]:
        channel_id = sys.argv[sys.argv.index("--channel") + 1]
        if os.environ.get("FAKE_BAD_READBACK") == "1":
            channel_id = "wrong-channel"
        print(json.dumps({"channel_id":channel_id,"name":os.environ.get("FAKE_CHANNEL_NAME", "build-feature-test-feature-t-feature1")}))
    elif sys.argv[1:3] == ["channels", "add-member"]:
        print(json.dumps({"accepted": True, "event_id":"evt-member"}))
    elif sys.argv[1:3] == ["channels", "archive"]:
        if os.environ.get("FAKE_ARCHIVE_FAIL") == "1":
            print(json.dumps({"error":"network","message":"archive unavailable"}), file=sys.stderr)
            raise SystemExit(2)
        print(json.dumps({"accepted": True, "event_id":"evt-archive"}))
    elif sys.argv[1:3] == ["messages", "search"]:
        query = sys.argv[sys.argv.index("--query") + 1]
        if os.environ.get("FAKE_EXISTING_MESSAGE") == "1":
            channel = "chan-recovered" if os.environ.get("FAKE_EXISTING_CHANNEL") == "1" else "chan-1"
            print(json.dumps([{"id":"m-existing","pubkey":"c" * 64,"created_at":100,"content":query,"tags":[["h",channel]]}]))
        else:
            print(json.dumps([{"id":"m1","pubkey":"c" * 64,"created_at":100,"content":"Parse retry decision","tags":[["h","chan-1"]]}]))
    else:
        print("{}")
'''
        path.write_text(script, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _write_config(self, **overrides) -> None:
        config = {
            "schema": "kurultai.buzz-buildrooms.v1",
            "profile": "kublai",
            "buzz_cli": str(self.buzz),
            "hermes_cli": str(self.hermes),
            "relay_url": "http://127.0.0.1:3000",
            "state_path": str(self.state_path),
            "secret_env_file": str(self.root / ".env"),
            "max_creations_per_tick": 1,
            "eligible_statuses": ["ready", "running"],
            "automatic_title_patterns": ["^(feat|feature|bug|fix|incident|security)[: -]"],
            "explicit_opt_in_markers": ["[buzz-buildroom]", "Buzz buildroom: true"],
            "explicit_opt_out_markers": ["Buzz buildroom: false"],
            "templates": {
                "feature": {"ttl_seconds": 604800, "channel_prefix": "build"},
                "bug": {"ttl_seconds": 259200, "channel_prefix": "bug"},
                "incident": {"ttl_seconds": 0, "channel_prefix": "incident"},
            },
            "members": {
                "kublai": {"pubkey": "a" * 64, "role": "bot"},
                "reviewer": {"pubkey": "b" * 64, "role": "bot"},
            },
            "default_reviewer": "reviewer",
            "archive_on_done": True,
        }
        config.update(overrides)
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

    def _env(self, tasks: list[dict]) -> dict[str, str]:
        env = os.environ.copy()
        env.update({
            "FAKE_CALL_LOG": str(self.log_path),
            "FAKE_TASKS": json.dumps(tasks),
            "BUZZ_PRIVATE_KEY": "1" * 64,
        })
        return env

    @staticmethod
    def _task(**overrides) -> dict:
        task = {
            "id": "t_feature1",
            "title": "Feature: Test feature",
            "body": "Stop condition: deterministic smoke passes\nBoundaries: no customer data\nDeliverables: tests, patch, verification",
            "assignee": "kublai",
            "status": "running",
            "priority": 10,
            "project_id": "proj-1",
            "created_at": 200,
            "completed_at": None,
            "verdict": None,
        }
        task.update(overrides)
        return task

    def _run(self, *args: str, tasks: list[dict] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), *args],
            cwd=ROOT,
            env=self._env(tasks or []),
            text=True,
            capture_output=True,
            check=False,
        )

    def _calls(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]

    def test_config_validation_rejects_non_loopback_http_relay(self) -> None:
        self._write_config(relay_url="http://relay.example.com")
        result = self._run("validate-config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-loopback relay must use https", result.stderr)

    def test_config_requires_exactly_one_creation_per_tick(self) -> None:
        self._write_config(max_creations_per_tick=2)
        result = self._run("validate-config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("max_creations_per_tick must equal 1", result.stderr)

    def test_title_or_marker_selects_buildroom_and_opt_out_wins(self) -> None:
        cfg = self.module.load_config(self.config_path)
        self.assertEqual(self.module.classify_task(self._task(), cfg), "feature")
        marked = self._task(title="Investigate latency", body="[buzz-buildroom]")
        self.assertEqual(self.module.classify_task(marked, cfg), "feature")
        opted_out = self._task(body="[buzz-buildroom]\nBuzz buildroom: false")
        self.assertIsNone(self.module.classify_task(opted_out, cfg))

    def test_task_binding_uses_complete_task_id(self) -> None:
        first = "t_same-prefix-000000000000000000000000-a"
        second = "t_same-prefix-000000000000000000000000-b"
        self.assertNotEqual(self.module.task_binding(first), self.module.task_binding(second))
        self.assertEqual(len(self.module.task_binding(first)), 24)

    def test_kickoff_is_allowlisted_and_does_not_copy_private_body(self) -> None:
        private_path = "/".join(("", "Users", "kublai", "brain", "hard-private", "x"))
        secret_line = "API_" + "TOKEN=" + "should-never-appear"
        task = self._task(body=(
            f"Internal prose {private_path}\n"
            "Stop condition: 20 canaries pass\n"
            "Boundaries: no customer data\n"
            "Deliverables: patch and receipt\n"
            f"{secret_line}"
        ))
        text = self.module.render_kickoff(task, "reviewer")
        self.assertIn("20 canaries pass", text)
        self.assertIn("no customer data", text)
        self.assertNotIn("hard-private", text)
        self.assertNotIn("API_TOKEN", text)
        self.assertNotIn("should-never-appear", text)

    def test_tick_creates_private_ephemeral_room_adds_roster_and_posts_kickoff(self) -> None:
        result = self._run("tick", tasks=[self._task()])
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._calls()
        create = next(x for x in calls if x["kind"] == "buzz" and x["argv"][:2] == ["channels", "create"])
        self.assertIn("private", create["argv"])
        self.assertIn("604800", create["argv"])
        member_calls = [x for x in calls if x["kind"] == "buzz" and x["argv"][:2] == ["channels", "add-member"]]
        self.assertEqual(len(member_calls), 2)
        send = next(x for x in calls if x["kind"] == "buzz" and x["argv"][:2] == ["messages", "send"])
        self.assertIn("**Canonical task:** `t_feature1`", send["stdin"])
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["tasks"]["t_feature1"]["phase"], "active")
        self.assertEqual(state["tasks"]["t_feature1"]["channel_id"], "chan-1")

    def test_tick_requires_channel_readback_before_active_phase(self) -> None:
        env = self._env([self._task()])
        env["FAKE_BAD_READBACK"] = "1"
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("channel readback mismatch", result.stderr)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["tasks"]["t_feature1"]["phase"], "channel_created")
        self.assertFalse(any(x["argv"][:2] == ["messages", "send"] for x in self._calls()))

    def test_tick_is_idempotent_and_never_duplicates_channel(self) -> None:
        task = self._task()
        first = self._run("tick", tasks=[task])
        second = self._run("tick", tasks=[task])
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        creates = [x for x in self._calls() if x["kind"] == "buzz" and x["argv"][:2] == ["channels", "create"]]
        self.assertEqual(len(creates), 1)

    def test_tick_recovers_exact_existing_channel_after_state_loss(self) -> None:
        env = self._env([self._task()])
        env["FAKE_EXISTING_CHANNEL"] = "1"
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._calls()
        self.assertFalse(any(x["argv"][:2] == ["channels", "create"] for x in calls))
        self.assertTrue(any(x["argv"][:2] == ["messages", "send"] for x in calls))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        record = state["tasks"]["t_feature1"]
        self.assertEqual(record["channel_id"], "chan-recovered")
        self.assertTrue(record["recovered_existing_channel"])

    def test_tick_rejects_recovered_channel_without_private_visibility_proof(self) -> None:
        env = self._env([self._task()])
        env["FAKE_EXISTING_CHANNEL"] = "1"
        env["FAKE_VISIBILITY_MISSING"] = "1"
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not an active private room", result.stderr)
        self.assertFalse(any(x["argv"][:2] == ["messages", "send"] for x in self._calls()))

    def test_tick_rejects_recovered_channel_with_wrong_task_binding(self) -> None:
        env = self._env([self._task()])
        env["FAKE_EXISTING_CHANNEL"] = "1"
        env["FAKE_CHANNEL_ABOUT"] = "wrong binding"
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("binding is invalid", result.stderr)
        self.assertFalse(any(x["argv"][:2] == ["messages", "send"] for x in self._calls()))

    def test_tick_recovers_existing_kickoff_message_after_state_loss(self) -> None:
        env = self._env([self._task()])
        env["FAKE_EXISTING_CHANNEL"] = "1"
        env["FAKE_EXISTING_MESSAGE"] = "1"
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._calls()
        self.assertFalse(any(x["argv"][:2] == ["messages", "send"] for x in calls))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        record = state["tasks"]["t_feature1"]
        self.assertEqual(record["phase"], "active")
        self.assertEqual(record["kickoff_event_id"], "m-existing")

    def test_tick_limits_channel_creations_per_run(self) -> None:
        tasks = [self._task(), self._task(id="t_feature2", title="Bug: second failure")]
        result = self._run("tick", tasks=tasks)
        self.assertEqual(result.returncode, 0, result.stderr)
        creates = [x for x in self._calls() if x["kind"] == "buzz" and x["argv"][:2] == ["channels", "create"]]
        self.assertEqual(len(creates), 1)

    def test_missing_credentials_fails_closed_without_buzz_write(self) -> None:
        env = self._env([self._task()])
        env.pop("BUZZ_PRIVATE_KEY")
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"reason": "buzz_credentials_unavailable"', result.stdout)
        self.assertFalse(any(x["kind"] == "buzz" for x in self._calls()))

    def test_live_controller_lock_prevents_overlapping_tick_writes(self) -> None:
        lock_path = self.state_path.with_name(self.state_path.name + ".lock")
        ready_path = self.root / "lock-ready"
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import fcntl,json,os,sys,time; "
                    "p=open(sys.argv[1],'w+'); fcntl.flock(p,fcntl.LOCK_EX); "
                    "p.write(json.dumps({'pid':os.getpid(),'created_at':1})); p.flush(); "
                    "open(sys.argv[2],'w').write('ready'); time.sleep(30)"
                ),
                str(lock_path),
                str(ready_path),
            ],
            text=True,
        )
        try:
            for _ in range(100):
                if ready_path.exists():
                    break
                time.sleep(0.01)
            self.assertTrue(ready_path.exists())
            result = self._run("tick", tasks=[self._task()])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"reason": "controller_busy"', result.stdout)
            self.assertFalse(any(x["kind"] == "buzz" for x in self._calls()))
        finally:
            holder.terminate()
            holder.wait(timeout=5)

    def test_terminal_task_posts_minimal_receipt_and_archives(self) -> None:
        running = self._task()
        self.assertEqual(self._run("tick", tasks=[running]).returncode, 0)
        done = self._task(status="done", completed_at=300, verdict="approve")
        self.log_path.unlink()
        result = self._run("tick", tasks=[done])
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._calls()
        send = next(x for x in calls if x["argv"][:2] == ["messages", "send"])
        self.assertIn("**Task status:** `done`", send["stdin"])
        self.assertNotIn(done["body"], send["stdin"])
        self.assertTrue(any(x["argv"][:2] == ["channels", "archive"] for x in calls))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["tasks"]["t_feature1"]["phase"], "closed")

    def test_closure_revalidates_private_bound_channel_before_posting(self) -> None:
        self.assertEqual(self._run("tick", tasks=[self._task()]).returncode, 0)
        done = self._task(status="done", completed_at=300, verdict="approve")
        env = self._env([done])
        env["FAKE_CLOSURE_VISIBILITY_PUBLIC"] = "1"
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("closure preflight", result.stderr)
        calls = self._calls()
        sends = [x for x in calls if x["argv"][:2] == ["messages", "send"]]
        self.assertEqual(len(sends), 1)  # kickoff only
        self.assertFalse(any(x["argv"][:2] == ["channels", "archive"] for x in calls))

    def test_closure_recomputes_binding_from_current_full_task_id(self) -> None:
        self.assertEqual(self._run("tick", tasks=[self._task()]).returncode, 0)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        record = state["tasks"]["t_feature1"]
        record["task_binding"] = "0" * 24
        record["channel_description"] = "wrong binding"
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        done = self._task(status="done", completed_at=300, verdict="approve")
        env = self._env([done])
        env["FAKE_CHANNEL_ABOUT"] = "wrong binding"
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("task binding mismatch", result.stderr)

    def test_parent_room_stays_active_until_review_child_approves(self) -> None:
        parent = self._task(children=["t_review"])
        review = self._task(
            id="t_review", title="Review implementation", assignee="reviewer", status="running",
            body="", children=[], created_at=201,
        )
        self.assertEqual(self._run("tick", tasks=[parent, review]).returncode, 0)
        parent_done = self._task(status="done", completed_at=300, children=["t_review"])
        self.log_path.unlink()
        held = self._run("tick", tasks=[parent_done, review])
        self.assertEqual(held.returncode, 0, held.stderr)
        self.assertFalse(any(x["argv"][:2] == ["channels", "archive"] for x in self._calls()))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["tasks"]["t_feature1"]["phase"], "active")

        review_done = dict(review, status="done", completed_at=301, verdict="approve")
        self.log_path.unlink()
        closed = self._run("tick", tasks=[parent_done, review_done])
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertTrue(any(x["argv"][:2] == ["channels", "archive"] for x in self._calls()))

    def _assert_rejected_child_holds_room(self, verdict: str) -> None:
        parent = self._task(children=["t_review"])
        review = self._task(
            id="t_review", title="Review implementation", assignee="reviewer", status="running",
            body="", children=[], created_at=201,
        )
        self.assertEqual(self._run("tick", tasks=[parent, review]).returncode, 0)
        parent_done = self._task(status="done", completed_at=300, children=["t_review"])
        review_done = dict(review, status="done", completed_at=301, verdict=verdict)
        self.log_path.unlink()
        result = self._run("tick", tasks=[parent_done, review_done])
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._calls()
        self.assertFalse(any(x["argv"][:2] == ["messages", "send"] for x in calls))
        self.assertFalse(any(x["argv"][:2] == ["channels", "archive"] for x in calls))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["tasks"]["t_feature1"]["phase"], "active")

    def test_request_changes_child_keeps_parent_room_active(self) -> None:
        self._assert_rejected_child_holds_room("request_changes")

    def test_reject_child_keeps_parent_room_active(self) -> None:
        self._assert_rejected_child_holds_room("reject")

    def test_archive_retry_does_not_duplicate_terminal_receipt(self) -> None:
        self.assertEqual(self._run("tick", tasks=[self._task()]).returncode, 0)
        done = self._task(status="done", completed_at=300, verdict="approve")
        env = self._env([done])
        env["FAKE_ARCHIVE_FAIL"] = "1"
        first = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(first.returncode, 0)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["tasks"]["t_feature1"]["phase"], "closure_posted")
        self.log_path.unlink()
        second = self._run("tick", tasks=[done])
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = self._calls()
        self.assertFalse(any(x["argv"][:2] == ["messages", "send"] for x in calls))
        self.assertTrue(any(x["argv"][:2] == ["channels", "archive"] for x in calls))

    def test_tick_recovers_existing_terminal_receipt_before_archiving(self) -> None:
        self.assertEqual(self._run("tick", tasks=[self._task()]).returncode, 0)
        self.log_path.unlink()
        done = self._task(status="done", completed_at=300, verdict="approve")
        env = self._env([done])
        env["FAKE_EXISTING_MESSAGE"] = "1"
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--config", str(self.config_path), "tick"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self._calls()
        self.assertFalse(any(x["argv"][:2] == ["messages", "send"] for x in calls))
        self.assertTrue(any(x["argv"][:2] == ["channels", "archive"] for x in calls))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        record = state["tasks"]["t_feature1"]
        self.assertEqual(record["closure_event_id"], "m-existing")
        self.assertEqual(record["phase"], "closed")

    def test_search_is_read_only_and_returns_normalized_results(self) -> None:
        result = self._run("search", "Parse retries")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["results"][0]["channel_id"], "chan-1")
        self.assertEqual(payload["results"][0]["content"], "Parse retry decision")
        writes = [x for x in self._calls() if x["kind"] == "buzz" and x["argv"][:2] != ["messages", "search"]]
        self.assertEqual(writes, [])

    def test_private_or_secret_shaped_task_is_blocked_before_channel_creation(self) -> None:
        secret = "gh" + "p_" + ("a" * 26)
        task = self._task(title="Feature: customer credential repair", body=f"Boundaries: use {secret}")
        result = self._run("tick", tasks=[task])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"reason": "privacy_gate"', result.stdout)
        self.assertFalse(any(x["kind"] == "buzz" for x in self._calls()))

    def test_tenant_scoped_task_is_never_exported_to_buzz(self) -> None:
        task = self._task(tenant="tenant-opaque")
        result = self._run("tick", tasks=[task])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"reason": "privacy_gate"', result.stdout)
        self.assertFalse(any(x["kind"] == "buzz" for x in self._calls()))

    def test_secret_shaped_task_identity_is_never_exported_to_buzz(self) -> None:
        secret = "gh" + "p_" + ("a" * 26)
        task = self._task(id=f"t_{secret}")
        result = self._run("tick", tasks=[task])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"reason": "privacy_gate"', result.stdout)
        self.assertFalse(any(x["kind"] == "buzz" for x in self._calls()))

    def test_config_rejects_unsafe_reviewer_identity(self) -> None:
        self._write_config(default_reviewer="../private/reviewer")
        result = self._run("validate-config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("default_reviewer is invalid", result.stderr)


if __name__ == "__main__":
    unittest.main()
