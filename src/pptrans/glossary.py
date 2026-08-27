"""Safe loading of compact JSON or YAML terminology files."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pptrans.ports.translator import GlossaryTerm

MAX_GLOSSARY_BYTES = 2 * 1024 * 1024


class _GlossaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    source: str = Field(min_length=1, max_length=1_000)
    target: str = Field(min_length=1, max_length=1_000)
    note: str | None = Field(default=None, max_length=2_000)


class _GlossaryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    terms: list[_GlossaryEntry] = Field(max_length=10_000)


def load_glossary(path: Path) -> tuple[GlossaryTerm, ...]:
    """Load a strict ``terms`` document and reject duplicate source entries."""

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Glossary file does not exist: {resolved}")
    if resolved.stat().st_size > MAX_GLOSSARY_BYTES:
        raise ValueError(f"Glossary exceeds the {MAX_GLOSSARY_BYTES:,}-byte limit.")
    if resolved.suffix.lower() not in {".json", ".yaml", ".yml"}:
        raise ValueError("Glossary must be JSON or YAML.")

    try:
        text = resolved.read_text(encoding="utf-8")
        raw = json.loads(text) if resolved.suffix.lower() == ".json" else yaml.safe_load(text)
        document = _GlossaryDocument.model_validate(raw, strict=True)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError("Glossary is not a valid PPTrans terms document.") from exc

    seen: set[str] = set()
    terms: list[GlossaryTerm] = []
    for item in document.terms:
        identity = item.source.casefold()
        if identity in seen:
            raise ValueError(f"Glossary repeats source term {item.source!r}.")
        seen.add(identity)
        terms.append(GlossaryTerm(source=item.source, target=item.target, note=item.note))
    return tuple(terms)


__all__ = ["load_glossary"]
