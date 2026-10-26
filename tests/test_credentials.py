import os
from pathlib import Path

import pytest

from openai_academy_api.credentials import collector_api_key, collector_client, key_fingerprint


def test_explicit_file_overrides_only_key_without_evaluating_other_assignments(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-test-value")
    path = tmp_path / ".env"
    path.write_text(
        'export OPENAI_API_KEY="explicit-test-value" # comment\n'
        'OPENAI_BASE_URL="https://evil.example"\n'
        "UNRELATED=$(touch never-execute)\n"
    )
    assert collector_api_key(path) == "explicit-test-value"
    assert os.environ["OPENAI_API_KEY"] == "ambient-test-value"
    assert key_fingerprint("explicit-test-value") != key_fingerprint("ambient-test-value")
    assert not (tmp_path / "never-execute").exists()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "OPENAI_API_KEY=\n",
        "OPENAI_API_KEY=a\nOPENAI_API_KEY=b\n",
        "OPENAI_API_KEY=$OTHER\n",
        "OPENAI_API_KEY=$(cat secret)\n",
        'OPENAI_API_KEY="unterminated',
    ],
)
def test_invalid_explicit_file_never_falls_back_to_ambient(tmp_path, monkeypatch, text):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-test-value")
    path = tmp_path / ".env"
    path.write_text(text)
    with pytest.raises(ValueError):
        collector_api_key(path)


def test_no_implicit_env_file_loading(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text("OPENAI_API_KEY=must-not-be-read\n")
    with pytest.raises(ValueError):
        collector_api_key()


def test_client_ignores_ambient_routing_auth_and_custom_headers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "wrong-ambient-key")
    monkeypatch.setenv("OPENAI_ORG_ID", "unrelated-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "unrelated-project")
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "unrelated-admin")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://evil.example")
    monkeypatch.setenv(
        "OPENAI_CUSTOM_HEADERS", "Authorization: Bearer unrelated\nX-Private: hidden"
    )
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    original = os.environ
    with collector_client("explicit-test-key") as client:
        assert client.api_key == "explicit-test-key"
        assert str(client.base_url) == "https://api.openai.com/v1/"
        assert client.organization is None and client.project is None
        assert not client.admin_api_key
        assert "X-Private" not in client.default_headers
        assert client.auth_headers["Authorization"] == "Bearer explicit-test-key"
        assert client.max_retries == 0
        assert client._client._trust_env is False
    assert os.environ is original
    assert os.environ["OPENAI_API_KEY"] == "wrong-ambient-key"


def test_env_template_has_exactly_the_collector_key_assignment(tmp_path):
    template = Path(".env.template").read_text()
    private = tmp_path / ".env"
    private.write_text(template.replace("OPENAI_API_KEY=\n", "OPENAI_API_KEY=fixture-value\n"))
    assert collector_api_key(private) == "fixture-value"
