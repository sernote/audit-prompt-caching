#!/usr/bin/env python3
"""Durable ledger for the daily cache source watch.

Python stdlib only; POSIX file locking (fcntl). Every command prints one JSON
object whose "ok" field matches the exit status. See README.md for the
workflow and the exit-code contract.
"""

import argparse
import contextlib
import difflib
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = 1
EXIT_OK, EXIT_ERROR, EXIT_PARTIAL, EXIT_CONFLICT, EXIT_LIMIT, EXIT_LEASE, EXIT_LOCK = range(7)

OUTCOMES = ("implement", "watch", "reject", "needs-evidence")
BEHAVIORS = (
    "cache-controls", "accounting", "ttl-threshold", "routing-identity",
    "isolation-residency", "pricing-roi", "engine-semantics",
)
SOURCE_TYPES = ("contract-doc", "pricing", "changelog", "release-feed", "release-page", "blog")
PRIORITIES = ("p0", "p1", "p2")
DATING = ("dated-entries", "undated-doc")
CADENCE_HOURS = {"daily": 24, "weekly": 168}
REQUIRED_FIELDS = (
    "id", "group", "priority", "type", "url", "dating", "cadence",
    "affects", "cache_relevance", "extraction", "verified",
)
SCHEDULE_SLACK = timedelta(hours=1)
ACTIVE_DISPATCH = ("reserved", "uncertain", "active", "stalled")
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GH_API_ARGS = re.compile(r"\bgh api\b([^\n`;]*)")
LEDGER_KEYS = ("sources", "runs", "gaps", "candidates")


class Failure(Exception):
    def __init__(self, code, status, **extra):
        super().__init__(status)
        self.code, self.status, self.extra = code, status, extra


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Failure(EXIT_ERROR, "usage_error", message=message)


# -- time -------------------------------------------------------------------

def parse_time(value):
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Failure(EXIT_ERROR, "usage_error", message=f"invalid ISO 8601 timestamp: {value}") from None
    if moment.tzinfo is None:
        raise Failure(EXIT_ERROR, "usage_error", message=f"timestamp needs a timezone: {value}")
    return moment.astimezone(timezone.utc)


