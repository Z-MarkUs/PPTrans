"""Verify that PPTrans's base install stays offline-provider independent."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable

from pptrans.adapters.providers import PaidProviderName, create_translator
from pptrans.application.errors import ProviderConfigurationError

PROVIDER_MODULES: tuple[PaidProviderName, ...] = ("anthropic", "openai")


def provider_sdk_presence_failures(
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> tuple[str, ...]:
    """Return failures for paid-provider SDKs visible in a base environment."""

    return tuple(
        f"base install unexpectedly exposes optional provider SDK: {module_name}"
        for module_name in PROVIDER_MODULES
        if find_spec(module_name) is not None
    )


def missing_sdk_failure(provider: PaidProviderName) -> str | None:
    """Return a failure when one missing-SDK path is not actionable."""

    try:
        create_translator(
            provider,
            model="offline-smoke-model",
            api_key="not-a-real-key",
        )
    except ProviderConfigurationError as exc:
        message = str(exc)
        expected = (f"pptrans[{provider}]", f".[{provider}]")
        if all(fragment in message for fragment in expected):
            return None
        return f"{provider} missing-SDK guidance is incomplete"
    except Exception as exc:  # noqa: BLE001
        return f"{provider} missing-SDK path raised unexpected {type(exc).__name__}"
    return f"{provider} initialized without its optional SDK"


def main() -> int:
    failures = list(provider_sdk_presence_failures())
    if failures:
        print("\n".join(failures))
        return 1

    identity = create_translator("identity", model=None)
    if identity.provider != "identity" or identity.model != "identity-v1":
        failures.append("identity provider did not initialize from the base install")

    failures.extend(
        failure
        for provider in PROVIDER_MODULES
        if (failure := missing_sdk_failure(provider)) is not None
    )

    if failures:
        print("\n".join(failures))
        return 1
    print("minimal install verified: identity works; paid-provider SDKs are explicit opt-ins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
