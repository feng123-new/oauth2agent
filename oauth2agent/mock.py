from __future__ import annotations

import base64
import json
import tempfile
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ed25519

from .core import (
    OAuthMaterial,
    build_agent_assertion,
    check_conversation_isolation,
    convert_oauth_to_agent_identity,
    identity_from_document,
    verify_responses,
    write_identity_file,
)


@dataclass(frozen=True)
class SimulationReport:
    email: str | None
    plan_type: str
    runtime_id: str
    task_id: str
    output_file: str
    response_text: str
    isolation_status: int


class _State:
    def __init__(self) -> None:
        self.public_key: ed25519.Ed25519PublicKey | None = None
        self.runtime_id = "agent-demo-runtime"
        self.task_id = "task-demo-run"
        self.account_id = "account-demo"


def _ssh_ed25519_to_public_key(value: str) -> ed25519.Ed25519PublicKey:
    parts = value.strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("invalid SSH Ed25519 public key")
    blob = base64.b64decode(parts[1])
    pos = 0

    def read_string() -> bytes:
        nonlocal pos
        length = int.from_bytes(blob[pos : pos + 4], "big")
        pos += 4
        chunk = blob[pos : pos + length]
        pos += length
        return chunk

    if read_string() != b"ssh-ed25519":
        raise ValueError("wrong key algorithm")
    raw = read_string()
    return ed25519.Ed25519PublicKey.from_public_bytes(raw)


def _decode_assertion(value: str) -> dict[str, str]:
    scheme, encoded = value.split(" ", 1)
    if scheme != "AgentAssertion":
        raise ValueError("wrong auth scheme")
    payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("assertion is not an object")
    return data


def _verify_assertion(state: _State, header: str) -> None:
    assert state.public_key is not None
    data = _decode_assertion(header)
    if data.get("agent_runtime_id") != state.runtime_id or data.get("task_id") != state.task_id:
        raise ValueError("wrong runtime/task")
    payload = f"{data['agent_runtime_id']}:{data['task_id']}:{data['timestamp']}".encode()
    state.public_key.verify(base64.b64decode(data["signature"]), payload)


def _handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/accounts/v1/agent/register":
                if not self.headers.get("Authorization", "").startswith("Bearer "):
                    self._json(401, {"error": "missing bearer"})
                    return
                state.public_key = _ssh_ed25519_to_public_key(body["agent_public_key"])
                self._json(200, {"agent_runtime_id": state.runtime_id})
                return
            if self.path == f"/api/accounts/v1/agent/{state.runtime_id}/task/register":
                assert state.public_key is not None
                payload = f"{state.runtime_id}:{body['timestamp']}".encode()
                state.public_key.verify(base64.b64decode(body["signature"]), payload)
                self._json(200, {"task_id": state.task_id})
                return
            if self.path == "/backend-api/codex/responses":
                try:
                    _verify_assertion(state, self.headers.get("Authorization", ""))
                except Exception as exc:
                    self._json(401, {"error": str(exc)})
                    return
                raw = b'data: {"type":"response.output_text.delta","delta":"OK"}\n\ndata: [DONE]\n\n'
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self._json(404, {"error": "not found"})

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/backend-api/conversations"):
                try:
                    _verify_assertion(state, self.headers.get("Authorization", ""))
                except Exception:
                    self._json(401, {"error": "invalid auth"})
                    return
                self._json(403, {"error": "forbidden"})
                return
            self._json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def run_simulation(output_dir: str | None = None) -> SimulationReport:
    state = _State()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"

    try:
        oauth = OAuthMaterial(
            access_token="demo-access-token-never-written",
            account_id=state.account_id,
            chatgpt_user_id="user-demo",
            email="demo@example.invalid",
            plan_type="pro",
            chatgpt_account_is_fedramp=False,
        )
        identity = convert_oauth_to_agent_identity(oauth, auth_api_base=f"{base}/api/accounts")

        root = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="oauth2agent-sim-"))
        root.mkdir(parents=True, exist_ok=True)
        output = root / "agent.json"
        write_identity_file(output, identity, output_format="sub2api")
        raw = output.read_text(encoding="utf-8")
        assert "demo-access-token-never-written" not in raw
        assert "access_token" not in raw
        assert "refresh_token" not in raw
        loaded = identity_from_document(json.loads(raw))
        assert loaded == identity

        assertion = build_agent_assertion(identity, timestamp="2026-08-12T00:00:00Z")
        _verify_assertion(state, assertion)
        response_text = verify_responses(identity, codex_base=f"{base}/backend-api/codex")
        isolation_status = check_conversation_isolation(identity, codex_base=f"{base}/backend-api/codex")

        return SimulationReport(
            email=identity.email,
            plan_type=identity.plan_type,
            runtime_id=identity.agent_runtime_id,
            task_id=identity.task_id,
            output_file=str(output),
            response_text=response_text,
            isolation_status=isolation_status,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
