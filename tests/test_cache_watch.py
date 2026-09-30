"""Ledger behavior for the daily cache source watch (maintenance/cache-watch)."""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WATCH_DIR = ROOT / "maintenance" / "cache-watch"
MODULE = WATCH_DIR / "cache_watch.py"
REGISTRY = WATCH_DIR / "sources.json"
SPEC = importlib.util.spec_from_file_location("cache_watch", MODULE)
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)

T0 = "2026-09-30T07:00:00Z"  # 09:00 Europe/Kaliningrad


def at(days=0, hours=0):
    moment = datetime(2026, 9, 30, 7, tzinfo=timezone.utc) + timedelta(days=days, hours=hours)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def source(source_id, cadence="daily", dating="undated-doc"):
    return {
        "id": source_id,
        "group": "example",
        "priority": "p0",
        "type": "contract-doc",
        "url": f"https://example.com/{source_id}",
        "dating": dating,
        "cadence": cadence,
        "affects": ["audit-prompt-caching/references/openai.md"],
        "cache_relevance": "cache controls",
        "extraction": "cache section",
        "verified": {"on": "2026-09-30", "method": "curl", "result": "200"},
    }


TEST_REGISTRY = {
    "schema": 1,
    "sources": [
        source("a-doc"),
        source("a-rel", dating="dated-entries"),
        source("b-weekly", cadence="weekly"),
    ],
}

GATE = [
    "--before", "TTL 5m", "--after", "TTL 1h",
    "--evidence", "https://example.com/a-doc",
    "--behavior", "ttl-threshold",
    "--reference", "audit-prompt-caching/references/openai.md",
]
DATING = {item["id"]: item["dating"] for item in TEST_REGISTRY["sources"]}


class WatchCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.ledger = self.base / "state"
        self.registry = self.base / "sources.json"
        self.registry.write_text(json.dumps(TEST_REGISTRY))
        code, out = self.cli("init", "--test-clock")  # replay clock allowed only in test-clock ledgers
        self.assertEqual((code, out["status"]), (0, "initialized"))

    def raw(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = watch.main(argv)
        out = json.loads(buffer.getvalue())
        self.assertEqual(out["ok"], code == 0, out)
        return code, out

    def cli(self, command, *args, now=T0):
        argv = [command, "--ledger", str(self.ledger)]
        if now:
            argv += ["--now", now]
        return self.raw(argv + list(args))

    def start(self, now=T0, **options):
        args = ["--registry", str(self.registry)]
        for name, value in options.items():
            args += [f"--{name.replace('_', '-')}", str(value)]
        code, out = self.cli("start-run", *args, now=now)
        self.assertEqual(code, 0, out)
        return out

    def lease(self, run):
        return ["--run", run["run_id"], "--token", run["token"]]

    def record(self, run, source_id, status="checked", now=T0, snapshot=None, items=None):
        # A checked undated doc needs a snapshot; a checked dated channel needs --items.
        if status == "checked" and snapshot is None and items is None:
            if DATING[source_id] == "dated-entries":
                items = 0
            else:
                snapshot = "stable cache contract"
        args = self.lease(run) + ["--source", source_id, "--status", status]
        if items is not None:
            args += ["--items", str(items)]
        if snapshot is not None:
            path = self.base / f"{source_id}-{len(list(self.base.iterdir()))}.txt"
            path.write_text(snapshot)
            args += ["--snapshot", str(path)]
        return self.cli("record-source", *args, now=now)

    def finish(self, run, now=T0):
        return self.cli("finish-run", *self.lease(run), now=now)

    def complete_run(self, now=T0, sources=("a-doc", "a-rel", "b-weekly")):
        run = self.start(now)
        for source_id in sources:
            self.assertEqual(self.record(run, source_id, now=now)[0], 0)
        self.assertEqual(self.finish(run, now=now)[0], 0)

    def triage(self, run, key, outcome="implement", aliases=(), gate=GATE, now=T0, reason="r"):
        args = self.lease(run) + ["--key", key, "--source", "a-doc", "--outcome", outcome, "--reason", reason]
        for alias in aliases:
            args += ["--alias", alias]
        return self.cli("triage", *args, *gate, now=now)

    def reserve(self, run, key, now=T0, **limits):
        args = self.lease(run) + ["--key", key]
        for name, value in limits.items():
            args += [f"--{name.replace('_', '-')}", str(value)]
        return self.cli("reserve", *args, now=now)

    def dispatch(self, run, key, reservation, now=T0):
        return self.cli(
            "dispatch", *self.lease(run), "--key", key, "--reservation", reservation,
            "--thread-id", "thread-1", "--model", "gpt-6-sol", "--effort", "xhigh",
            "--reviewer", "claude-b opus-5.5 high", now=now,
        )

    def lifecycle(self, run, command, key, status, now=T0, *extra):
        return self.cli(command, *self.lease(run), "--key", key, "--status", status, *extra, now=now)


class WindowTest(WatchCase):
    def test_first_run_covers_previous_24h_plus_overlap(self):
        run = self.start()
        self.assertEqual(run["primary_window"], {"start": at(-1), "end": T0})
        self.assertEqual(run["sources"]["a-doc"]["window_start"], at(-1, -6))
        self.assertEqual(run["sources"]["a-doc"]["window_end"], T0)

    def test_failed_first_run_keeps_original_coverage_start_on_retries(self):
        run = self.start()
        self.record(run, "a-doc")
        self.record(run, "b-weekly")
        self.assertEqual(self.record(run, "a-rel", status="failed")[0], 0)
        code, out = self.finish(run)
        self.assertEqual((code, out["status"], out["failed"]), (2, "partial", ["a-rel"]))

        for day in (1, 2):
            run = self.start(at(day))
            self.assertEqual(run["sources"]["a-rel"]["window_start"], at(-1, -6))
            self.assertEqual(run["sources"]["a-doc"]["window_start"], at(day - 1, -6))
            self.record(run, "a-doc", now=at(day))
            self.record(run, "a-rel", status="partial", now=at(day))
            self.assertEqual(self.finish(run, now=at(day))[0], 2)

        code, out = self.cli("status")
        self.assertEqual(out["sources"]["a-rel"]["first_seen_at"], T0)
        self.assertIsNone(out["sources"]["a-rel"]["cursor"])

    def test_catch_up_is_capped_and_each_uncovered_interval_recorded_once(self):
        self.complete_run()
        run = self.start(at(20))
        self.assertEqual(run["sources"]["a-doc"]["window_start"], at(6, -6))
        self.assertIn({"source": "a-doc", "from": T0, "to": at(6)}, run["new_gaps"])
        self.assertEqual(self.finish(run, now=at(20))[0], 2)

        run = self.start(at(20))  # same-day retry: no new gap
        self.assertEqual(run["sources"]["a-doc"]["window_start"], at(6, -6))
        self.assertEqual(run["new_gaps"], [])
        self.assertEqual(self.finish(run, now=at(20))[0], 2)

        run = self.start(at(21))  # still failing: the cap slides one more day
        self.assertEqual(run["sources"]["a-doc"]["window_start"], at(7, -6))
        self.assertIn({"source": "a-doc", "from": at(6), "to": at(7)}, run["new_gaps"])
        self.assertEqual(self.finish(run, now=at(21))[0], 2)

        run = self.start(at(60))  # far later, still failing: window stays bounded
        self.assertEqual(run["sources"]["a-doc"]["window_start"], at(46, -6))
        self.assertIn({"source": "a-doc", "from": at(7), "to": at(46)}, run["new_gaps"])
        code, out = self.cli("status")
        # Contiguous uncovered intervals merge; no earlier date is forgotten.
        self.assertEqual([g for g in out["coverage_gaps"] if g["source"] == "a-doc"],
                         [{"source": "a-doc", "from": T0, "to": at(46)}])

    def test_weekly_source_not_due_does_not_block_complete_run(self):
        self.complete_run()
        run = self.start(at(1))
        self.assertEqual(run["not_due"], ["b-weekly"])
        self.record(run, "a-doc", now=at(1))
        self.record(run, "a-rel", now=at(1))
        code, out = self.finish(run, now=at(1))
        self.assertEqual((code, out["status"], out["missing"]), (0, "complete", []))

    def test_unrecorded_due_source_makes_run_partial(self):
        run = self.start()
        self.record(run, "a-doc")
        code, out = self.finish(run)
        self.assertEqual((code, out["status"], out["missing"]), (2, "partial", ["a-rel", "b-weekly"]))

    def test_disabled_sources_are_reported_not_silently_dropped(self):
        registry = json.loads(self.registry.read_text())
        registry["sources"][2]["enabled"] = False
        self.registry.write_text(json.dumps(registry))
        run = self.start()
        self.assertEqual(run["disabled"], ["b-weekly"])
        self.assertNotIn("b-weekly", run["sources"])
        self.record(run, "a-doc")
        self.record(run, "a-rel")
        code, out = self.finish(run)
        self.assertEqual((code, out["status"], out["disabled"]), (0, "complete", ["b-weekly"]))


class LeaseTest(WatchCase):
    def test_production_ledger_uses_real_clock_and_refuses_replay_clock(self):
        prod = str(self.base / "prod")
        self.assertEqual(self.raw(["init", "--ledger", prod])[1]["status"], "initialized")
        start = ["start-run", "--ledger", prod, "--registry", str(self.registry)]
        code, out = self.raw(start + ["--now", T0])
        self.assertEqual((code, out["status"]), (1, "now_not_allowed"))
        run = self.raw(start)[1]
        self.assertEqual(run["status"], "started")
        code, out = self.raw(start)
        self.assertEqual((code, out["status"], out["run_id"]), (5, "run_active", run["run_id"]))
        lease = ["--run", run["run_id"], "--token", run["token"]]
        code, out = self.raw(["record-source", "--ledger", prod, *lease, "--source", "a-rel",
                              "--status", "checked", "--items", "0", "--now", at(0, 1)])
        self.assertEqual((code, out["status"]), (1, "now_not_allowed"))
        code, out = self.raw(["init", "--ledger", str(self.base / "prod2"), "--now", T0])
        self.assertEqual((code, out["status"]), (1, "now_not_allowed"))

    def test_live_lease_blocks_second_run_and_expired_run_is_abandoned(self):
        first = self.start()
        code, out = self.cli("start-run", "--registry", str(self.registry), now=at(0, 1))
        self.assertEqual((code, out["status"], out["run_id"]), (5, "run_active", first["run_id"]))

        second = self.start(at(0, 5))
        self.assertEqual(second["abandoned"], [first["run_id"]])
        code, out = self.record(first, "a-doc", now=at(0, 5))
        self.assertEqual((code, out["status"]), (5, "lease_invalid"))

    def test_commands_renew_lease_but_expired_or_wrong_token_cannot_mutate(self):
        run = self.start()
        self.assertEqual(self.record(run, "a-doc", now=at(0, 3))[0], 0)
        self.assertEqual(self.record(run, "a-rel", now=at(0, 6))[0], 0)

        forged = dict(run, token="not-the-token")
        self.assertEqual(self.record(forged, "b-weekly", now=at(0, 6))[0], 5)

        late = at(0, 11)
        self.assertEqual(self.triage(run, "k1", now=late)[0], 5)
        self.assertEqual(self.reserve(run, "k1", now=late)[0], 5)
        self.assertEqual(self.finish(run, now=late)[0], 5)

    def test_expired_lease_cannot_dispatch_existing_reservation(self):
        run = self.start()
        self.triage(run, "k1")
        reservation = self.reserve(run, "k1")[1]["reservation"]
        code, out = self.dispatch(run, "k1", reservation, now=at(0, 5))
        self.assertEqual((code, out["status"]), (5, "lease_invalid"))


class SnapshotTest(WatchCase):
    def test_baseline_then_whitespace_only_unchanged_then_changed_with_diff(self):
        run = self.start()
        code, out = self.record(run, "a-doc", snapshot="TTL: 5 minutes\n\n  Minimum:   1024 tokens  \n")
        self.assertEqual((code, out["snapshot"]), (0, "baseline"))
        self.finish(run)

        run = self.start(at(1))
        out = self.record(run, "a-doc", now=at(1), snapshot="TTL: 5 minutes\nMinimum: 1024 tokens")[1]
        self.assertEqual(out["snapshot"], "unchanged")
        self.finish(run, now=at(1))

        run = self.start(at(2))
        out = self.record(run, "a-doc", now=at(2), snapshot="TTL: 1 hour\nMinimum: 1024 tokens")[1]
        self.assertEqual(out["snapshot"], "changed")
        self.assertTrue(out["content_id"].startswith("sha256:"))
        diff = Path(out["diff"]).read_text()
        self.assertIn("-TTL: 5 minutes", diff)
        self.assertIn("+TTL: 1 hour", diff)

    def test_snapshot_requires_checked_status(self):
        run = self.start()
        code, out = self.record(run, "a-doc", status="failed", snapshot="x")
        self.assertEqual((code, out["status"]), (1, "usage_error"))

    def test_unreadable_snapshot_is_json_error_not_traceback(self):
        run = self.start()
        args = self.lease(run) + ["--source", "a-doc", "--status", "checked",
                                  "--snapshot", str(self.base / "missing.txt")]
        code, out = self.cli("record-source", *args)
        self.assertEqual((code, out["status"]), (1, "io_error"))

    def test_checked_undated_doc_needs_nonempty_snapshot_and_dated_channel_needs_items(self):
        run = self.start()
        code, out = self.cli("record-source", *self.lease(run), "--source", "a-doc", "--status", "checked")
        self.assertEqual((code, out["status"]), (1, "snapshot_required"))
        code, out = self.record(run, "a-doc", snapshot=" \n\t\n")
        self.assertEqual((code, out["status"]), (1, "snapshot_required"))
        code, out = self.cli("record-source", *self.lease(run), "--source", "a-rel", "--status", "checked")
        self.assertEqual((code, out["status"]), (1, "items_required"))
        code, out = self.record(run, "a-rel", items=-1)
        self.assertEqual((code, out["status"]), (1, "usage_error"))
        self.assertEqual(self.record(run, "a-rel", status="failed")[0], 0)

    def test_snapshot_promotion_failure_is_reported_and_change_reported_again(self):
        run = self.start()
        self.record(run, "a-doc", snapshot="TTL: 5 minutes")
        self.finish(run)
        run = self.start(at(1))
        self.record(run, "a-doc", now=at(1), snapshot="TTL: 1 hour")
        real_replace = os.replace

        def failing_promote(src, dst):
            if Path(dst).parent.name == "snapshots" and "runs" not in Path(dst).parts:
                raise OSError("read-only snapshots")
            return real_replace(src, dst)

        with patch.object(watch.os, "replace", side_effect=failing_promote):
            code, out = self.finish(run, now=at(1))
        self.assertEqual((code, out["status"]), (1, "io_error"))
        run = self.start(at(2))
        self.assertEqual(self.record(run, "a-doc", now=at(2), snapshot="TTL: 1 hour")[1]["snapshot"], "changed")

    def test_change_seen_in_abandoned_run_is_reported_again(self):
        run = self.start()
        self.record(run, "a-doc", snapshot="TTL: 5 minutes")
        self.finish(run)

        run = self.start(at(1))
        self.assertEqual(self.record(run, "a-doc", now=at(1), snapshot="TTL: 1 hour")[1]["snapshot"], "changed")

        run = self.start(at(2))
        self.assertEqual(self.record(run, "a-doc", now=at(2), snapshot="TTL: 1 hour")[1]["snapshot"], "changed")


class TriageTest(WatchCase):
    def setUp(self):
        super().setUp()
        self.run_ = self.start()

    def test_implement_requires_complete_relevance_gate(self):
        code, out = self.triage(self.run_, "k1", gate=GATE[2:])
        self.assertEqual((code, out["status"]), (1, "gate_incomplete"))
        code, out = self.triage(self.run_, "k1", gate=GATE[:8])
        self.assertEqual((code, out["status"], out["missing"]), (1, "gate_incomplete", ["references"]))
        code, out = self.triage(self.run_, "k1", gate=GATE[:7] + ["marketing"] + GATE[8:])
        self.assertEqual((code, out["status"]), (1, "usage_error"))
        code, out = self.triage(self.run_, "k2", outcome="reject", gate=[])
        self.assertEqual((code, out["status"]), (0, "created"))

    def test_triage_source_must_be_known(self):
        args = self.lease(self.run_) + ["--key", "k1", "--source", "nope", "--outcome", "watch", "--reason", "r"]
        code, out = self.cli("triage", *args)
        self.assertEqual((code, out["status"]), (1, "unknown_source"))

    def test_bare_url_alias_is_refused(self):
        code, out = self.triage(self.run_, "k1", aliases=["https://example.com/a-doc"])
        self.assertEqual((code, out["status"]), (1, "invalid_alias"))
        for alias in ("https://example.com/a-doc@v1#", "https://example.com/a-doc@#topic"):
            code, out = self.triage(self.run_, "k1", aliases=[alias])
            self.assertEqual((code, out["status"]), (1, "invalid_alias"), alias)

    def test_distinct_changes_on_same_url_are_distinct_candidates(self):
        first = "https://example.com/a-doc@sha256:111111111111"
        second = "https://example.com/a-doc@sha256:222222222222"
        self.assertEqual(self.triage(self.run_, "openai:ttl:1h", aliases=[first])[1]["status"], "created")
        self.assertEqual(self.triage(self.run_, "openai:minimum:512", aliases=[second])[1]["status"], "created")

        # A reworded sighting of a known change reuses its key; the new alias is merged.
        code, out = self.triage(self.run_, "openai:ttl:1h", aliases=[first, "entry:changelog-2026-09-30"])
        self.assertEqual((code, out["status"], out["key"]), (0, "updated", "openai:ttl:1h"))
        candidates = self.cli("status")[1]["candidates"]
        self.assertEqual(sorted(candidates), ["openai:minimum:512", "openai:ttl:1h"])
        self.assertIn("entry:changelog-2026-09-30", candidates["openai:ttl:1h"]["aliases"])

    def test_shared_release_alias_with_different_key_is_a_conflict_not_a_merge(self):
        # One release (or one snapshot diff) can hold several unrelated changes.
        release = "https://github.com/x/y/releases@v0.31.0"
        self.assertEqual(self.triage(self.run_, "vllm:apc:hash", aliases=[release])[1]["status"], "created")
        first = self.cli("status")[1]["candidates"]["vllm:apc:hash"]

        code, out = self.triage(self.run_, "vllm:connector:x", outcome="watch", aliases=[release], gate=[])
        self.assertEqual((code, out["status"], out["keys"], out["aliases"]),
                         (3, "alias_conflict", ["vllm:apc:hash"], [release]))
        candidates = self.cli("status")[1]["candidates"]
        self.assertEqual(candidates["vllm:apc:hash"], first)
        self.assertNotIn("vllm:connector:x", candidates)
        self.assertEqual(self.reserve(self.run_, "vllm:apc:hash")[1]["status"], "reserved")

        # Reserved work is no sink for an unrelated change in the same release.
        gate = ["--evidence", "https://example.com/connector"]
        code, out = self.triage(self.run_, "vllm:connector:x", outcome="watch", aliases=[release], gate=gate)
        self.assertEqual((code, out["status"]), (3, "alias_conflict"))
        record = self.cli("status")[1]["candidates"]["vllm:apc:hash"]
        self.assertEqual((record["outcome"], record["gate"], record["evidence"], record["dispatch"]["status"]),
                         ("implement", first["gate"], first["evidence"], "reserved"))

        # Change-scoped bindings keep the two changes apart.
        scoped = release + "#connector-x"
        code, out = self.triage(self.run_, "vllm:connector:x", outcome="watch", aliases=[scoped], gate=[])
        self.assertEqual((code, out["status"]), (0, "created"))
        code, out = self.triage(self.run_, "vllm:apc:hash", aliases=[scoped])
        self.assertEqual((code, out["status"], out["keys"]), (3, "alias_conflict", ["vllm:connector:x"]))
        self.assertNotIn(scoped, self.cli("status")[1]["candidates"]["vllm:apc:hash"]["aliases"])
        # Deliberately reusing the existing key resolves the conflict (live work: evidence only).
        self.assertEqual(self.triage(self.run_, "vllm:apc:hash", aliases=[release])[1]["status"],
                         "duplicate_active")

        code, out = self.finish(self.run_)
        self.assertEqual((code, out["unresolved_conflicts"]), (2, []))

    def test_unresolved_alias_conflict_is_listed_by_finish_run(self):
        alias = "https://example.com/a-doc@sha256:111111111111"
        self.triage(self.run_, "k1", aliases=[alias])
        self.assertEqual(self.triage(self.run_, "k2", outcome="watch", aliases=[alias], gate=[])[0], 3)
        self.assertEqual(self.triage(self.run_, "k2", outcome="watch", aliases=[alias], gate=[])[0], 3)
        code, out = self.finish(self.run_)
        self.assertEqual((code, out["unresolved_conflicts"]),
                         (2, [{"key": "k2", "keys": ["k1"], "aliases": [alias]}]))

    def test_duplicate_of_active_work_merges_evidence_without_new_action(self):
        alias = "https://github.com/x/y/releases@v1.2.0"
        self.triage(self.run_, "vllm:apc:hash", aliases=[alias])
        self.assertEqual(self.reserve(self.run_, "vllm:apc:hash")[0], 0)
        gate = GATE[:4] + ["--evidence", "https://example.com/second"] + GATE[6:]
        code, out = self.triage(self.run_, "vllm:apc:hash", aliases=[alias, "entry:apc-hash-note"], gate=gate)
        self.assertEqual((code, out["status"], out["key"]), (3, "duplicate_active", "vllm:apc:hash"))
        record = self.cli("status")[1]["candidates"]["vllm:apc:hash"]
        self.assertIn("https://example.com/second", record["evidence"])
        self.assertIn("entry:apc-hash-note", record["aliases"])
        self.assertEqual(record["outcome"], "implement")

    def test_source_declared_dates_are_kept_verbatim_with_observed_at(self):
        args = ["--published-at", "2026-09", "--updated-at", "2026-09-29"]
        self.triage(self.run_, "k1", outcome="watch", gate=args)
        entry = self.cli("status")[1]["candidates"]["k1"]["history"][-1]
        self.assertEqual((entry["published_at"], entry["updated_at"], entry["observed_at"]),
                         ("2026-09", "2026-09-29", T0))


class DispatchTest(WatchCase):
    def setUp(self):
        super().setUp()
        self.run_ = self.start()
        for key in ("k1", "k2"):
            self.triage(self.run_, key)

    def test_reserve_requires_implement_outcome(self):
        self.triage(self.run_, "k3", outcome="watch", gate=[])
        code, out = self.reserve(self.run_, "k3")
        self.assertEqual((code, out["status"]), (3, "not_implement"))

    def test_active_cap_uncertain_reconcile_and_attempt_cap(self):
        reservation = self.reserve(self.run_, "k1", max_active=1)[1]["reservation"]
        code, out = self.reserve(self.run_, "k2", max_active=1)
        self.assertEqual((code, out["status"]), (4, "capacity"))

        mark = ["--key", "k1", "--reservation", reservation]
        self.assertEqual(self.cli("mark-uncertain", *self.lease(self.run_), *mark, "--note", "timeout")[0], 0)
        code, out = self.reserve(self.run_, "k1")
        self.assertEqual((code, out["status"]), (3, "reconcile_required"))
        self.assertEqual(self.cli("release", *self.lease(self.run_), *mark, "--reason", "not in list")[0], 0)

        code, out = self.reserve(self.run_, "k1", max_attempts=2)
        self.assertEqual((code, out["attempt"]), (0, 2))
        mark[-1] = out["reservation"]
        self.cli("release", *self.lease(self.run_), *mark, "--reason", "not in list")
        code, out = self.reserve(self.run_, "k1", max_attempts=2)
        self.assertEqual((code, out["status"]), (4, "attempts_exhausted"))

    def test_dispatch_requires_matching_reservation_and_records_model(self):
        reservation = self.reserve(self.run_, "k1")[1]["reservation"]
        code, out = self.dispatch(self.run_, "k1", "wrong")
        self.assertEqual((code, out["status"]), (3, "reservation_mismatch"))
        self.assertEqual(self.dispatch(self.run_, "k1", reservation)[0], 0)
        record = self.cli("status")[1]["candidates"]["k1"]["dispatch"]
        self.assertEqual((record["status"], record["model"], record["effort"]), ("active", "gpt-6-sol", "xhigh"))

        self.assertEqual(self.lifecycle(self.run_, "thread", "k1", "failed")[0], 0)
        self.assertEqual(self.reserve(self.run_, "k1")[1]["attempt"], 2)

    def test_pending_client_thread_id_is_never_recorded_as_thread_id(self):
        reservation = self.reserve(self.run_, "k1")[1]["reservation"]
        mark = ["--key", "k1", "--reservation", reservation]
        self.cli("mark-uncertain", *self.lease(self.run_), *mark,
                 "--note", "setup in progress", "--client-thread-id", "client-7")
        args = [*self.lease(self.run_), *mark, "--model", "gpt-6-sol", "--effort", "xhigh", "--reviewer", "r"]
        code, out = self.cli("dispatch", *args, "--thread-id", "client-7")
        self.assertEqual((code, out["status"]), (3, "client_id_not_thread_id"))
        self.assertEqual(self.cli("dispatch", *args, "--thread-id", "thread-ready-9")[0], 0)
        record = self.cli("status")[1]["candidates"]["k1"]["dispatch"]
        self.assertEqual((record["thread_id"], record["client_thread_id"]), ("thread-ready-9", "client-7"))

    def test_completed_thread_with_open_pr_blocks_duplicates_and_counts_toward_cap(self):
        reservation = self.reserve(self.run_, "k1")[1]["reservation"]
        self.dispatch(self.run_, "k1", reservation)
        self.lifecycle(self.run_, "pr", "k1", "open", T0, "--url", "https://github.com/o/r/pull/1")
        self.lifecycle(self.run_, "thread", "k1", "completed")

        self.assertEqual(self.reserve(self.run_, "k1")[1]["status"], "duplicate_active")
        self.assertEqual(self.reserve(self.run_, "k2", max_active=1)[1]["status"], "capacity")

        self.lifecycle(self.run_, "pr", "k1", "merged", T0, "--url", "https://github.com/o/r/pull/1")
        self.assertEqual(self.reserve(self.run_, "k2", max_active=1)[0], 0)
        code, out = self.reserve(self.run_, "k1")
        self.assertEqual((code, out["status"]), (3, "already_merged"))

    def test_closed_unmerged_pr_and_completed_without_pr_require_retriage(self):
        reservation = self.reserve(self.run_, "k1")[1]["reservation"]
        self.dispatch(self.run_, "k1", reservation)
        self.lifecycle(self.run_, "pr", "k1", "open", T0, "--url", "https://github.com/o/r/pull/2")
        self.lifecycle(self.run_, "pr", "k1", "closed_unmerged", T0, "--url", "https://github.com/o/r/pull/2")
        self.lifecycle(self.run_, "thread", "k1", "completed")
        self.assertEqual(self.reserve(self.run_, "k1")[1]["status"], "needs_decision")
        self.triage(self.run_, "k1", reason="reviewer asked for a narrower change")
        self.assertEqual(self.reserve(self.run_, "k1")[1]["status"], "reserved")

        reservation = self.reserve(self.run_, "k2")[1]["reservation"]
        self.dispatch(self.run_, "k2", reservation)
        self.lifecycle(self.run_, "thread", "k2", "completed")
        self.assertEqual(self.reserve(self.run_, "k2")[1]["status"], "needs_decision")

    def test_pr_recorded_after_thread_completion_clears_needs_decision(self):
        reservation = self.reserve(self.run_, "k1")[1]["reservation"]
        self.dispatch(self.run_, "k1", reservation)
        self.lifecycle(self.run_, "thread", "k1", "completed")
        self.lifecycle(self.run_, "pr", "k1", "open", T0, "--url", "https://github.com/o/r/pull/3")
        status = self.cli("status")[1]
        self.assertFalse(status["candidates"]["k1"]["needs_decision"])
        self.assertNotIn({"key": "k1", "reason": "needs decision"}, status["attention"])
        self.lifecycle(self.run_, "pr", "k1", "merged", T0, "--url", "https://github.com/o/r/pull/3")
        self.assertFalse(self.cli("status")[1]["candidates"]["k1"]["needs_decision"])

    def test_inactive_implement_backlog_stays_visible_after_sources_advance(self):
        for key in ("k3", "k4"):
            self.triage(self.run_, key)
        reservation = self.reserve(self.run_, "k1")[1]["reservation"]
        self.dispatch(self.run_, "k1", reservation)
        self.lifecycle(self.run_, "thread", "k1", "failed", T0, "--note", "worker unavailable")
        reservation = self.reserve(self.run_, "k2")[1]["reservation"]
        self.cli("release", *self.lease(self.run_), "--key", "k2", "--reservation", reservation,
                 "--reason", "confirmed absent")
        reservation = self.reserve(self.run_, "k4")[1]["reservation"]
        self.dispatch(self.run_, "k4", reservation)
        self.assertEqual(self.reserve(self.run_, "k3", max_active=1)[1]["status"], "capacity")
        self.lifecycle(self.run_, "pr", "k4", "open", T0, "--url", "https://github.com/o/r/pull/4")
        self.lifecycle(self.run_, "pr", "k4", "merged", T0, "--url", "https://github.com/o/r/pull/4")
        self.lifecycle(self.run_, "thread", "k4", "completed")
        for source_id in ("a-doc", "a-rel", "b-weekly"):
            self.record(self.run_, source_id)
        self.assertEqual(self.finish(self.run_)[0], 0)
        self.complete_run(at(1), sources=("a-doc", "a-rel"))  # snapshots and cursors advance

        attention = self.cli("status", now=at(1))[1]["attention"]
        self.assertEqual(attention, [
            {"key": "k1", "reason": "dispatch backlog: failed, attempt 1"},
            {"key": "k2", "reason": "dispatch backlog: released, attempt 1"},
            {"key": "k3", "reason": "dispatch backlog: none, attempt 0"},
        ])  # merged k4 is not reopened

        run = self.start(at(2))
        self.assertEqual(self.reserve(run, "k3", now=at(2))[1]["status"], "reserved")
        self.assertEqual(self.reserve(run, "k1", now=at(2))[1]["attempt"], 2)

    def test_exhausted_attempts_require_a_decision_and_keep_queue_evidence(self):
        for attempt in (1, 2):
            reservation = self.reserve(self.run_, "k1")[1]["reservation"]
            self.dispatch(self.run_, "k1", reservation)
            self.lifecycle(self.run_, "thread", "k1", "failed", T0, "--note", f"worker down {attempt}")
        code, out = self.reserve(self.run_, "k1", max_attempts=2)
        self.assertEqual((code, out["status"], out["needs_decision"]), (4, "attempts_exhausted", True))

        status = self.cli("status")[1]
        record = status["candidates"]["k1"]
        self.assertEqual((record["outcome"], record["dispatch"]["status"], record["dispatch"]["attempt"],
                          record["dispatch"]["note"], record["dispatch"]["thread_id"]),
                         ("implement", "failed", 2, "worker down 2", "thread-1"))
        self.assertEqual((record["history"][-1]["event"], record["history"][-1]["max_attempts"]),
                         ("attempts_exhausted", 2))
        self.assertEqual([item for item in status["attention"] if item["key"] == "k1"],
                         [{"key": "k1", "reason": "needs decision"}])
        self.assertEqual(self.reserve(self.run_, "k1")[1]["status"], "needs_decision")

    def test_concurrent_reservations_have_single_winner(self):
        args = [sys.executable, str(MODULE), "reserve", "--ledger", str(self.ledger), "--now", T0,
                *self.lease(self.run_), "--key", "k1", "--max-active", "9"]
        procs = [subprocess.Popen(args, stdout=subprocess.PIPE, text=True,
                                  env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}) for _ in range(6)]
        results = [(p.wait(timeout=60), json.loads(p.stdout.read())) for p in procs]
        for p in procs:
            p.stdout.close()
        self.assertEqual(sorted(code for code, _ in results), [0, 3, 3, 3, 3, 3])
        self.assertEqual({out["status"] for code, out in results if code}, {"duplicate_active"})


