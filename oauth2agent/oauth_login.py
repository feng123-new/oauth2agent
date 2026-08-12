from __future__ import annotations

import hashlib
import secrets
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from .core import OAuth2AgentError, OAuthMaterial, parse_oauth_document, _b64url_encode, _expect_json_success

DEFAULT_ISSUER = "https://auth.openai.com"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_SCOPES = "openid profile email offline_access api.connectors.read api.connectors.invoke"


@dataclass(frozen=True)
class PKCEPair:
    verifier: str
    challenge: str


def generate_pkce() -> PKCEPair:
    verifier = _b64url_encode(secrets.token_bytes(64))
    challenge = _b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())
    return PKCEPair(verifier=verifier, challenge=challenge)


def build_authorize_url(
    *,
    issuer: str,
    redirect_uri: str,
    state: str,
    challenge: str,
) -> str:
    query = {
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": OAUTH_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": "codex_cli_rs",
    }
    return f"{issuer.rstrip('/')}/oauth/authorize?{urlencode(query)}"


def parse_callback_url(callback_url: str, expected_state: str) -> str:
    parsed = urlparse(callback_url.strip())
    params = parse_qs(parsed.query)
    actual_state = params.get("state", [None])[0]
    if not secrets.compare_digest(actual_state or "", expected_state):
        raise OAuth2AgentError("OAuth callback state mismatch")
    error = params.get("error", [None])[0]
    if error:
        detail = params.get("error_description", [""])[0]
        raise OAuth2AgentError(f"OAuth authorization failed: {error}: {detail}")
    code = params.get("code", [None])[0]
    if not code:
        raise OAuth2AgentError("OAuth callback does not contain code")
    return code


def receive_callback(port: int, expected_state: str) -> str:
    result: dict[str, str | Exception] = {}
    completed = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            try:
                if urlparse(self.path).path != "/auth/callback":
                    self.send_error(404)
                    return
                callback = f"http://localhost:{port}{self.path}"
                result["code"] = parse_callback_url(callback, expected_state)
                body = "Agent Identity authorization completed. You can close this page.".encode("utf-8")
                self.send_response(200)
            except Exception as exc:  # pragma: no cover - network/UI path
                result["error"] = exc
                body = "Authorization failed. Return to the terminal for details.".encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            completed.set()

        def log_message(self, format: str, *args: object) -> None:
            return

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise OAuth2AgentError(f"unable to listen on 127.0.0.1:{port}: {exc}") from exc

    server.timeout = 1
    try:
        while not completed.is_set():
            server.handle_request()
    except KeyboardInterrupt as exc:  # pragma: no cover - interactive path
        raise OAuth2AgentError("OAuth login cancelled") from exc
    finally:
        server.server_close()

    if "error" in result:
        raise OAuth2AgentError(str(result["error"]))
    return str(result["code"])


def exchange_code(
    *,
    issuer: str,
    code: str,
    redirect_uri: str,
    verifier: str,
) -> dict[str, Any]:
    return _expect_json_success(
        "POST",
        f"{issuer.rstrip('/')}/oauth/token",
        form_body={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": OAUTH_CLIENT_ID,
            "code_verifier": verifier,
        },
    )


def interactive_oauth(
    *,
    issuer: str = DEFAULT_ISSUER,
    port: int = 1455,
    manual: bool = False,
    open_browser: bool = True,
) -> OAuthMaterial:
    redirect_uri = f"http://localhost:{port}/auth/callback"
    pkce = generate_pkce()
    state = secrets.token_urlsafe(32)
    auth_url = build_authorize_url(
        issuer=issuer,
        redirect_uri=redirect_uri,
        state=state,
        challenge=pkce.challenge,
    )

    print("Open this ChatGPT OAuth URL:\n")
    print(auth_url)
    print()
    if open_browser:
        webbrowser.open(auth_url)

    if manual:
        callback_url = input("Paste the full callback URL: ").strip()
        code = parse_callback_url(callback_url, state)
    else:
        print(f"Waiting for callback on {redirect_uri} ...")
        code = receive_callback(port, state)

    token_document = exchange_code(
        issuer=issuer,
        code=code,
        redirect_uri=redirect_uri,
        verifier=pkce.verifier,
    )
    return parse_oauth_document(token_document)
