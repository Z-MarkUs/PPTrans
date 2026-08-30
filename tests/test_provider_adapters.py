"""Offline contract tests for translation provider adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from anthropic import AnthropicError
from anthropic import AuthenticationError as AnthropicAuthenticationError
from anthropic import RateLimitError as AnthropicRateLimitError
from openai import AuthenticationError as OpenAIAuthenticationError
from openai import OpenAIError
from openai import RateLimitError as OpenAIRateLimitError

from pptrans.adapters import providers
from pptrans.adapters.providers import anthropic as anthropic_adapter
from pptrans.adapters.providers import openai as openai_adapter
from pptrans.adapters.providers.anthropic import AnthropicTranslator
from pptrans.adapters.providers.identity import IdentityTranslator
from pptrans.adapters.providers.openai import OpenAITranslator
from pptrans.application.errors import (
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
)
from pptrans.domain.models import (
    ParagraphLocator,
    SpanKind,
    TextContainer,
    TextSpan,
    TranslatedSpan,
    TranslationUnit,
)
from pptrans.ports.translator import TranslationBatchRequest


def _unit() -> TranslationUnit:
    return TranslationUnit(
        id="unit-1",
        locator=ParagraphLocator(
            slide_part="ppt/slides/slide1.xml",
            slide_index=0,
            shape_id_path=(7,),
            container=TextContainer.SHAPE,
            paragraph_index=0,
        ),
        spans=(
            TextSpan(
                id="span-1",
                node_index=0,
                kind=SpanKind.TEXT,
                source="Hello",
                translatable=True,
            ),
            TextSpan(
                id="span-locked",
                node_index=1,
                kind=SpanKind.FIELD,
                source="2026",
                translatable=False,
            ),
        ),
        source_digest="digest",
    )


def _request() -> TranslationBatchRequest:
    return TranslationBatchRequest(
        units=(_unit(),),
        source_lang="en",
        target_lang="fr",
    )


def _payload(text: str = "Bonjour") -> dict[str, object]:
    return {
        "translations": [
            {
                "unit_id": "unit-1",
                "spans": [{"span_id": "span-1", "text": text}],
            }
        ]
    }


def _sdk_response(status_code: int) -> SimpleNamespace:
    return SimpleNamespace(
        status_code=status_code,
        request=SimpleNamespace(method="POST", url="https://provider.invalid/v1/translate"),
        headers={},
    )


@dataclass
class _RecordingEndpoint:
    response: object | None = None
    error: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_identity_translator_is_offline_ordered_and_excludes_locked_spans() -> None:
    result = IdentityTranslator().translate(_request())

    assert result.translations[0].unit_id == "unit-1"
    assert result.translations[0].spans == (TranslatedSpan(span_id="span-1", text="Hello"),)
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0


def test_openai_adapter_uses_responses_schema_and_disables_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = _RecordingEndpoint(
        response=SimpleNamespace(
            output_text=json.dumps(_payload("Bonjour")),
            usage=SimpleNamespace(input_tokens=41, output_tokens=17),
        )
    )
    client = SimpleNamespace(responses=endpoint)
    monkeypatch.setattr(
        openai_adapter,
        "OpenAI",
        lambda **_kwargs: pytest.fail("injected clients must prevent SDK construction"),
    )
    translator = OpenAITranslator(
        model="gpt-test",
        max_output_tokens=512,
        client=client,
    )

    result = translator.translate(_request())

    assert result.translations[0].spans[0].text == "Bonjour"
    assert result.usage.input_tokens == 41
    assert result.usage.output_tokens == 17
    assert len(endpoint.calls) == 1
    call = endpoint.calls[0]
    assert call["model"] == "gpt-test"
    assert call["max_output_tokens"] == 512
    assert call["store"] is False
    assert call["instructions"] == openai_adapter.SYSTEM_INSTRUCTIONS
    assert json.loads(call["input"])["units"][0]["unit_id"] == "unit-1"
    output_format = call["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["name"] == "pptrans_translation_batch"
    assert output_format["strict"] is True
    assert output_format["schema"]["additionalProperties"] is False


@pytest.mark.parametrize("output_text", [None, "", "   "])
def test_openai_adapter_rejects_missing_structured_output(output_text: object) -> None:
    endpoint = _RecordingEndpoint(response=SimpleNamespace(output_text=output_text, usage=None))
    translator = OpenAITranslator(model="gpt-test", client=SimpleNamespace(responses=endpoint))

    with pytest.raises(ProviderResponseError, match="no structured translation output"):
        translator.translate(_request())


@pytest.mark.parametrize(
    "output_text",
    [
        "{broken",
        json.dumps({**_payload(), "commentary": "extra"}),
        json.dumps({"translations": []}),
    ],
    ids=["malformed", "extra", "partial"],
)
def test_openai_adapter_rejects_malformed_or_extra_payload_fields(
    output_text: str,
) -> None:
    endpoint = _RecordingEndpoint(response=SimpleNamespace(output_text=output_text, usage=None))
    translator = OpenAITranslator(model="gpt-test", client=SimpleNamespace(responses=endpoint))

    if output_text == json.dumps({"translations": []}):
        assert translator.translate(_request()).translations == ()
    else:
        with pytest.raises(ProviderResponseError):
            translator.translate(_request())


def test_openai_adapter_maps_sdk_errors_without_leaking_request_details() -> None:
    endpoint = _RecordingEndpoint(error=OpenAIError("secret request body"))
    translator = OpenAITranslator(model="gpt-test", client=SimpleNamespace(responses=endpoint))

    with pytest.raises(ProviderRequestError) as raised:
        translator.translate(_request())

    assert str(raised.value) == "OpenAI translation request failed."
    assert isinstance(raised.value.__cause__, OpenAIError)
    assert "secret" not in str(raised.value)


@pytest.mark.parametrize(
    ("error_type", "status_code"),
    [(OpenAIAuthenticationError, 401), (OpenAIRateLimitError, 429)],
    ids=["authentication", "rate-limit"],
)
def test_openai_adapter_fails_closed_on_operational_sdk_errors(
    error_type: type[OpenAIError],
    status_code: int,
) -> None:
    error = error_type(
        "sensitive provider response",
        response=_sdk_response(status_code),
        body={"error": "sensitive provider response"},
    )
    endpoint = _RecordingEndpoint(error=error)
    translator = OpenAITranslator(model="gpt-test", client=SimpleNamespace(responses=endpoint))

    with pytest.raises(ProviderRequestError, match="OpenAI translation request failed") as raised:
        translator.translate(_request())

    assert raised.value.__cause__ is error
    assert "sensitive" not in str(raised.value)


def test_openai_adapter_discards_invalid_usage_values() -> None:
    endpoint = _RecordingEndpoint(
        response=SimpleNamespace(
            output_text=json.dumps(_payload()),
            usage=SimpleNamespace(input_tokens=True, output_tokens=-1),
        )
    )
    translator = OpenAITranslator(model="gpt-test", client=SimpleNamespace(responses=endpoint))

    result = translator.translate(_request())

    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None


@pytest.mark.parametrize("model", ["", "   "])
def test_openai_adapter_requires_an_explicit_nonblank_model(model: str) -> None:
    with pytest.raises(ValueError, match="explicit OpenAI model"):
        OpenAITranslator(model=model, client=SimpleNamespace(responses=object()))


def test_openai_adapter_enforces_output_budget_floor() -> None:
    with pytest.raises(ValueError, match="at least 256"):
        OpenAITranslator(
            model="gpt-test",
            max_output_tokens=255,
            client=SimpleNamespace(responses=object()),
        )


def test_openai_sdk_client_pins_the_official_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    captured_http: dict[str, object] = {}
    sentinel = SimpleNamespace(responses=object())
    http_sentinel = object()
    for variable in ("OPENAI_BASE_URL", "OPENAI_CUSTOM_HEADERS"):
        monkeypatch.delenv(variable, raising=False)

    def construct(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(openai_adapter, "OpenAI", construct)
    monkeypatch.setattr(
        openai_adapter,
        "OpenAIDefaultHttpxClient",
        lambda **kwargs: captured_http.update(kwargs) or http_sentinel,
    )

    OpenAITranslator(model="gpt-test", api_key="opaque-key", timeout=17.0)

    assert captured == {
        "api_key": "opaque-key",
        "base_url": openai_adapter.OPENAI_API_BASE_URL,
        "timeout": 17.0,
        "max_retries": 2,
        "http_client": http_sentinel,
    }
    assert captured_http == {"trust_env": False}


@pytest.mark.parametrize("variable", ["OPENAI_BASE_URL", "OPENAI_CUSTOM_HEADERS"])
def test_openai_sdk_client_rejects_ambient_routing(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    for candidate in ("OPENAI_BASE_URL", "OPENAI_CUSTOM_HEADERS"):
        monkeypatch.delenv(candidate, raising=False)
    monkeypatch.setenv(variable, "https://untrusted.invalid")
    monkeypatch.setattr(
        openai_adapter,
        "OpenAI",
        lambda **_kwargs: pytest.fail("unsafe SDK configuration must fail first"),
    )

    with pytest.raises(ProviderConfigurationError, match=variable):
        OpenAITranslator(model="gpt-test", api_key="opaque-key")


def test_anthropic_adapter_forces_exactly_one_schema_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_block = SimpleNamespace(
        type="tool_use",
        name="submit_translations",
        input=_payload("Bonjour"),
    )
    endpoint = _RecordingEndpoint(
        response=SimpleNamespace(
            content=[tool_block],
            usage=SimpleNamespace(input_tokens=35, output_tokens=12),
        )
    )
    client = SimpleNamespace(messages=endpoint)
    monkeypatch.setattr(
        anthropic_adapter,
        "Anthropic",
        lambda **_kwargs: pytest.fail("injected clients must prevent SDK construction"),
    )
    translator = AnthropicTranslator(
        model="claude-test",
        max_output_tokens=512,
        client=client,
    )

    result = translator.translate(_request())

    assert result.translations[0].spans[0].text == "Bonjour"
    assert result.usage.input_tokens == 35
    assert result.usage.output_tokens == 12
    assert len(endpoint.calls) == 1
    call = endpoint.calls[0]
    assert call["model"] == "claude-test"
    assert call["max_tokens"] == 512
    assert call["system"] == anthropic_adapter.SYSTEM_INSTRUCTIONS
    assert json.loads(call["messages"][0]["content"])["target_lang"] == "fr"
    assert call["tool_choice"] == {"type": "tool", "name": "submit_translations"}
    assert len(call["tools"]) == 1
    assert call["tools"][0]["name"] == "submit_translations"
    assert call["tools"][0]["input_schema"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "content",
    [
        None,
        [],
        [SimpleNamespace(type="text", text="Bonjour")],
        [SimpleNamespace(type="tool_use", name="wrong", input=_payload())],
        [SimpleNamespace(type="tool_use", name="submit_translations", input="not-a-dict")],
        [
            SimpleNamespace(type="tool_use", name="submit_translations", input=_payload()),
            SimpleNamespace(type="tool_use", name="submit_translations", input=_payload()),
        ],
        [
            SimpleNamespace(type="tool_use", name="submit_translations", input=_payload()),
            SimpleNamespace(type="text", text="extra commentary"),
        ],
        [
            SimpleNamespace(type="tool_use", name="submit_translations", input=_payload()),
            SimpleNamespace(type="tool_use", name="wrong", input=_payload()),
        ],
    ],
    ids=[
        "none",
        "empty",
        "text-only",
        "wrong-tool",
        "wrong-input",
        "duplicate",
        "tool-plus-text",
        "tool-plus-wrong-tool",
    ],
)
def test_anthropic_adapter_rejects_missing_or_ambiguous_tool_output(content: object) -> None:
    endpoint = _RecordingEndpoint(response=SimpleNamespace(content=content, usage=None))
    translator = AnthropicTranslator(
        model="claude-test",
        client=SimpleNamespace(messages=endpoint),
    )

    with pytest.raises(ProviderResponseError, match="exactly one structured"):
        translator.translate(_request())


def test_anthropic_adapter_rejects_extra_payload_fields() -> None:
    tool_block = SimpleNamespace(
        type="tool_use",
        name="submit_translations",
        input={**_payload(), "commentary": "extra"},
    )
    endpoint = _RecordingEndpoint(response=SimpleNamespace(content=[tool_block], usage=None))
    translator = AnthropicTranslator(
        model="claude-test",
        client=SimpleNamespace(messages=endpoint),
    )

    with pytest.raises(ProviderResponseError):
        translator.translate(_request())


def test_anthropic_adapter_maps_sdk_errors_without_leaking_request_details() -> None:
    endpoint = _RecordingEndpoint(error=AnthropicError("secret request body"))
    translator = AnthropicTranslator(
        model="claude-test",
        client=SimpleNamespace(messages=endpoint),
    )

    with pytest.raises(ProviderRequestError) as raised:
        translator.translate(_request())

    assert str(raised.value) == "Anthropic translation request failed."
    assert isinstance(raised.value.__cause__, AnthropicError)
    assert "secret" not in str(raised.value)


@pytest.mark.parametrize(
    ("error_type", "status_code"),
    [(AnthropicAuthenticationError, 401), (AnthropicRateLimitError, 429)],
    ids=["authentication", "rate-limit"],
)
def test_anthropic_adapter_fails_closed_on_operational_sdk_errors(
    error_type: type[AnthropicError],
    status_code: int,
) -> None:
    error = error_type(
        "sensitive provider response",
        response=_sdk_response(status_code),
        body={"error": "sensitive provider response"},
    )
    endpoint = _RecordingEndpoint(error=error)
    translator = AnthropicTranslator(
        model="claude-test",
        client=SimpleNamespace(messages=endpoint),
    )

    with pytest.raises(
        ProviderRequestError, match="Anthropic translation request failed"
    ) as raised:
        translator.translate(_request())

    assert raised.value.__cause__ is error
    assert "sensitive" not in str(raised.value)


def test_anthropic_adapter_discards_invalid_usage_values() -> None:
    tool_block = SimpleNamespace(
        type="tool_use",
        name="submit_translations",
        input=_payload(),
    )
    endpoint = _RecordingEndpoint(
        response=SimpleNamespace(
            content=[tool_block],
            usage=SimpleNamespace(input_tokens=False, output_tokens=-1),
        )
    )
    translator = AnthropicTranslator(
        model="claude-test",
        client=SimpleNamespace(messages=endpoint),
    )

    result = translator.translate(_request())

    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None


@pytest.mark.parametrize("model", ["", "   "])
def test_anthropic_adapter_requires_an_explicit_nonblank_model(model: str) -> None:
    with pytest.raises(ValueError, match="explicit Anthropic model"):
        AnthropicTranslator(model=model, client=SimpleNamespace(messages=object()))


def test_anthropic_adapter_enforces_output_budget_floor() -> None:
    with pytest.raises(ValueError, match="at least 256"):
        AnthropicTranslator(
            model="claude-test",
            max_output_tokens=255,
            client=SimpleNamespace(messages=object()),
        )


def test_anthropic_sdk_client_pins_the_official_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    captured_http: dict[str, object] = {}
    sentinel = SimpleNamespace(messages=object())
    http_sentinel = object()
    for variable in ("ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS"):
        monkeypatch.delenv(variable, raising=False)

    def construct(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(anthropic_adapter, "Anthropic", construct)
    monkeypatch.setattr(
        anthropic_adapter,
        "AnthropicDefaultHttpxClient",
        lambda **kwargs: captured_http.update(kwargs) or http_sentinel,
    )

    AnthropicTranslator(model="claude-test", api_key="opaque-key", timeout=19.0)

    assert captured == {
        "api_key": "opaque-key",
        "base_url": anthropic_adapter.ANTHROPIC_API_BASE_URL,
        "timeout": 19.0,
        "max_retries": 2,
        "http_client": http_sentinel,
    }
    assert captured_http == {"trust_env": False}


@pytest.mark.parametrize("variable", ["ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS"])
def test_anthropic_sdk_client_rejects_ambient_routing(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    for candidate in ("ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS"):
        monkeypatch.delenv(candidate, raising=False)
    monkeypatch.setenv(variable, "https://untrusted.invalid")
    monkeypatch.setattr(
        anthropic_adapter,
        "Anthropic",
        lambda **_kwargs: pytest.fail("unsafe SDK configuration must fail first"),
    )

    with pytest.raises(ProviderConfigurationError, match=variable):
        AnthropicTranslator(model="claude-test", api_key="opaque-key")


def test_factory_creates_identity_without_credentials() -> None:
    translator = providers.create_translator("identity", model=None)

    assert isinstance(translator, IdentityTranslator)


def test_factory_rejects_an_identity_model_override() -> None:
    with pytest.raises(ProviderConfigurationError, match="only supports identity-v1"):
        providers.create_translator("identity", model="other")


@pytest.mark.parametrize("provider_name", ["openai", "anthropic"])
@pytest.mark.parametrize("model", [None, "", "   "])
def test_factory_requires_a_paid_provider_model(
    provider_name: providers.ProviderName,
    model: str | None,
) -> None:
    with pytest.raises(ProviderConfigurationError, match="--model is required"):
        providers.create_translator(provider_name, model=model)


@pytest.mark.parametrize(
    ("provider_name", "environment_name"),
    [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")],
)
def test_factory_requires_nonblank_credentials(
    provider_name: providers.ProviderName,
    environment_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(environment_name, raising=False)
    with pytest.raises(ProviderConfigurationError, match=environment_name):
        providers.create_translator(provider_name, model="test-model")
    with pytest.raises(ProviderConfigurationError, match=environment_name):
        providers.create_translator(provider_name, model="test-model", api_key="   ")


@pytest.mark.parametrize(
    ("provider_name", "environment_name"),
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
    ],
)
def test_factory_uses_explicit_key_before_environment(
    provider_name: providers.ProviderName,
    environment_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, object] = {}
    sentinel = IdentityTranslator()

    def construct(**kwargs: object) -> IdentityTranslator:
        received.update(kwargs)
        return sentinel

    monkeypatch.setenv(environment_name, "environment-key")
    monkeypatch.setattr(providers, "_load_provider_constructor", lambda _provider: construct)

    result = providers.create_translator(
        provider_name,
        model=" test-model ",
        api_key="explicit-key",
    )

    assert result is sentinel
    assert received == {"model": " test-model ", "api_key": "explicit-key"}


@pytest.mark.parametrize("provider_name", ["openai", "anthropic"])
def test_factory_reports_the_exact_missing_optional_sdk(
    provider_name: providers.PaidProviderName,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_sdk(_module_name: str) -> object:
        raise ModuleNotFoundError(
            f"No module named {provider_name!r}",
            name=provider_name,
        )

    monkeypatch.setattr(providers, "import_module", missing_sdk)

    with pytest.raises(ProviderConfigurationError) as caught:
        providers.create_translator(
            provider_name,
            model="test-model",
            api_key="opaque-test-key",
        )

    message = str(caught.value)
    assert f"pptrans[{provider_name}]" in message
    assert f".[{provider_name}]" in message


def test_provider_loader_does_not_hide_an_unrelated_import_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_transitive_dependency(_module_name: str) -> object:
        raise ModuleNotFoundError("No module named 'httpx'", name="httpx")

    monkeypatch.setattr(providers, "import_module", missing_transitive_dependency)

    with pytest.raises(ModuleNotFoundError, match="httpx"):
        providers.create_translator(
            "openai",
            model="test-model",
            api_key="opaque-test-key",
        )


@pytest.mark.parametrize(
    ("class_name", "expected"),
    [
        ("OpenAITranslator", OpenAITranslator),
        ("AnthropicTranslator", AnthropicTranslator),
    ],
)
def test_provider_module_preserves_lazy_public_class_imports(
    class_name: str,
    expected: type[object],
) -> None:
    assert providers.__getattr__(class_name) is expected


def test_provider_module_rejects_unknown_lazy_attributes() -> None:
    def read_unknown_attribute() -> object:
        return providers.NotAProvider

    with pytest.raises(AttributeError, match="NotAProvider"):
        read_unknown_attribute()


def test_factory_rejects_an_unsupported_provider() -> None:
    with pytest.raises(ProviderConfigurationError, match="Unsupported provider"):
        providers.create_translator(  # type: ignore[arg-type]
            "not-a-provider",
            model="test-model",
            api_key="not-secret",
        )