class SafetyTest(WatchCase):
    def test_ledger_inside_git_work_tree_is_refused(self):
        (self.base / "checkout" / ".git").mkdir(parents=True)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = watch.main(["init", "--ledger", str(self.base / "checkout" / "state")])
        out = json.loads(buffer.getvalue())
        self.assertEqual((code, out["ok"], out["status"]), (1, False, "ledger_in_checkout"))

    def test_failed_atomic_write_keeps_previous_ledger(self):
        run = self.start()
        before = (self.ledger / "ledger.json").read_text()
        with patch.object(watch.os, "replace", side_effect=OSError("disk full")):
            code, out = self.triage(run, "k1")
        self.assertEqual((code, out["status"]), (1, "write_failed"))
        self.assertEqual((self.ledger / "ledger.json").read_text(), before)
        self.assertEqual(sorted(p.name for p in self.ledger.iterdir() if p.name.startswith(".")), [])

    def test_invalid_now_is_usage_error(self):
        code, out = self.cli("status", now="invalid")
        self.assertEqual((code, out["status"]), (1, "usage_error"))

    def test_corrupt_or_unsupported_ledger_is_reported_and_left_untouched(self):
        path = self.ledger / "ledger.json"
        for text, status in (("{not json", "ledger_corrupt"), ('{"schema": 99}', "ledger_unsupported")):
            path.write_text(text)
            for command in (("status",), ("start-run", "--registry", str(self.registry))):
                code, out = self.cli(*command)
                self.assertEqual((code, out["status"]), (1, status))
            code, out = self.cli("init")
            self.assertEqual((code, out["status"]), (1, status))
            self.assertEqual(path.read_text(), text)


