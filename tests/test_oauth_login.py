from urllib.parse import parse_qs, urlparse

import pytest

from oauth2agent.core import OAuth2AgentError
from oauth2agent.oauth_login import build_authorize_url, generate_pkce, parse_callback_url


def test_pkce_and_authorize_url():
    pair = generate_pkce()
    assert pair.verifier
    assert pair.challenge
    url = build_authorize_url(
        issuer="https://auth.openai.com",
        redirect_uri="http://localhost:1455/auth/callback",
        state="state-1",
        challenge=pair.challenge,
    )
    params = parse_qs(urlparse(url).query)
    assert params["state"] == ["state-1"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["originator"] == ["codex_cli_rs"]


def test_callback_state_validation():
    url = "http://localhost:1455/auth/callback?code=abc&state=good"
    assert parse_callback_url(url, "good") == "abc"
    with pytest.raises(OAuth2AgentError):
        parse_callback_url(url, "bad")