def fmt(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_time(args, ledger):
    """Real UTC time; --now is accepted only by ledgers initialized with --test-clock."""
    if args.now:
        if ledger.get("clock") != "test":
            raise Failure(EXIT_ERROR, "now_not_allowed",
                          message="--now needs a ledger created with init --test-clock (tests and smoke runs)")
        return parse_time(args.now)
    return datetime.now(timezone.utc).replace(microsecond=0)


# -- storage ----------------------------------------------------------------

def ledger_dir(args):
    raw = args.ledger or os.environ.get("CACHE_WATCH_LEDGER")
    if not raw:
        raise Failure(EXIT_ERROR, "usage_error", message="--ledger or CACHE_WATCH_LEDGER is required")
    path = Path(raw).expanduser().resolve()
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            raise Failure(EXIT_ERROR, "ledger_in_checkout", checkout=str(parent))
    return path


@contextlib.contextmanager
def locked(directory, timeout=30.0):
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(directory / "ledger.lock", os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as error:
        raise Failure(EXIT_ERROR, "io_error", message=str(error)) from None
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Failure(EXIT_LOCK, "lock_timeout") from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def load(directory):
    path = directory / "ledger.json"
    if not path.exists():
        raise Failure(EXIT_ERROR, "not_initialized", ledger=str(directory))
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise Failure(EXIT_ERROR, "io_error", message=str(error)) from None
    except ValueError as error:
        raise Failure(EXIT_ERROR, "ledger_corrupt", message=str(error), ledger=str(path)) from None
    if not isinstance(ledger, dict) or ledger.get("schema") != SCHEMA or not all(
            isinstance(ledger.get(key), (dict, list)) for key in LEDGER_KEYS):
        raise Failure(EXIT_ERROR, "ledger_unsupported", expected_schema=SCHEMA, ledger=str(path))
    return ledger


def save(directory, ledger):
    try:
        atomic_write(directory / "ledger.json", json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    except OSError as error:
        raise Failure(EXIT_ERROR, "write_failed", error=str(error)) from None


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# -- registry ---------------------------------------------------------------

def unquoted_gh_api_paths(text):
    """gh api arguments with "?" left unquoted: zsh globs them and aborts."""
    return [arg for match in GH_API_ARGS.finditer(text) for arg in match.group(1).split()
            if "?" in arg and arg[0] not in "'\""]


def registry_errors(data, repo_root=None):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return [f"registry schema must be {SCHEMA}"]
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        return ["registry needs a non-empty sources list"]
    errors, ids, urls = [], set(), set()
    enums = {"priority": PRIORITIES, "type": SOURCE_TYPES, "dating": DATING, "cadence": tuple(CADENCE_HOURS)}
    for item in sources:
        name = item.get("id", "<missing id>")
        errors += [f"{name}: missing field {field}" for field in REQUIRED_FIELDS if field not in item]
        if name in ids:
            errors.append(f"duplicate id: {name}")
        ids.add(name)
        if not SOURCE_ID.match(str(name)):
            errors.append(f"{name}: id must be lowercase letters, digits and dashes")
        url = str(item.get("url", ""))
        if not url.startswith("https://"):
            errors.append(f"{name}: url must be https")
        if url in urls:
            errors.append(f"{name}: duplicate url {url}")
        urls.add(url)
        for field, allowed in enums.items():
            if field in item and item[field] not in allowed:
                errors.append(f"{name}: {field} must be one of {', '.join(allowed)}")
        if item.get("type") == "blog" and item.get("discovery_only") is not True:
            errors.append(f"{name}: blog sources must be discovery_only")
        errors += [f"{name}: quote the gh api path {arg}"
                   for arg in unquoted_gh_api_paths(str(item.get("extraction", "")))]
        affects = item.get("affects")
        if not isinstance(affects, list) or not affects:
            errors.append(f"{name}: affects must list repository paths")
        elif repo_root is not None:
            errors += [f"{name}: affects path not found: {p}" for p in affects if not (repo_root / p).exists()]
        verified = item.get("verified")
        if not isinstance(verified, dict) or not all(verified.get(k) for k in ("on", "method", "result")):
            errors.append(f"{name}: verified needs on, method and result")
    return errors


def load_registry(path, repo_root=None):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Failure(EXIT_ERROR, "invalid_registry", errors=[str(error)]) from None
    errors = registry_errors(data, repo_root)
    if errors:
        raise Failure(EXIT_ERROR, "invalid_registry", errors=errors)
    return data


def cmd_validate_registry(args):
    repo_root = Path(args.repo_root).resolve() if args.repo_root else None
    data = load_registry(args.registry, repo_root)
    return EXIT_OK, {"status": "valid", "errors": [], "sources": len(data["sources"])}


# -- runs and coverage ------------------------------------------------------

def cmd_init(args):
    directory = ledger_dir(args)
    with locked(directory):
        if (directory / "ledger.json").exists():
            load(directory)  # report a corrupt or foreign ledger instead of accepting it
            return EXIT_OK, {"status": "exists", "ledger": str(directory)}
        clock = {"clock": "test" if args.test_clock else "real"}
        ledger = {"schema": SCHEMA, "clock": clock["clock"], "created_at": fmt(current_time(args, clock)),
                  "sources": {}, "runs": {}, "gaps": [], "candidates": {}}
        save(directory, ledger)
    return EXIT_OK, {"status": "initialized", "ledger": str(directory), "clock": ledger["clock"]}


def add_gap(ledger, source_id, start, end):
    segment = {"source": source_id, "from": fmt(start), "to": fmt(end)}
    for gap in ledger["gaps"]:
        if gap["source"] == source_id and gap["to"] == segment["from"]:
            gap["to"] = segment["to"]
            return segment
    ledger["gaps"].append(dict(segment))
    return segment


def abandon_expired_runs(ledger, now):
    abandoned = []
    for run_id, run in sorted(ledger["runs"].items()):
        if run["status"] != "open":
            continue
        if now < parse_time(run["lease_expires_at"]):
            raise Failure(EXIT_LEASE, "run_active", run_id=run_id, lease_expires_at=run["lease_expires_at"])
        run["status"] = "abandoned"
        abandoned.append(run_id)
    return abandoned


def plan_source(ledger, source, now, overlap, max_catchup, new_gaps):
    state = ledger["sources"].setdefault(
        source["id"], {"first_seen_at": fmt(now), "cursor": None, "pending_from": None})
    cursor = parse_time(state["cursor"]) if state["cursor"] else None
    pending = parse_time(state["pending_from"]) if state["pending_from"] else None
    cadence = timedelta(hours=CADENCE_HOURS[source["cadence"]])
    if cursor and not pending and now - cursor < cadence - SCHEDULE_SLACK:
        return None
    primary_start = now - timedelta(hours=24)
    requested = min(primary_start, pending or cursor or primary_start)
    floor = now - max_catchup
    if requested < floor:
        new_gaps.append(add_gap(ledger, source["id"], requested, floor))
        requested = floor
    state["pending_from"] = fmt(requested)
    return {"requested_from": fmt(requested), "window_start": fmt(requested - overlap), "window_end": fmt(now)}


def cmd_start_run(args):
    directory = ledger_dir(args)
    registry = load_registry(args.registry)
    overlap = timedelta(hours=args.overlap_hours)
    max_catchup = timedelta(days=args.max_catchup_days)
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
        abandoned = abandon_expired_runs(ledger, now)
        windows, not_due, new_gaps = {}, [], []
        dating, disabled = {}, []
        for source in registry["sources"]:
            if source.get("enabled", True) is False:
                disabled.append(source["id"])
                continue
            window = plan_source(ledger, source, now, overlap, max_catchup, new_gaps)
            if window is None:
                not_due.append(source["id"])
            else:
                windows[source["id"]] = window
                dating[source["id"]] = source["dating"]
        run_id = f"run-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
        token = secrets.token_hex(24)  # hex never starts with "-", so argparse cannot misread it
        expires = fmt(now + timedelta(hours=args.lease_hours))
        ledger["runs"][run_id] = {
            "started_at": fmt(now), "status": "open", "token_sha256": digest(token),
            "lease_hours": args.lease_hours, "lease_expires_at": expires,
            "due": dict(sorted(dating.items())), "disabled": disabled, "checks": {},
            "conflicts": [],
        }
        save(directory, ledger)
    return EXIT_OK, {
        "status": "started", "run_id": run_id, "token": token, "lease_expires_at": expires,
        "primary_window": {"start": fmt(now - timedelta(hours=24)), "end": fmt(now)},
        "sources": windows, "not_due": not_due, "new_gaps": new_gaps, "abandoned": abandoned,
        "disabled": disabled,
    }


def open_run(ledger, args, now):
    run = ledger["runs"].get(args.run)
    valid = (
        run is not None and run["status"] == "open"
        and hmac.compare_digest(run["token_sha256"], digest(args.token))
        and now < parse_time(run["lease_expires_at"])
    )
    if not valid:
        raise Failure(EXIT_LEASE, "lease_invalid", run_id=args.run)
    run["lease_expires_at"] = fmt(now + timedelta(hours=run["lease_hours"]))
    return run


def normalize_snapshot(text):
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "".join(f"{line}\n" for line in lines if line)


def read_snapshot(snapshot_path):
    try:
        return normalize_snapshot(Path(snapshot_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        raise Failure(EXIT_ERROR, "io_error", message=str(error)) from None


def stage_snapshot(directory, run_id, source_id, text):
    result = {"content_id": f"sha256:{digest(text)[:16]}"}
    committed = directory / "snapshots" / f"{source_id}.txt"
    run_dir = directory / "runs" / run_id
    if not committed.exists():
        result["state"] = "baseline"
    elif committed.read_text(encoding="utf-8") == text:
        result["state"] = "unchanged"
    else:
        result["state"] = "changed"
        diff = difflib.unified_diff(committed.read_text(encoding="utf-8").splitlines(), text.splitlines(),
                                    "previous", "current", lineterm="")
        diff_path = run_dir / f"{source_id}.diff"
        atomic_write(diff_path, "\n".join(diff) + "\n")
        result["diff"] = str(diff_path)
    staged = run_dir / "snapshots" / f"{source_id}.txt"
    atomic_write(staged, text)
    result["staged"] = str(staged)
    return result


def cmd_record_source(args):
    directory = ledger_dir(args)
    if args.snapshot and args.status != "checked":
        raise Failure(EXIT_ERROR, "usage_error", message="--snapshot requires --status checked")
    if args.items is not None and args.items < 0:
        raise Failure(EXIT_ERROR, "usage_error", message="--items must be zero or more")
    text = read_snapshot(args.snapshot) if args.snapshot else None
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
        run = open_run(ledger, args, now)
        if args.source not in run["due"]:
            raise Failure(EXIT_ERROR, "source_not_due", source=args.source)
        if args.status == "checked" and run["due"][args.source] == "undated-doc" and not text:
            raise Failure(EXIT_ERROR, "snapshot_required", source=args.source,
                          message="a checked undated doc needs a non-empty cache-relevant extract")
        if args.status == "checked" and run["due"][args.source] == "dated-entries" and args.items is None:
            raise Failure(EXIT_ERROR, "items_required", source=args.source,
                          message="a checked dated channel needs --items (in-window entries examined)")
        previous = run["checks"].get(args.source, {})
        check = {"status": args.status, "attempts": previous.get("attempts", 0) + 1,
                 "observed_at": fmt(now), "note": args.note, "items": args.items}
        if text:
            try:
                check["snapshot"] = stage_snapshot(directory, args.run, args.source, text)
            except OSError as error:
                raise Failure(EXIT_ERROR, "io_error", message=str(error)) from None
        run["checks"][args.source] = check
        save(directory, ledger)
    snapshot = check.get("snapshot", {})
    return EXIT_OK, {"status": "recorded", "source": args.source, "check": args.status,
                     "attempts": check["attempts"], "snapshot": snapshot.get("state"),
                     "content_id": snapshot.get("content_id"), "diff": snapshot.get("diff")}


def cmd_finish_run(args):
    directory = ledger_dir(args)
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
        run = open_run(ledger, args, now)
        checked, failed, missing = [], [], []
        for source_id in run["due"]:
            check = run["checks"].get(source_id)
            bucket = missing if check is None else checked if check["status"] == "checked" else failed
            bucket.append(source_id)
        promote = []
        for source_id in checked:
            state = ledger["sources"][source_id]
            state["cursor"], state["pending_from"] = run["started_at"], None
            snapshot = run["checks"][source_id].get("snapshot")
            if snapshot:
                state.setdefault("baseline_observed_at", run["checks"][source_id]["observed_at"])
                state["snapshot"] = {"content_id": snapshot["content_id"],
                                     "observed_at": run["checks"][source_id]["observed_at"]}
                promote.append((Path(snapshot["staged"]), directory / "snapshots" / f"{source_id}.txt"))
        run["status"] = "complete" if not failed and not missing else "partial"
        run["finished_at"] = fmt(now)
        unresolved = [{name: c[name] for name in ("key", "keys", "aliases")}
                      for c in run.get("conflicts", []) if not c.get("resolved")]
        save(directory, ledger)
        # Promote after the ledger commit: a crash here re-reports a change, never hides one.
        unpromoted = []
        for staged, committed in promote:
            try:
                committed.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, committed)
            except OSError as error:
                unpromoted.append({"source": committed.stem, "error": str(error)})
    if unpromoted:
        return EXIT_ERROR, {"status": "io_error", "run_id": args.run, "run_status": run["status"],
                            "unpromoted_snapshots": unpromoted,
                            "message": "ledger committed; unpromoted snapshots are compared again next run"}
    code = EXIT_OK if run["status"] == "complete" else EXIT_PARTIAL
    return code, {"status": run["status"], "run_id": args.run,
                  "checked": checked, "failed": failed, "missing": missing,
                  "disabled": run.get("disabled", []), "unresolved_conflicts": unresolved}


# -- candidates and dispatch ------------------------------------------------

def normalize_alias(alias):
    alias = alias.strip()
    if alias.startswith("entry:") and len(alias) > len("entry:"):
        return alias
    locator, sep, binding = alias.rpartition("@")
    version, scoped, topic = binding.partition("#")
    if (not sep or not locator or not version or (scoped and not topic) or "/" in binding
            or any(c.isspace() for c in alias)):
        raise Failure(EXIT_ERROR, "invalid_alias", alias=alias,
                      message="use <url>@<version-or-content-id>[#<topic>] or entry:<immutable id>")
    return f"{locator.rstrip('/')}@{binding}"


def merge_unique(existing, extra):
    return existing + [item for item in extra if item not in existing]


def has_active_work(candidate):
    return candidate["dispatch"]["status"] in ACTIVE_DISPATCH or candidate["pr"]["status"] == "open"


def cmd_triage(args):
    directory = ledger_dir(args)
    key = args.key.strip().lower()
    aliases = [normalize_alias(alias) for alias in args.alias]
    gate = {"before": args.before, "after": args.after, "behaviors": args.behavior, "references": args.reference}
    if args.outcome == "implement":
        missing = [name for name in ("before", "after", "behaviors") if not gate[name]]
        missing += [] if args.evidence else ["evidence"]
        missing += [] if gate["references"] else ["references"]
        if missing:
            raise Failure(EXIT_ERROR, "gate_incomplete", missing=missing)
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
        open_run(ledger, args, now)
        if args.source not in ledger["sources"]:
            raise Failure(EXIT_ERROR, "unknown_source", source=args.source)
        candidates = ledger["candidates"]
        run = ledger["runs"][args.run]
        # An alias names a release or snapshot, which can hold several changes: a
        # shared alias under another key is a conflict for the coordinator, never a merge.
        owners = sorted(k for k, c in candidates.items() if k != key and set(c["aliases"]) & set(aliases))
        if owners:
            shared = sorted({a for k in owners for a in candidates[k]["aliases"]} & set(aliases))
            conflict = {"key": key, "keys": owners, "aliases": shared}
            conflicts = run.setdefault("conflicts", [])
            if not any(not c.get("resolved") and all(c[name] == conflict[name] for name in conflict)
                       for c in conflicts):
                conflicts.append(dict(conflict, at=fmt(now)))
            save(directory, ledger)
            return EXIT_CONFLICT, {"status": "alias_conflict", **conflict}
        for conflict in run.get("conflicts", []):
            if key == conflict["key"] or key in conflict["keys"]:
                conflict["resolved"] = True
        # Source-declared dates stay verbatim (a date-only or month-only value is never
        # expanded to a midnight timestamp); observed_at is when this run saw the change.
        entry = {"at": fmt(now), "run": args.run, "outcome": args.outcome, "reason": args.reason,
                 "published_at": args.published_at, "updated_at": args.updated_at, "observed_at": fmt(now)}
        if key in candidates:
            candidate = candidates[key]
            candidate["aliases"] = merge_unique(candidate["aliases"], aliases)
            candidate["evidence"] = merge_unique(candidate["evidence"], args.evidence)
            if has_active_work(candidate):
                candidate["history"].append(dict(entry, ignored="duplicate_active"))
                save(directory, ledger)
                return EXIT_CONFLICT, {"status": "duplicate_active", "key": key}
            candidate.update(outcome=args.outcome, reason=args.reason, needs_decision=False)
            if any(gate.values()):
                candidate["gate"] = gate
            candidate["history"].append(entry)
            status = "updated"
        else:
            candidates[key] = {
                "key": key, "source": args.source, "outcome": args.outcome, "reason": args.reason,
                "aliases": aliases, "evidence": list(args.evidence), "gate": gate, "history": [entry],
                "needs_decision": False, "created_at": fmt(now),
                "dispatch": {"status": "none", "attempt": 0}, "pr": {"status": "none"},
            }
            status = "created"
        save(directory, ledger)
    return EXIT_OK, {"status": status, "key": key}


def candidate_for(ledger, args):
    candidate = ledger["candidates"].get(args.key.strip().lower())
    if candidate is None:
        raise Failure(EXIT_ERROR, "unknown_candidate", key=args.key)
    return candidate


def reserve_block(ledger, candidate, args):
    dispatch = candidate["dispatch"]
    if candidate["pr"]["status"] == "merged":
        return EXIT_CONFLICT, "already_merged"
    if dispatch["status"] == "uncertain":
        return EXIT_CONFLICT, "reconcile_required"
    if has_active_work(candidate):
        return EXIT_CONFLICT, "duplicate_active"
    if candidate["needs_decision"]:
        return EXIT_CONFLICT, "needs_decision"
    if candidate["outcome"] != "implement":
        return EXIT_CONFLICT, "not_implement"
    if dispatch["attempt"] >= args.max_attempts:
        return EXIT_LIMIT, "attempts_exhausted"
    if sum(has_active_work(c) for c in ledger["candidates"].values()) >= args.max_active:
        return EXIT_LIMIT, "capacity"
    return None


def cmd_reserve(args):
    directory = ledger_dir(args)
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
        open_run(ledger, args, now)
        candidate = candidate_for(ledger, args)
        block = reserve_block(ledger, candidate, args)
        if block is not None and block[1] == "attempts_exhausted":
            # The dispatch record stays as queue evidence; a decision replaces the retry.
            candidate["needs_decision"] = True
            candidate["history"].append({"at": fmt(now), "run": args.run, "event": "attempts_exhausted",
                                         "attempt": candidate["dispatch"]["attempt"],
                                         "max_attempts": args.max_attempts})
        if block is None:
            dispatch = candidate["dispatch"]
            reservation = secrets.token_hex(8)
            candidate["dispatch"] = {"status": "reserved", "attempt": dispatch["attempt"] + 1,
                                     "reservation": reservation, "reserved_at": fmt(now), "run": args.run}
        save(directory, ledger)
    if block:
        return block[0], {"status": block[1], "key": candidate["key"],
                          "needs_decision": candidate["needs_decision"]}
    return EXIT_OK, {"status": "reserved", "key": candidate["key"], "reservation": reservation,
                     "attempt": candidate["dispatch"]["attempt"]}


def transition(args, allowed, apply):
    """Apply a reservation-bound dispatch transition under the run lease."""
    directory = ledger_dir(args)
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
        open_run(ledger, args, now)
        candidate = candidate_for(ledger, args)
        dispatch = candidate["dispatch"]
        if dispatch["status"] not in allowed:
            raise Failure(EXIT_CONFLICT, "invalid_transition", key=candidate["key"], current=dispatch["status"])
        if not hmac.compare_digest(dispatch.get("reservation", ""), args.reservation):
            raise Failure(EXIT_CONFLICT, "reservation_mismatch", key=candidate["key"])
        apply(dispatch, fmt(now))
        save(directory, ledger)
    return EXIT_OK, {"status": dispatch["status"], "key": candidate["key"]}


def cmd_dispatch(args):
    def apply(dispatch, now):
        if args.thread_id == dispatch.get("client_thread_id"):
            raise Failure(EXIT_CONFLICT, "client_id_not_thread_id",
                          message="reconcile the ready thread ID; a pending client ID is not a thread ID")
        dispatch.update(status="active", thread_id=args.thread_id, model=args.model, effort=args.effort,
                        reviewer=args.reviewer, catalog_checked_at=args.catalog_checked_at, dispatched_at=now)
    return transition(args, ("reserved", "uncertain"), apply)


def cmd_mark_uncertain(args):
    return transition(args, ("reserved",), lambda d, now: d.update(
        status="uncertain", note=args.note, client_thread_id=args.client_thread_id, updated_at=now))


def cmd_release(args):
    return transition(args, ("reserved", "uncertain"),
                      lambda d, now: d.update(status="released", note=args.reason, updated_at=now))


def cmd_thread(args):
    directory = ledger_dir(args)
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
        open_run(ledger, args, now)
        candidate = candidate_for(ledger, args)
        dispatch = candidate["dispatch"]
        if dispatch["status"] not in ("active", "stalled"):
            raise Failure(EXIT_CONFLICT, "invalid_transition", key=candidate["key"], current=dispatch["status"])
        dispatch.update(status=args.status, note=args.note, updated_at=fmt(now))
        if args.status == "completed" and candidate["pr"]["status"] not in ("open", "merged"):
            candidate["needs_decision"] = True
        save(directory, ledger)
    return EXIT_OK, {"status": args.status, "key": candidate["key"], "needs_decision": candidate["needs_decision"]}


def cmd_pr(args):
    directory = ledger_dir(args)
    allowed = {"open": ("none", "closed_unmerged"), "merged": ("open",), "closed_unmerged": ("open",)}
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
        open_run(ledger, args, now)
        candidate = candidate_for(ledger, args)
        current = candidate["pr"]["status"]
        if current not in allowed[args.status]:
            raise Failure(EXIT_CONFLICT, "invalid_transition", key=candidate["key"], current=current)
        candidate["pr"] = {"status": args.status, "url": args.url, "updated_at": fmt(now)}
        # An open or merged PR settles the decision; a closed-unmerged PR reopens it.
        candidate["needs_decision"] = args.status == "closed_unmerged"
        save(directory, ledger)
    return EXIT_OK, {"status": args.status, "key": candidate["key"], "needs_decision": candidate["needs_decision"]}


def attention_items(ledger):
    items = []
    for key, candidate in sorted(ledger["candidates"].items()):
        dispatch_status, pr_status = candidate["dispatch"]["status"], candidate["pr"]["status"]
        if dispatch_status in ("reserved", "uncertain", "stalled"):
            items.append({"key": key, "reason": f"dispatch {dispatch_status}"})
        if dispatch_status == "active" or pr_status == "open":
            items.append({"key": key, "reason": f"follow thread {dispatch_status}, pr {pr_status}"})
        if candidate["needs_decision"]:
            items.append({"key": key, "reason": "needs decision"})
        elif (candidate["outcome"] == "implement" and pr_status != "merged"
              and not has_active_work(candidate)):
            # Confirmed work nobody is doing (never dispatched, deferred, failed, released)
            # stays queued until dispatched, merged or re-triaged.
            items.append({"key": key, "reason": f"dispatch backlog: {dispatch_status}, "
                                                f"attempt {candidate['dispatch']['attempt']}"})
    return items


def cmd_status(args):
    directory = ledger_dir(args)
    with locked(directory):
        ledger = load(directory)
        now = current_time(args, ledger)
    runs = sorted(ledger["runs"].items(), key=lambda item: item[1]["started_at"])
    open_runs = [{"run_id": run_id, "lease_expires_at": run["lease_expires_at"],
                  "expired": now >= parse_time(run["lease_expires_at"])}
                 for run_id, run in runs if run["status"] == "open"]
    last = {"run_id": runs[-1][0], "status": runs[-1][1]["status"]} if runs else None
    return EXIT_OK, {
        "status": "ok", "open_runs": open_runs, "last_run": last, "sources": ledger["sources"],
        "coverage_gaps": ledger["gaps"], "attention": attention_items(ledger),
        "active_work": sum(has_active_work(c) for c in ledger["candidates"].values()),
        "candidates": ledger["candidates"],
    }


# -- CLI --------------------------------------------------------------------

def build_parser():
    parser = Parser(description="Durable ledger for the daily cache source watch.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    common = Parser(add_help=False)
    common.add_argument("--ledger", help="ledger directory outside any checkout (or CACHE_WATCH_LEDGER)")
    common.add_argument("--now", help="override the current UTC time (ISO 8601) for replay and tests")
    lease = Parser(add_help=False, parents=[common])
    lease.add_argument("--run", required=True)
    lease.add_argument("--token", required=True)

    def add(name, handler, parents, help_text):
        sub = commands.add_parser(name, parents=parents, help=help_text)
        sub.set_defaults(handler=handler)
        return sub

    sub = add("validate-registry", cmd_validate_registry, [], "validate sources.json")
    sub.add_argument("--registry", required=True)
    sub.add_argument("--repo-root", help="also check that affects paths exist")

    sub = add("init", cmd_init, [common], "create the ledger")
    sub.add_argument("--test-clock", action="store_true",
                     help="allow --now on this ledger; for tests and smoke runs only")
    add("status", cmd_status, [common], "summarize coverage, gaps and candidates")

    sub = add("start-run", cmd_start_run, [common], "take the run lease and compute windows")
    sub.add_argument("--registry", required=True)
    sub.add_argument("--overlap-hours", type=float, default=6)
    sub.add_argument("--max-catchup-days", type=float, default=14)
    sub.add_argument("--lease-hours", type=float, default=4)

    sub = add("record-source", cmd_record_source, [lease], "record one source check")
    sub.add_argument("--source", required=True)
    sub.add_argument("--status", required=True, choices=("checked", "failed", "partial"))
    sub.add_argument("--snapshot", help="file with the normalized cache-relevant extract")
    sub.add_argument("--items", type=int, help="number of in-window dated items examined")
    sub.add_argument("--note")

    add("finish-run", cmd_finish_run, [lease], "close the run; exit 2 when partial")

    sub = add("triage", cmd_triage, [lease], "record a relevance-gate decision")
    sub.add_argument("--key", required=True)
    sub.add_argument("--source", required=True)
    sub.add_argument("--outcome", required=True, choices=OUTCOMES)
    sub.add_argument("--reason", required=True)
    sub.add_argument("--alias", action="append", default=[])
    sub.add_argument("--evidence", action="append", default=[])
    sub.add_argument("--before")
    sub.add_argument("--after")
    sub.add_argument("--behavior", action="append", default=[], choices=BEHAVIORS)
    sub.add_argument("--reference", action="append", default=[])
    sub.add_argument("--published-at", help="source-declared publication date, verbatim (any precision)")
    sub.add_argument("--updated-at", help="source-declared update date, verbatim (any precision)")

    sub = add("reserve", cmd_reserve, [lease], "reserve an implement candidate before creating a thread")
    sub.add_argument("--key", required=True)
    sub.add_argument("--max-active", type=int, default=2)
    sub.add_argument("--max-attempts", type=int, default=2)

    reservation = Parser(add_help=False, parents=[lease])
    reservation.add_argument("--key", required=True)
    reservation.add_argument("--reservation", required=True)

    sub = add("dispatch", cmd_dispatch, [reservation], "record the created (or found) thread")
    sub.add_argument("--thread-id", required=True)
    sub.add_argument("--model", required=True)
    sub.add_argument("--effort", required=True)
    sub.add_argument("--reviewer", required=True)
    sub.add_argument("--catalog-checked-at")

    sub = add("mark-uncertain", cmd_mark_uncertain, [reservation], "thread creation outcome unknown")
    sub.add_argument("--note", required=True)
    sub.add_argument("--client-thread-id", help="pending client-side ID; never valid as --thread-id")

    sub = add("release", cmd_release, [reservation], "confirmed that no thread exists")
    sub.add_argument("--reason", required=True)

    sub = add("thread", cmd_thread, [lease], "update the child thread lifecycle")
    sub.add_argument("--key", required=True)
    sub.add_argument("--status", required=True, choices=("active", "stalled", "completed", "failed"))
    sub.add_argument("--note")

    sub = add("pr", cmd_pr, [lease], "update the pull request lifecycle")
    sub.add_argument("--key", required=True)
    sub.add_argument("--status", required=True, choices=("open", "merged", "closed_unmerged"))
    sub.add_argument("--url", required=True)
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        code, payload = args.handler(args)
    except Failure as failure:
        code, payload = failure.code, {"status": failure.status, **failure.extra}
    print(json.dumps({"ok": code == EXIT_OK, **payload}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