class RegistryTest(unittest.TestCase):
    REQUIRED_GROUPS = {
        "openai", "anthropic", "google-gemini", "google-vertex", "aws-bedrock", "azure-openai",
        "openrouter", "deepseek", "qwen", "zai", "yandex", "vllm", "sglang", "lmcache",
        "nvidia-dynamo", "tensorrt-llm", "litellm", "llm-d", "vercel-ai-sdk", "mastra",
    }

    def validate(self, registry, repo_root=ROOT):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = watch.main(["validate-registry", "--registry", str(registry), "--repo-root", str(repo_root)])
        return code, json.loads(buffer.getvalue())

    def test_repository_registry_is_valid_and_covers_required_groups(self):
        code, out = self.validate(REGISTRY)
        self.assertEqual((code, out["errors"]), (0, []))
        groups = {item["group"] for item in json.loads(REGISTRY.read_text())["sources"]}
        self.assertEqual(self.REQUIRED_GROUPS - groups, set())

    def test_registry_validation_reports_each_broken_entry(self):
        bad = [
            source("dup"), source("dup"),
            dict(source("plain-http"), url="http://example.com/x"),
            dict(source("missing-ref"), affects=["audit-prompt-caching/references/nope.md"]),
            dict(source("blog"), type="blog"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.json"
            path.write_text(json.dumps({"schema": 1, "sources": bad}))
            code, out = self.validate(path)
        self.assertEqual(code, 1)
        text = "\n".join(out["errors"])
        for needle in ("duplicate id: dup", "plain-http: url must be https",
                       "missing-ref: affects path not found", "blog: blog sources must be discovery_only"):
            self.assertIn(needle, text)

    def test_gh_api_paths_with_query_strings_are_quoted_for_zsh(self):
        # zsh treats an unquoted "?" as a glob and aborts with "no matches found".
        bad = [dict(source("gh-rel"), extraction="Releases. gh api repos/o/r/releases?per_page=30; page back")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.json"
            path.write_text(json.dumps({"schema": 1, "sources": bad}))
            code, out = self.validate(path)
        self.assertEqual(code, 1)
        self.assertIn("gh-rel: quote the gh api path repos/o/r/releases?per_page=30", "\n".join(out["errors"]))
        self.assertEqual(watch.unquoted_gh_api_paths("gh api 'repos/o/r/releases?per_page=30&page=2'"), [])
        runbook = (WATCH_DIR / "daily-run.md").read_text()
        self.assertIn("gh api '", runbook)
        self.assertEqual(watch.unquoted_gh_api_paths(runbook), [])


if __name__ == "__main__":
    unittest.main()
