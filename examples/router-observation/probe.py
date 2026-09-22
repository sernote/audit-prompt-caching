#!/usr/bin/env python3
"""Observe an unmodified router against one controlled synthetic HTTP worker."""

import argparse
import hashlib
import http.client
import json
import os
import platform
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from contextlib import ExitStack, closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


HOST = "127.0.0.1"
ENVIRONMENT = {"RUST_LOG": "vllm_router_rs=debug", "NO_PROXY": HOST, "no_proxy": HOST}


class Worker(BaseHTTPRequestHandler):
    """Synthetic worker: two terminal-marked streams and an intentional truncation."""

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        data = ({"object": "list", "data": [{"id": "mock-model", "object": "model"}]}
                if self.path == "/v1/models" else {"status": "ok", "model_path": "mock-model"})
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        mode = self.headers.get("x-lab-mode")
        self.server.records.append({
            "path": self.path, "request_id_received": self.headers.get("x-request-id"),
            "lab_mode": mode, "request_headers": list(self.headers.items()),
            "request_body": body.decode(), "worker_kind": "synthetic_http_mock", "usage": None,
        })
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.send_header("x-lab-worker", "synthetic-worker-1")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(b': keepalive\n\ndata: {"choices":[{"delta":{"role":"assistant"}}]}\n\n')
            self.wfile.flush()
            time.sleep(0.05)
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n')
            self.wfile.flush()
            time.sleep(0.05)
            if mode == "complete":
                self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # The client record retains transport failures; this worker is synthetic.


