"""Deterministic tests for configuration and read-only local diagnostics."""

from __future__ import annotations

import json
import os
from collections import namedtuple
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from pptrans import cli, config, doctor
from pptrans.doctor import DoctorCheck


class _Renderer:
    def __init__(self, *, available: bool = False, reason: str = "not configured") -> None:
        self._availability = SimpleNamespace(available=available, reason=reason)

    def availability(self) -> SimpleNamespace:
        return self._availability


def _fixed_version(distribution: str) -> str:
    return {
        "anthropic": "0.40.0",
        "lxml": "5.3.1",
        "openai": "2.0.0",
        "python-pptx": "1.0.2",
    }[distribution]


def test_doctor_check_serializes_all_fields_without_secrets() -> None:
    check = DoctorCheck(
        name="openai_credential",
        status="pass",
        detail="OPENAI_API_KEY is set",
        required=True,
    )

    assert check.as_dict() == {
        "name": "openai_credential",
        "status": "pass",
        "detail": "OPENAI_API_KEY is set",
        "required": True,
    }


@pytest.mark.parametrize(
    ("provider", "environment_name"),
    [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")],
)
def test_run_doctor_checks_credentials_without_network_or_secret_disclosure(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    environment_name: str,
) -> None:
    credential_value = "opaque-test-value"
    monkeypatch.setattr(doctor, "version", _fixed_version)
    monkeypatch.setattr(doctor, "LibreOfficeRenderer", _Renderer)
    monkeypatch.setenv(environment_name, credential_value)

    checks = doctor.run_doctor(provider)

    by_name = {check.name: check for check in checks}
    assert by_name["python"].status == "pass"
    assert by_name["lxml"].status == "pass"
    assert by_name["python-pptx"].status == "pass"
    assert by_name["python-pptx"].required is False
    assert by_name[provider].status == "pass"
    assert by_name[provider].required is True
    assert by_name[f"{provider}_credential"].status == "pass"
    assert environment_name in by_name[f"{provider}_credential"].detail
    assert credential_value not in repr(checks)
    assert by_name["libreoffice_review"] == DoctorCheck(
        name="libreoffice_review",
        status="warn",
        detail="not configured",
        required=False,
    )


@pytest.mark.parametrize(
    ("provider", "environment_name"),
    [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")],
)
def test_run_doctor_treats_blank_credentials_as_missing(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    environment_name: str,
) -> None:
    monkeypatch.setattr(doctor, "version", _fixed_version)
    monkeypatch.setattr(doctor, "LibreOfficeRenderer", _Renderer)
    monkeypatch.setenv(environment_name, " \t ")

    checks = doctor.run_doctor(provider)

    credential = next(check for check in checks if check.name == f"{provider}_credential")
    assert credential.status == "fail"
    assert credential.required is True
    assert credential.detail == f"{environment_name} is not set"


@pytest.mark.parametrize(
    "python_version",
    [(3, 9, 19, "final", 0), (3, 14, 0, "final", 0)],
    ids=["below-supported-range", "above-supported-range"],
)
def test_run_doctor_marks_missing_requirements_and_unsupported_python(
    monkeypatch: pytest.MonkeyPatch,
    python_version: tuple[int, int, int, str, int],
) -> None:
    VersionInfo = namedtuple(
        "VersionInfo",
        ["major", "minor", "micro", "releaselevel", "serial"],
    )

    def missing(_distribution: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(doctor.sys, "version_info", VersionInfo(*python_version))
    monkeypatch.setattr(doctor, "version", missing)
    monkeypatch.setattr(doctor, "LibreOfficeRenderer", _Renderer)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    checks = doctor.run_doctor("openai")

    by_name = {check.name: check for check in checks}
    assert by_name["python"].status == "fail"
    assert by_name["python"].required is True
    assert by_name["lxml"].status == "fail"
    assert by_name["python-pptx"].status == "warn"
    assert by_name["python-pptx"].required is False
    assert by_name["openai"].status == "fail"
    assert by_name["openai"].required is True
    assert by_name["openai_credential"].status == "fail"
    assert by_name["openai_credential"].detail == "OPENAI_API_KEY is not set"
    assert by_name["libreoffice_review"].status == "warn"
    assert by_name["libreoffice_review"].required is False


def test_run_doctor_reports_available_renderer_as_optional_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "version", _fixed_version)
    monkeypatch.setattr(
        doctor,
        "LibreOfficeRenderer",
        lambda: _Renderer(available=True, reason="LibreOffice 25.2"),
    )

    checks = doctor.run_doctor()

    renderer = next(check for check in checks if check.name == "libreoffice_review")
    assert renderer.status == "pass"
    assert renderer.required is False
    assert all("credential" not in check.name for check in checks)


def test_run_doctor_rejects_an_untested_python_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor.sys, "implementation", SimpleNamespace(name="pypy"))
    monkeypatch.setattr(doctor, "version", _fixed_version)
    monkeypatch.setattr(doctor, "LibreOfficeRenderer", _Renderer)

    checks = doctor.run_doctor()

    python = next(check for check in checks if check.name == "python")
    assert python.status == "fail"
    assert python.required is True
    assert python.detail.startswith("pypy ")


def test_doctor_json_returns_zero_for_passes_and_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = (
        DoctorCheck(name="python", status="pass", detail="3.12.0", required=True),
        DoctorCheck(name="renderer", status="warn", detail="optional", required=False),
    )
    monkeypatch.setattr(cli, "load_environment", lambda _path: False)
    monkeypatch.setattr(cli, "run_doctor", lambda _provider: checks)

    result = CliRunner().invoke(cli.app, ["doctor", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [check.as_dict() for check in checks]


def test_doctor_json_emits_results_then_returns_one_for_required_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = (
        DoctorCheck(name="python", status="pass", detail="3.12.0", required=True),
        DoctorCheck(name="credential", status="fail", detail="not set", required=True),
    )
    monkeypatch.setattr(cli, "load_environment", lambda _path: False)
    monkeypatch.setattr(cli, "run_doctor", lambda _provider: checks)

    result = CliRunner().invoke(cli.app, ["doctor", "--provider", "openai", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == [check.as_dict() for check in checks]


def test_doctor_human_output_distinguishes_optional_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = (
        DoctorCheck(name="python", status="pass", detail="3.12.0", required=True),
        DoctorCheck(name="renderer", status="warn", detail="not installed", required=False),
    )
    monkeypatch.setattr(cli, "load_environment", lambda _path: False)
    monkeypatch.setattr(cli, "run_doctor", lambda _provider: checks)

    result = CliRunner().invoke(cli.app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "Required" in result.output
    assert "yes" in result.output
    assert "no" in result.output


def test_explicit_dotenv_preserves_exported_values_and_loads_missing_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "pptrans.env"
    env_file.write_text(
        "PPTRANS_TEST_PRECEDENCE=from-file\nPPTRANS_TEST_LOADED=loaded-from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PPTRANS_TEST_PRECEDENCE", "from-process")
    monkeypatch.delenv("PPTRANS_TEST_LOADED", raising=False)

    loaded = config.load_environment(env_file)

    assert loaded is True
    assert os.getenv("PPTRANS_TEST_PRECEDENCE") == "from-process"
    assert os.getenv("PPTRANS_TEST_LOADED") == "loaded-from-file"


def test_missing_explicit_dotenv_is_an_actionable_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.env"

    with pytest.raises(FileNotFoundError, match="Environment file does not exist"):
        config.load_environment(missing)


def test_no_dotenv_file_is_discovered_implicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def record_load(**kwargs: object) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr(config, "load_dotenv", record_load)

    assert config.load_environment() is False
    assert calls == []


def test_default_memory_path_uses_platform_cache_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_cache(app_name: str, app_author: str) -> Path:
        calls.append((app_name, app_author))
        return tmp_path / "cache-root"

    monkeypatch.setattr(config, "user_cache_path", fake_cache)

    result = config.default_memory_path()

    assert calls == [("pptrans", "Z-MarkUs")]
    assert result == tmp_path / "cache-root" / "translation-memory-v2.sqlite3"
