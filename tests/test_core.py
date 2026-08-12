import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization

from oauth2agent.core import (
    AgentIdentity,
    OAuth2AgentError,
    build_agent_assertion,
    generate_key_material,
    identity_from_document,
    parse_oauth_document,
)


def _jwt(payload: dict) -> str:
    enc = lambda obj: base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{enc({'alg':'none'})}.{enc(payload)}.sig"


def test_parse_nested_oauth_document():
    id_token = _jwt({
        "email": "user@example.com",
        "https://api.openai.com/auth": {
            "chatgpt_account_id": "account-1",
            "chatgpt_user_id": "user-1",
            "chatgpt_plan_type": "pro",
        },
    })
    doc = {"tokens": {"access_token": "access", "id_token": id_token, "refresh_token": "refresh"}}
    oauth = parse_oauth_document(doc)
    assert oauth.access_token == "access"
    assert oauth.account_id == "account-1"
    assert oauth.chatgpt_user_id == "user-1"
    assert oauth.plan_type == "pro"


def test_identity_output_does_not_contain_oauth_tokens():
    key = generate_key_material()
    identity = AgentIdentity(
        agent_runtime_id="agent-1",
        agent_private_key=key.private_key_pkcs8_base64,
        task_id="task-1",
        account_id="account-1",
        chatgpt_user_id="user-1",
        email="user@example.com",
        plan_type="pro",
        chatgpt_account_is_fedramp=False,
    )
    doc = identity.to_sub2api_document()
    raw = json.dumps(doc)
    assert "access_token" not in raw
    assert "refresh_token" not in raw
    assert identity_from_document(doc) == identity


def test_agent_assertion_contains_signed_envelope():
    key = generate_key_material()
    identity = AgentIdentity(
        agent_runtime_id="agent-1",
        agent_private_key=key.private_key_pkcs8_base64,
        task_id="task-1",
        account_id="account-1",
        chatgpt_user_id="user-1",
        email=None,
        plan_type="pro",
        chatgpt_account_is_fedramp=False,
    )
    header = build_agent_assertion(identity, timestamp="2026-08-12T00:00:00Z")
    assert header.startswith("AgentAssertion ")


def test_parse_oauth_requires_access_token():
    with pytest.raises(OAuth2AgentError):
        parse_oauth_document({"tokens": {"id_token": "x.y.z"}})


def test_parse_oauth_rejects_multiple_accounts():
    with pytest.raises(OAuth2AgentError, match="multiple distinct access_token"):
        parse_oauth_document({
            "accounts": [
                {"access_token": "access-a"},
                {"access_token": "access-b"},
            ]
        })


def test_decrypt_encrypted_task_id_when_pynacl_available():
    nacl = pytest.importorskip("nacl.bindings")
    from oauth2agent.core import _decrypt_task_id

    key = generate_key_material()
    private_raw = key.private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    ed_public, _ed_secret = nacl.crypto_sign_seed_keypair(private_raw)
    curve_public = nacl.crypto_sign_ed25519_pk_to_curve25519(ed_public)
    encrypted = nacl.crypto_box_seal(b"task-encrypted", curve_public)
    encoded = base64.b64encode(encrypted).decode("ascii")
    assert _decrypt_task_id(key.private_key, encoded) == "task-encrypted"
