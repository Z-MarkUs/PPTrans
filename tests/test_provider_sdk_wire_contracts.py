"""Exercise PPTrans adapters through the real provider SDK HTTP stacks."""

from __future__ import annotations

import importlib
import json
from typing import Any

from anthropic import Anthropic
from anthropic import DefaultHttpxClient as AnthropicDefaultHttpxClient
from openai import DefaultHttpxClient as OpenAIDefaultHttpxClient
from openai import OpenAI

from pptrans.adapters.providers.anthropic import AnthropicTranslator
from pptrans.adapters.providers.common import SYSTEM_INSTRUCTIONS
from pptrans.adapters.providers.openai import OpenAITranslator
from pptrans.domain.models import (
    ParagraphLocator,
    SpanKind,
    TextContainer,
    TextSpan,
    TranslationUnit,
)
from pptrans.ports.translator import TranslationBatchRequest


def _request() -> TranslationBatchRequest:
    unit = TranslationUnit(
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
    return TranslationBatchRequest(units=(unit,), source_lang="en", target_lang="fr")


def _payload(text: str = "Bonjour") -> dict[str, object]:
    return {
        "translations": [
            {
                "unit_id": "unit-1",
                "spans": [{"span_id": "span-1", "text": text}],
            }
        ]
    }


def _httpx_for(client_type: type[object]) -> Any:
    """Load the HTTPX namespace used by this installed SDK generation."""

    base_module = client_type.__mro__[1].__module__.partition(".")[0]
    return importlib.import_module(base_module)


def _recording_transport(
    client_type: type[object],
    response_document: dict[str, object],
) -> tuple[Any, list[tuple[str, str, dict[str, Any]]]]:
    httpx = _httpx_for(client_type)
    requests: list[tuple[str, str, dict[str, Any]]] = []

    def handle(request: Any) -> object:
        body = json.loads(request.content)
        assert isinstance(body, dict)
        requests.append((request.method, request.url.path, body))
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json=response_document,
            request=request,
        )

    return httpx.MockTransport(handle), requests


def _openai_response() -> dict[str, object]:
    return {
        "id": "resp_pptrans_test",
        "object": "response",
        "created_at": 1_725_000_000,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": 512,
        "model": "gpt-test",
        "output": [
            {
                "id": "msg_pptrans_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(_payload()),
                        "annotations": [],
                    }
                ],
            }
        ],
        "parallel_tool_calls": False,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": False,
        "temperature": None,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": None,
        "truncation": "disabled",
        "usage": {
            "input_tokens": 41,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 17,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 58,
        },
        "metadata": {},
    }


def _anthropic_response() -> dict[str, object]:
    return {
        "id": "msg_pptrans_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_pptrans_test",
                "name": "submit_translations",
                "input": _payload(),
            }
        ],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 35, "output_tokens": 12},
    }


def _assert_request_document(serialized: object) -> None:
    assert isinstance(serialized, str)
    document = json.loads(serialized)
    assert document["source_lang"] == "en"
    assert document["target_lang"] == "fr"
    assert document["units"][0]["unit_id"] == "unit-1"
    assert [(span["span_id"], span["translatable"]) for span in document["units"][0]["spans"]] == [
        ("span-1", True),
        ("span-locked", False),
    ]


def test_openai_real_sdk_serializes_and_parses_the_wire_contract() -> None:
    transport, requests = _recording_transport(OpenAIDefaultHttpxClient, _openai_response())
    http_client = OpenAIDefaultHttpxClient(transport=transport, trust_env=False)

    with OpenAI(
        api_key="unit-test-placeholder",
        base_url="https://api.openai.com/v1",
        max_retries=0,
        http_client=http_client,
    ) as client:
        result = OpenAITranslator(
            model="gpt-test",
            max_output_tokens=512,
            client=client,
        ).translate(_request())

    assert result.translations[0].spans[0].text == "Bonjour"
    assert result.usage.input_tokens == 41
    assert result.usage.output_tokens == 17
    assert len(requests) == 1
    method, path, body = requests[0]
    assert (method, path) == ("POST", "/v1/responses")
    assert body["model"] == "gpt-test"
    assert body["instructions"] == SYSTEM_INSTRUCTIONS
    assert body["max_output_tokens"] == 512
    assert body["store"] is False
    _assert_request_document(body["input"])
    output_format = body["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["name"] == "pptrans_translation_batch"
    assert output_format["strict"] is True
    assert output_format["schema"]["additionalProperties"] is False


def test_anthropic_real_sdk_serializes_and_parses_the_wire_contract() -> None:
    transport, requests = _recording_transport(
        AnthropicDefaultHttpxClient,
        _anthropic_response(),
    )
    http_client = AnthropicDefaultHttpxClient(transport=transport, trust_env=False)

    with Anthropic(
        api_key="unit-test-placeholder",
        base_url="https://api.anthropic.com",
        max_retries=0,
        http_client=http_client,
    ) as client:
        result = AnthropicTranslator(
            model="claude-test",
            max_output_tokens=512,
            client=client,
        ).translate(_request())

    assert result.translations[0].spans[0].text == "Bonjour"
    assert result.usage.input_tokens == 35
    assert result.usage.output_tokens == 12
    assert len(requests) == 1
    method, path, body = requests[0]
    assert (method, path) == ("POST", "/v1/messages")
    assert body["model"] == "claude-test"
    assert body["max_tokens"] == 512
    assert body["system"] == SYSTEM_INSTRUCTIONS
    _assert_request_document(body["messages"][0]["content"])
    assert body["tool_choice"] == {"type": "tool", "name": "submit_translations"}
    assert len(body["tools"]) == 1
    assert body["tools"][0]["name"] == "submit_translations"
    assert body["tools"][0]["input_schema"]["additionalProperties"] is False
