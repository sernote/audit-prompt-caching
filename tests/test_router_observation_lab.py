"""Offline checks for the controlled HTTP observation lab; no Rust or sockets."""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


PROBE = Path(__file__).resolve().parents[1] / "examples/router-observation/probe.py"
SPEC = importlib.util.spec_from_file_location("router_observation_probe", PROBE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
CONTENT = b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n'
FINISH = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'


class Response:
    def __init__(self, events, status=200):
        self.events, self.status, self.at = iter(events), status, 1

    def getheaders(self):
        return [("Content-Type", "text/event-stream")]

    def readline(self):
        self.at, value = next(self.events, (9, b""))
        if isinstance(value, Exception):
            raise value
        return value


@contextmanager
def fake_runtime(error=None):
    child, server = Mock(), Mock(server_port=8123)
    child.poll.return_value = None
    with patch.object(probe, "ThreadingHTTPServer", return_value=server), \
         patch.object(probe, "Thread"), \
         patch.object(probe, "reserve_ports", return_value=(8124, 8125)), \
         patch.object(probe, "wait_for_router", side_effect=error), \
         patch("platform.platform", return_value="offline-test"), \
         patch("subprocess.Popen", return_value=child) as launch, redirect_stdout(io.StringIO()):
        yield child, server, launch


class RouterObservationTest(unittest.TestCase):
    def observe(self, events, status=200):
        response = Response(events, status)
        return probe.observe_sse(response, 0, now=lambda: response.at)

    def test_first_content_ignores_heartbeat_role_and_empty_delta(self):
        record = self.observe([
            (2, b": keepalive\n"),
            (3, b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n'),
            (4, b'data: {"choices":[{"delta":{"content":""}}]}\n'),
            (5, CONTENT), (6, FINISH), (7, b"data: [DONE]\n"),
        ])
        self.assertEqual(record["headers_ms"], 1000)
        self.assertEqual(record["first_content_delta_ms"], 5000)
        self.assertEqual(record["eof_ms"], 9000)
        self.assertTrue(record["stream_complete"])

    def test_http_200_eof_without_both_terminal_markers_is_not_complete(self):
        for ending in ([], [(6, FINISH)], [(6, b"data: [DONE]\n")]):
            with self.subTest(ending=ending):
                record = self.observe([(5, CONTENT), *ending])
                self.assertTrue(record["transport_eof"])
                self.assertFalse(record["stream_complete"])

    def test_http_error_is_not_complete_even_with_terminal_markers(self):
        record = self.observe([(5, CONTENT), (6, FINISH), (7, b"data: [DONE]\n")], 503)
        self.assertFalse(record["stream_complete"])

    def test_read_error_preserves_partial_content_without_claiming_eof(self):
        record = self.observe([(5, CONTENT), (6, TimeoutError("stream stalled"))])
        self.assertFalse(record["stream_complete"])
        self.assertFalse(record["transport_eof"])
        self.assertIsNone(record["eof_ms"])
        self.assertEqual(record["sse_lines"], [CONTENT.decode()])
        self.assertIn("stream stalled", record["error"])

    def test_runtime_error_preserves_artifacts_and_cleans_up_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            with fake_runtime(RuntimeError("startup failed")) as (child, server, _):
                code = probe.main([
                    "--router-binary", sys.executable, "--router-revision", "operator-supplied",
                    "--output-dir", str(output),
                ])
            self.assertEqual(code, 1)
            self.assertTrue((output / "manifest.json").is_file(), "missing failure manifest")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "error")
            self.assertIn("startup failed", manifest["error"])
            self.assertEqual(json.loads((output / "client.json").read_text()), [])
            self.assertEqual(json.loads((output / "worker.json").read_text()), [])
            self.assertTrue((output / "router.log").is_file())
            self.assertTrue((output / "metrics.txt").is_file())
        child.terminate.assert_called_once()
        child.wait.assert_called_once()
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()

    def test_expected_sequence_preserves_requests_and_overrides_inherited_log_filter(self):
        streams = [[(5, CONTENT), (6, FINISH), (7, b"data: [DONE]\n")]] * 2 + [[(5, CONTENT)]]
        responses = [Response(events) for events in streams] + [Mock(status=200)]
        responses[-1].read.return_value = b"# synthetic metrics\n"
        connections = [Mock() for _ in responses]
        for connection, response in zip(connections, responses):
            connection.getresponse.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new"
            with fake_runtime() as (_, _, launch), \
                 patch("http.client.HTTPConnection", side_effect=connections), \
                 patch.dict(os.environ, {"RUST_LOG": "warn"}):
                code = probe.main([
                    "--router-binary", sys.executable, "--router-revision", "operator-supplied",
                    "--output-dir", str(output),
                ])
            self.assertEqual(code, 0)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(launch.call_args.kwargs["env"]["RUST_LOG"], "vllm_router_rs=debug")
            records = json.loads((output / "client.json").read_text())
            self.assertEqual([r["stream_complete"] for r in records], [True, True, False])
            requests = [c.request.call_args.args for c in connections[:3]]
            self.assertEqual(len({args[2] for args in requests}), 1, "bodies must stay identical")
            self.assertEqual([args[3]["x-lab-mode"] for args in requests], ["complete", "complete", "truncated"])
            self.assertEqual(len({args[3]["x-request-id"] for args in requests}), 3)

    def test_existing_output_is_refused_without_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "keep.txt"
            marker.write_text("keep")
            result = subprocess.run(
                [sys.executable, str(PROBE), "--router-binary", sys.executable,
                 "--router-revision", "operator-supplied", "--output-dir", directory],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output directory already exists", result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [marker])
            self.assertEqual(marker.read_text(), "keep")

    def test_metrics_write_failure_keeps_error_manifest_and_partial_artifacts(self):
        streams = [[(5, CONTENT), (6, FINISH), (7, b"data: [DONE]\n")]] * 2 + [[(5, CONTENT)]]
        responses = [Response(events) for events in streams] + [Mock(status=200)]
        responses[-1].read.return_value = b"# synthetic metrics\n"
        connections = [Mock() for _ in responses]
        for connection, response in zip(connections, responses):
            connection.getresponse.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            output, stdout = Path(directory) / "new", io.StringIO()
            with fake_runtime() as (child, server, _), \
                 patch("http.client.HTTPConnection", side_effect=connections), \
                 patch.object(Path, "write_bytes", side_effect=OSError("metrics write failed")), \
                 redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                try:
                    code = probe.main([
                        "--router-binary", sys.executable, "--router-revision", "operator-supplied",
                        "--output-dir", str(output),
                    ])
                except SystemExit as exc:
                    code = exc.code
            self.assertEqual(code, 1)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "error")
            self.assertIn("metrics write failed", manifest["error"])
            self.assertEqual(json.loads(stdout.getvalue())["status"], "error")
            self.assertEqual(len(json.loads((output / "client.json").read_text())), 3)
            self.assertTrue((output / "worker.json").is_file())
            self.assertTrue((output / "router.log").is_file())
            self.assertFalse((output / "metrics.txt").exists())
        child.terminate.assert_called_once()
        child.wait.assert_called_once()
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
