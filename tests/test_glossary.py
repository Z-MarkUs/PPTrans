"""Strict, offline tests for PPTrans terminology-file loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pptrans.glossary import MAX_GLOSSARY_BYTES, load_glossary
from pptrans.ports.translator import GlossaryTerm


@pytest.mark.parametrize("suffix", [".json", ".yaml", ".yml"])
def test_loads_strict_json_and_yaml_documents(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"terms{suffix}"
    if suffix == ".json":
        path.write_text(
            json.dumps(
                {
                    "terms": [
                        {"source": " deck ", "target": " présentation ", "note": " formal "},
                        {"source": "slide", "target": "diapositive", "note": None},
                    ]
                }
            ),
            encoding="utf-8",
        )
    else:
        path.write_text(
            """terms:
  - source: " deck "
    target: " présentation "
    note: " formal "
  - source: slide
    target: diapositive
    note: null
""",
            encoding="utf-8",
        )

    loaded = load_glossary(path)

    assert loaded == (
        GlossaryTerm(source="deck", target="présentation", note="formal"),
        GlossaryTerm(source="slide", target="diapositive", note=None),
    )


def test_empty_terms_document_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text('{"terms": []}', encoding="utf-8")

    assert load_glossary(path) == ()


@pytest.mark.parametrize(
    "document",
    [
        {"terms": [{"source": "API", "target": "接口"}, {"source": "api", "target": "API"}]},
        {
            "terms": [
                {"source": "Straße", "target": "rue"},
                {"source": "STRASSE", "target": "route"},
            ]
        },
    ],
    ids=["ascii-casefold", "unicode-casefold"],
)
def test_rejects_duplicate_sources_case_insensitively(
    tmp_path: Path,
    document: dict[str, object],
) -> None:
    path = tmp_path / "duplicates.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="repeats source term"):
        load_glossary(path)


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        {},
        {"terms": "not-a-list"},
        {"terms": [], "unexpected": True},
        {"terms": [{"source": "deck", "target": "jeu", "unexpected": True}]},
        {"terms": [{"source": 7, "target": "sept"}]},
        {"terms": [{"source": "deck", "target": False}]},
        {"terms": [{"source": "   ", "target": "jeu"}]},
        {"terms": [{"source": "deck", "target": "   "}]},
        {"terms": [{"source": "deck", "target": "jeu", "note": 7}]},
    ],
    ids=[
        "null-root",
        "list-root",
        "missing-terms",
        "terms-not-list",
        "extra-root-field",
        "extra-entry-field",
        "numeric-source",
        "boolean-target",
        "blank-source",
        "blank-target",
        "numeric-note",
    ],
)
def test_rejects_wrong_shapes_types_blanks_and_extra_fields(
    tmp_path: Path,
    document: object,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="valid PPTrans terms document"):
        load_glossary(path)


@pytest.mark.parametrize(
    ("suffix", "content"),
    [
        (".json", "{broken"),
        (".yaml", "terms: [unterminated"),
    ],
)
def test_rejects_malformed_serialization(tmp_path: Path, suffix: str, content: str) -> None:
    path = tmp_path / f"malformed{suffix}"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="valid PPTrans terms document"):
        load_glossary(path)


def test_rejects_non_utf8_input(tmp_path: Path) -> None:
    path = tmp_path / "binary.json"
    path.write_bytes(b'{"terms": [\xff]}')

    with pytest.raises(ValueError, match="valid PPTrans terms document"):
        load_glossary(path)


def test_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError, match="Glossary file does not exist"):
        load_glossary(path)


@pytest.mark.parametrize("suffix", [".txt", ".toml", ""])
def test_rejects_invalid_extension_even_for_valid_json(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"terms{suffix}"
    path.write_text('{"terms": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="must be JSON or YAML"):
        load_glossary(path)


def test_rejects_files_over_the_byte_limit_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (MAX_GLOSSARY_BYTES + 1))

    with pytest.raises(ValueError, match=f"{MAX_GLOSSARY_BYTES:,}-byte limit"):
        load_glossary(path)


@pytest.mark.parametrize(
    "entry",
    [
        {"source": "s" * 1_001, "target": "ok"},
        {"source": "ok", "target": "t" * 1_001},
        {"source": "ok", "target": "fine", "note": "n" * 2_001},
    ],
    ids=["source", "target", "note"],
)
def test_rejects_entry_fields_over_their_character_limits(
    tmp_path: Path,
    entry: dict[str, str],
) -> None:
    path = tmp_path / "too-long.json"
    path.write_text(json.dumps({"terms": [entry]}), encoding="utf-8")

    with pytest.raises(ValueError, match="valid PPTrans terms document"):
        load_glossary(path)
