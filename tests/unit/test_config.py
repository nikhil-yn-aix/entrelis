"""settings read env names and fall back to defaults."""

from pathlib import Path

import pytest

from entrelis.config import Settings

PASSWORD_VARS = ("FALKORDB_PASSWORD", "FALKORDB_RW_PASSWORD", "FALKORDB_RO_PASSWORD")
OPTIONAL_VARS = ("ENTRELIS_FALKORDB_URL", "ENTRELIS_OTEL_ENDPOINT")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in (*PASSWORD_VARS, *OPTIONAL_VARS):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_defaults_apply_when_nothing_is_set() -> None:
    settings = Settings()
    assert settings.falkordb_url == "redis://localhost:6379"
    assert settings.otel_endpoint == "http://localhost:4318"
    assert settings.falkordb_rw_password.get_secret_value() == ""


def test_env_names_fill_every_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTRELIS_FALKORDB_URL", "redis://graph.internal:6390")
    monkeypatch.setenv("ENTRELIS_OTEL_ENDPOINT", "http://jaeger.internal:4318")
    monkeypatch.setenv("FALKORDB_PASSWORD", "admin-pw")
    monkeypatch.setenv("FALKORDB_RW_PASSWORD", "rw-pw")
    monkeypatch.setenv("FALKORDB_RO_PASSWORD", "ro-pw")
    settings = Settings()
    assert settings.falkordb_url == "redis://graph.internal:6390"
    assert settings.otel_endpoint == "http://jaeger.internal:4318"
    assert settings.falkordb_password.get_secret_value() == "admin-pw"
    assert settings.falkordb_rw_password.get_secret_value() == "rw-pw"
    assert settings.falkordb_ro_password.get_secret_value() == "ro-pw"


def test_secrets_are_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PASSWORD_VARS:
        monkeypatch.setenv(name, "hunter2-" + name.lower())
    assert "hunter2" not in repr(Settings())


def test_empty_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PASSWORD_VARS:
        monkeypatch.setenv(name, "pw")
    monkeypatch.setenv("ENTRELIS_FALKORDB_URL", "")
    assert Settings().falkordb_url == "redis://localhost:6379"


def test_dotenv_file_is_read_and_unknown_keys_are_ignored(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "FALKORDB_PASSWORD=a\nFALKORDB_RW_PASSWORD=b\nFALKORDB_RO_PASSWORD=c\n"
        "SLACK_BOT_TOKEN=xoxb-unused\n"
    )
    assert Settings().falkordb_rw_password.get_secret_value() == "b"