def observe_sse(response: http.client.HTTPResponse, started: float,
                now: Callable[[], float] = time.monotonic) -> dict:
    """Read only this lab's one-JSON-line SSE grammar, never a generic SDK stream."""
    record = {
        "http_status": response.status, "response_headers": response.getheaders(),
        "headers_ms": (now() - started) * 1000, "first_content_delta_ms": None,
        "eof_ms": None, "transport_eof": False, "saw_finish_reason": False,
        "saw_done": False, "stream_complete": False, "sse_lines": [], "error": None,
    }
    try:
        while raw := response.readline():
            line = raw.decode("utf-8")
            record["sse_lines"].append(line)
            data = line.rstrip("\r\n")
            if data == "data: [DONE]":
                record["saw_done"] = True
            elif data.startswith("data: "):
                for choice in json.loads(data[6:])["choices"]:
                    if choice.get("delta", {}).get("content") and record["first_content_delta_ms"] is None:
                        record["first_content_delta_ms"] = (now() - started) * 1000
                    if choice.get("finish_reason"):
                        record["saw_finish_reason"] = True
        record["transport_eof"] = True
        record["eof_ms"] = (now() - started) * 1000
    except (OSError, http.client.HTTPException, UnicodeError, ValueError, KeyError, TypeError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["stream_complete"] = (
        record["http_status"] == 200 and record["transport_eof"]
        and record["first_content_delta_ms"] is not None
        and record["saw_done"] and record["saw_finish_reason"]
    )
    return record


def reserve_ports() -> tuple[int, int]:
    """Choose distinct ephemeral ports; the router must bind them after release."""
    with socket.socket() as router, socket.socket() as metrics:
        router.bind((HOST, 0))
        metrics.bind((HOST, 0))
        return router.getsockname()[1], metrics.getsockname()[1]


def wait_for_router(child: subprocess.Popen, port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError("router exited during startup; inspect router.log")
        try:
            with socket.create_connection((HOST, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError("router did not listen within 15 seconds")


def stop_router(child: subprocess.Popen) -> None:
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=3)


def run_lab(binary: Path, output: Path, revision: str) -> dict:
    """Run only loopback traffic and preserve partial evidence after runtime errors."""
    output.mkdir(parents=True, exist_ok=False)
    clients, workers, metrics = [], [], b""
    manifest = {
        "status": "error", "error": None, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_kind": "unmodified_router_with_one_synthetic_http_worker",
        "router_revision": revision, "router_revision_provenance": "operator_supplied_not_verified_by_probe",
        "binary_sha256": None, "command": [], "child_environment_overrides": ENVIRONMENT,
        "python": sys.version, "platform": platform.platform(),
        "request_id_source": "client_generated_x-request-id", "actual_engine_usage": None,
        "timing_scope": "client_arrival_of_synthetic_content_not_GPU_or_engine_TTFT",
        "router_log_source": "native_unmodified_router", "worker_source": "synthetic_http_mock",
        "otel_enabled": False, "normalized_export_created": False,
    }
    try:
        with ExitStack() as stack:
            log = stack.enter_context((output / "router.log").open("wb"))
            digest = hashlib.sha256()
            with binary.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            manifest["binary_sha256"] = digest.hexdigest()
            worker = ThreadingHTTPServer((HOST, 0), Worker)
            worker.records = workers
            stack.callback(worker.server_close)
            Thread(target=worker.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
            stack.callback(worker.shutdown)
            router_port, metrics_port = reserve_ports()
            command = [
                str(binary), "--host", HOST, "--port", str(router_port),
                "--worker-urls", f"http://{HOST}:{worker.server_port}", "--policy", "cache_aware",
                "--log-level", "debug", "--prometheus-host", HOST, "--prometheus-port", str(metrics_port),
                "--disable-retries", "--request-timeout-secs", "10",
                "--worker-startup-timeout-secs", "15", "--worker-startup-check-interval", "1",
            ]
            manifest["command"] = command
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                     env={**os.environ, **ENVIRONMENT})
            stack.callback(stop_router, child)
            wait_for_router(child, router_port)
            body = json.dumps({"model": "mock-model", "stream": True, "max_tokens": 2,
                               "messages": [{"role": "user", "content": "A stable synthetic prompt. " * 20}]})
            for mode in ("complete", "complete", "truncated"):
                headers = {"Content-Type": "application/json", "x-request-id": f"lab-{uuid.uuid4().hex}",
                           "x-lab-mode": mode}
                record = {"request_id": headers["x-request-id"], "lab_mode": mode,
                          "request_body": body, "request_headers": headers, "stream_complete": False}
                clients.append(record)
                with closing(http.client.HTTPConnection(HOST, router_port, timeout=10)) as conn:
                    started = time.monotonic()
                    conn.request("POST", "/v1/chat/completions", body, headers)
                    record.update(observe_sse(conn.getresponse(), started))
            with closing(http.client.HTTPConnection(HOST, metrics_port, timeout=5)) as conn:
                conn.request("GET", "/metrics")
                response = conn.getresponse()
                metrics = response.read()
                manifest["metrics_http_status"] = response.status
                if response.status != 200:
                    raise RuntimeError(f"metrics returned HTTP {response.status}")
            if ([r["stream_complete"] for r in clients] != [True, True, False]
                or any(r["http_status"] != 200 or r["error"] or not r["transport_eof"] for r in clients)
                or clients[2]["first_content_delta_ms"] is None
                or clients[2]["saw_done"] or clients[2]["saw_finish_reason"]):
                raise RuntimeError("did not observe the expected two complete streams and one truncation")
            manifest["status"] = "complete"
    except (Exception, KeyboardInterrupt) as exc:
        manifest.update(status="error", error=f"{type(exc).__name__}: {exc}")
        if clients and "error" not in clients[-1]:
            clients[-1]["error"] = manifest["error"]
    finally:
        manifest_path = output / "manifest.json"
        try:
            for name, value in (("client", clients), ("worker", workers)):
                (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            (output / "metrics.txt").write_bytes(metrics)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            error = f"artifact persistence failed: {type(exc).__name__}: {exc}"
            manifest.update(status="error", error=f"{manifest['error']}; {error}" if manifest["error"] else error)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router-binary", required=True, type=Path)
    parser.add_argument("--router-revision", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("output directory already exists; choose a new directory")
    if not args.router_binary.is_file():
        parser.error("router binary must be an existing file")
    if not args.router_revision.strip():
        parser.error("router revision must be explicitly supplied and nonempty")
    try:
        result = run_lab(args.router_binary.resolve(), args.output_dir.resolve(), args.router_revision)
    except OSError as exc:
        parser.exit(1, f"error: {exc}\n")
    print(json.dumps({"status": result["status"], "error": result["error"], "output_dir": str(args.output_dir)}))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
