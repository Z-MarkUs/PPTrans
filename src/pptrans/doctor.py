"""Read-only diagnostics for local PPTrans capabilities."""

from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from pptrans.adapters.renderers.libreoffice import LibreOfficeRenderer

CheckStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True, slots=True, kw_only=True)
class DoctorCheck:
    """One redaction-safe capability diagnostic."""

    name: str
    status: CheckStatus
    detail: str
    required: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _package_check(distribution: str, *, required: bool = True) -> DoctorCheck:
    try:
        installed = version(distribution)
    except PackageNotFoundError:
        return DoctorCheck(
            name=distribution,
            status="fail" if required else "warn",
            detail="not installed",
            required=required,
        )
    return DoctorCheck(name=distribution, status="pass", detail=installed, required=required)


def run_doctor(provider: str | None = None) -> tuple[DoctorCheck, ...]:
    """Inspect dependencies, credentials, and optional rendering without network calls."""

    python_ok = sys.version_info >= (3, 10)
    checks = [
        DoctorCheck(
            name="python",
            status="pass" if python_ok else "fail",
            detail=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            required=True,
        ),
        _package_check("lxml"),
        _package_check("python-pptx", required=False),
    ]

    if provider in {"openai", "anthropic"}:
        variable = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        configured = bool((os.getenv(variable) or "").strip())
        checks.append(
            DoctorCheck(
                name=f"{provider}_credential",
                status="pass" if configured else "fail",
                detail=f"{variable} is set" if configured else f"{variable} is not set",
                required=True,
            )
        )

    availability = LibreOfficeRenderer().availability()
    checks.append(
        DoctorCheck(
            name="libreoffice_review",
            status="pass" if availability.available else "warn",
            detail=availability.reason,
            required=False,
        )
    )
    return tuple(checks)


__all__ = ["DoctorCheck", "run_doctor"]
