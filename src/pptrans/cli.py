"""Command-line interface for the formatting-safe PPTrans v2 pipeline."""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, NoReturn
from unicodedata import category

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from pptrans import __version__
from pptrans.adapters.providers import create_translator
from pptrans.adapters.sqlite_memory import SQLiteTranslationMemory
from pptrans.application.deck import preflight_output, write_translated_deck
from pptrans.application.translate import (
    ProviderWorkEstimate,
    TranslationOptions,
    estimate_provider_work,
    translate_plan,
    validate_provider_budget,
)
from pptrans.config import default_memory_path, load_environment
from pptrans.doctor import run_doctor
from pptrans.domain.errors import PPTransError
from pptrans.domain.models import DeckPlan, Diagnostic
from pptrans.glossary import load_glossary
from pptrans.ooxml.inspect import inspect_deck


class ProviderChoice(str, Enum):
    """Providers implemented by the v2 CLI."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    IDENTITY = "identity"


app = typer.Typer(
    add_completion=False,
    help="Translate editable PPTX files by patching text nodes in the original OOXML package.",
    invoke_without_command=True,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
console = Console()
error_console = Console(stderr=True)


def _terminal_string(value: object, *, allow_newlines: bool = False) -> str:
    """Render control characters visibly so untrusted text cannot drive a terminal."""

    safe: list[str] = []
    for character in str(value):
        codepoint = ord(character)
        if character == "\n" and allow_newlines:
            safe.append(character)
        elif category(character) == "Cc":
            safe.append(f"\\u{codepoint:04x}")
        else:
            safe.append(character)
    return "".join(safe)


def _write_json(value: object) -> None:
    """Write plain ASCII-safe JSON without Rich markup or terminal styling."""

    sys.stdout.write(json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n")


def _configure_utf8_streams() -> None:
    """Use UTF-8 for real console streams while leaving test capture objects alone."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _abort(message: str, *, code: int = 2) -> NoReturn:
    error_console.print(Text.assemble(("Error:", "red"), " ", _terminal_string(message)))
    raise typer.Exit(code=code)


def _default_output(source: Path, target_lang: str) -> Path:
    safe_language = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in target_lang.strip()
    ).strip("-")
    return source.with_name(f"{source.stem}.{safe_language or 'translated'}.pptx")


def _absolute_output_leaf(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.parent.resolve(strict=False) / expanded.name


def _warning_payload(plan: DeckPlan) -> list[dict[str, object]]:
    return [
        {
            "code": warning.code,
            "message": warning.message,
            "slide": warning.slide_index,
            "shape_id_path": list(warning.shape_id_path),
        }
        for warning in plan.warnings
    ]


def _warning_location(warning: Diagnostic) -> str:
    parts: list[str] = []
    if warning.slide_index is not None:
        parts.append(f"slide {warning.slide_index}")
    if warning.shape_id_path:
        parts.append("shape " + "/".join(str(shape_id) for shape_id in warning.shape_id_path))
    return ", ".join(parts)


def _print_warnings(plan: DeckPlan) -> None:
    for warning in plan.warnings:
        location = _warning_location(warning)
        label = warning.code if not location else f"{warning.code} ({location})"
        error_console.print(
            Text.assemble(
                ("Warning:", "yellow"),
                " ",
                _terminal_string(label),
                ": ",
                _terminal_string(warning.message),
            )
        )


def _abort_for_warnings(plan: DeckPlan) -> NoReturn:
    _print_warnings(plan)
    count = len(plan.warnings)
    noun = "warning" if count == 1 else "warnings"
    _abort(
        f"Inspection reported {count} {noun}; refusing to continue because "
        "--fail-on-warnings is set.",
        code=1,
    )


def _require_translation_units(plan: DeckPlan) -> None:
    if not plan.units:
        raise ValueError(
            "No supported translatable slide text was found. Charts, SmartArt, notes, "
            "masters, image text, and other unsupported parts are preserved but not translated."
        )


def _validate_preview_provider_model(provider: ProviderChoice, model: str | None) -> str:
    """Validate provider/model selection without importing an SDK or reading credentials."""

    if provider is ProviderChoice.IDENTITY:
        if model not in (None, "", "identity-v1"):
            raise ValueError("The identity provider only supports identity-v1.")
        return "identity-v1"
    if model is None or not model.strip():
        raise ValueError(f"--model is required for provider {provider.value!r}.")
    return model.strip()


def _provider_preview_payload(
    plan: DeckPlan,
    estimate: ProviderWorkEstimate,
    *,
    provider: ProviderChoice,
    model: str,
) -> dict[str, object]:
    """Build a deck-text-free provider-work preview."""

    return {
        "mode": "dry-run",
        "provider": provider.value,
        "model": model,
        "source_sha256": plan.input_sha256,
        "slides": len(plan.slide_parts),
        "translation_units": len(plan.units),
        "translatable_spans": sum(len(unit.translatable_span_ids) for unit in plan.units),
        "provider_units": estimate.provider_units,
        "provider_calls": estimate.provider_calls,
        "source_context_characters": estimate.source_context_characters,
        "request_characters": estimate.request_characters,
        "largest_request_characters": estimate.largest_request_characters,
        "request_characters_per_call": list(estimate.request_characters_per_call),
        "assumes_zero_memory_hits": True,
        "measurement_scope": "characters-not-tokens-cost-or-latency",
        "warnings": _warning_payload(plan),
    }


def _print_provider_preview(payload: dict[str, object]) -> None:
    table = Table(title="PPTrans provider work preview")
    table.add_column("Property")
    table.add_column("Value")
    rows = (
        ("Provider", payload["provider"]),
        ("Model", payload["model"]),
        ("Source SHA-256", payload["source_sha256"]),
        ("Slides", payload["slides"]),
        ("Translation units", payload["translation_units"]),
        ("Translatable spans", payload["translatable_spans"]),
        ("Provider units", payload["provider_units"]),
        ("Provider calls", payload["provider_calls"]),
        ("Source/context characters", payload["source_context_characters"]),
        ("Serialized request characters", payload["request_characters"]),
        ("Largest request characters", payload["largest_request_characters"]),
    )
    for label, value in rows:
        table.add_row(label, Text(_terminal_string(value)))
    console.print(table)
    console.print(
        "Plan assumes zero translation-memory hits; total workload is an upper bound, while "
        "per-call grouping describes this zero-hit plan. Character counts are not token, "
        "currency, or latency estimates. No credential, provider, memory, output, or network "
        "was used."
    )


def _build_provider_preview(
    *,
    input_path: Path,
    source_lang: str,
    target_lang: str,
    provider: ProviderChoice,
    model: str | None,
    output_path: Path | None,
    glossary_path: Path | None,
    style: str | None,
    batch_size: int,
    max_provider_units: int,
    max_provider_calls: int,
    max_provider_source_characters: int,
    max_provider_request_characters: int,
    memory_path: Path | None,
    dotenv_path: Path | None,
    overwrite: bool,
    fail_on_warnings: bool,
) -> tuple[DeckPlan, ProviderWorkEstimate, str]:
    """Inspect and estimate without crossing a credential, memory, output, or SDK boundary."""

    if output_path is not None or overwrite:
        raise ValueError("--dry-run cannot be combined with --output or --overwrite.")
    if dotenv_path is not None:
        raise ValueError("--dry-run cannot be combined with --env-file.")
    if memory_path is not None:
        raise ValueError("--dry-run cannot be combined with --memory.")
    selected_model = _validate_preview_provider_model(provider, model)
    source = input_path.expanduser().resolve()
    resolved_glossary = glossary_path.expanduser().resolve() if glossary_path is not None else None
    glossary = load_glossary(resolved_glossary) if resolved_glossary is not None else ()
    plan = inspect_deck(source, source_lang=source_lang, target_lang=target_lang)
    if fail_on_warnings and plan.warnings:
        _abort_for_warnings(plan)
    _require_translation_units(plan)
    options = TranslationOptions(
        glossary=glossary,
        style=style,
        batch_size=batch_size,
        max_provider_units=max_provider_units,
        max_provider_calls=max_provider_calls,
        max_provider_source_characters=max_provider_source_characters,
        max_provider_request_characters=max_provider_request_characters,
    )
    estimate = estimate_provider_work(
        plan.units,
        options,
        source_lang=plan.source_lang,
        target_lang=plan.target_lang,
    )
    return plan, estimate, selected_model


def _resolve_translation_paths(
    *,
    input_path: Path,
    output_path: Path | None,
    target_lang: str,
    dotenv_path: Path | None,
    glossary_path: Path | None,
    memory_path: Path | None,
    no_memory: bool,
) -> tuple[Path, Path, Path | None, Path | None, Path | None]:
    """Resolve CLI paths and reject aliases before opening configuration or providers."""

    source = input_path.expanduser().resolve()
    raw_destination = (
        output_path if output_path is not None else _default_output(source, target_lang)
    )
    destination = _absolute_output_leaf(raw_destination)
    if destination.is_symlink():
        raise ValueError("Output path must not be a symbolic link.")
    resolved_dotenv = dotenv_path.expanduser().resolve() if dotenv_path is not None else None
    resolved_glossary = glossary_path.expanduser().resolve() if glossary_path is not None else None
    if destination == source:
        raise ValueError("Output path must not overwrite the source PPTX.")
    configuration_inputs = {
        path for path in (resolved_dotenv, resolved_glossary) if path is not None
    }
    if destination in configuration_inputs:
        raise ValueError("Output path must not overwrite an environment or glossary input.")
    if no_memory and memory_path is not None:
        raise ValueError("--memory cannot be combined with --no-memory.")

    resolved_memory = None
    if not no_memory:
        resolved_memory = _absolute_output_leaf(memory_path or default_memory_path())
        if resolved_memory.is_symlink():
            raise ValueError("Translation-memory path must not be a symbolic link.")
        if resolved_memory in {source, destination, *configuration_inputs}:
            raise ValueError(
                "Translation-memory path must be distinct from the source, output, "
                "environment file, and glossary."
            )
    return source, destination, resolved_dotenv, resolved_glossary, resolved_memory


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option("--version", help="Print the installed PPTrans version and exit."),
    ] = False,
) -> None:
    """Run PPTrans commands."""

    if version:
        console.print(f"pptrans {__version__}")
        raise typer.Exit


@app.command("inspect")
def inspect_command(
    input_path: Annotated[Path, typer.Argument(help="Source .pptx presentation.")],
    source_lang: Annotated[str, typer.Option("--source", help="Source language code/name.")],
    target_lang: Annotated[str, typer.Option("--target", help="Target language code/name.")],
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emit machine-readable metadata; deck-text-free unless --show-text is set.",
        ),
    ] = False,
    show_text: Annotated[
        bool,
        typer.Option("--show-text", help="Include deck text in output; may expose sensitive data."),
    ] = False,
    fail_on_warnings: Annotated[
        bool,
        typer.Option(
            "--fail-on-warnings",
            help="Exit 1 after inspection when unsupported-content warnings are present.",
        ),
    ] = False,
) -> None:
    """Inspect a deck without calling a model or changing any file."""

    try:
        plan = inspect_deck(input_path, source_lang=source_lang, target_lang=target_lang)
    except (PPTransError, OSError, ValueError) as exc:
        _abort(str(exc))

    payload: dict[str, object] = {
        "schema_version": plan.schema_version,
        "source": str(plan.source_path),
        "sha256": plan.input_sha256,
        "slides": len(plan.slide_parts),
        "translation_units": len(plan.units),
        "translatable_spans": sum(len(unit.translatable_span_ids) for unit in plan.units),
        "warnings": _warning_payload(plan),
    }
    if show_text:
        payload["units"] = [
            {"unit_id": unit.id, "slide": unit.locator.slide_index, "text": unit.source_text}
            for unit in plan.units
        ]
    if as_json:
        _write_json(payload)
        if fail_on_warnings and plan.warnings:
            raise typer.Exit(code=1)
        return

    table = Table(title="PPTrans deck plan")
    table.add_column("Property")
    table.add_column("Value")
    table.add_row("Source", Text(_terminal_string(plan.source_path)))
    table.add_row("SHA-256", Text(plan.input_sha256))
    table.add_row("Slides", Text(str(len(plan.slide_parts))))
    table.add_row("Translation units", Text(str(len(plan.units))))
    table.add_row("Warnings", Text(str(len(plan.warnings))))
    console.print(table)
    _print_warnings(plan)
    if show_text:
        for unit in plan.units:
            console.print(
                Text.assemble(
                    (f"{unit.id} · slide {unit.locator.slide_index}", "dim"),
                    " ",
                    _terminal_string(unit.source_text, allow_newlines=True),
                )
            )
    if fail_on_warnings and plan.warnings:
        raise typer.Exit(code=1)


@app.command("translate")
def translate_command(
    input_path: Annotated[Path, typer.Argument(help="Source .pptx presentation.")],
    source_lang: Annotated[str, typer.Option("--source", help="Source language code/name.")],
    target_lang: Annotated[str, typer.Option("--target", help="Target language code/name.")],
    provider: Annotated[
        ProviderChoice,
        typer.Option("--provider", case_sensitive=False, help="Translation provider."),
    ],
    model: Annotated[
        str | None,
        typer.Option("--model", help="Explicit provider model; required for paid providers."),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Distinct destination .pptx path."),
    ] = None,
    glossary_path: Annotated[
        Path | None,
        typer.Option("--glossary", help="Strict PPTrans JSON/YAML terminology file."),
    ] = None,
    style: Annotated[
        str | None,
        typer.Option("--style", help="Optional tone or audience constraint."),
    ] = None,
    batch_size: Annotated[
        int, typer.Option("--batch-size", min=1, max=200, help="Units per provider call.")
    ] = 24,
    max_provider_units: Annotated[
        int,
        typer.Option(
            "--max-provider-units",
            min=1,
            help="Maximum cache-miss units sent to a provider; raise explicitly for large runs.",
        ),
    ] = 2_000,
    max_provider_calls: Annotated[
        int,
        typer.Option(
            "--max-provider-calls",
            min=1,
            help="Maximum logical provider batches; SDK-internal retries are not counted.",
        ),
    ] = 100,
    max_provider_source_characters: Annotated[
        int,
        typer.Option(
            "--max-provider-source-characters",
            min=1,
            help="Maximum source/context characters sent to a provider.",
        ),
    ] = 2_000_000,
    max_provider_request_characters: Annotated[
        int,
        typer.Option(
            "--max-provider-request-characters",
            min=1,
            help="Maximum total serialized request characters across all logical batches.",
        ),
    ] = 5_000_000,
    memory_path: Annotated[
        Path | None,
        typer.Option("--memory", help="Local SQLite translation-memory path."),
    ] = None,
    no_memory: Annotated[
        bool, typer.Option("--no-memory", help="Disable translation-memory reads and writes.")
    ] = False,
    dotenv_path: Annotated[
        Path | None,
        typer.Option("--env-file", help="Load credentials from this local dotenv file."),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace an existing output, never the source.")
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Preview a zero-memory-hit provider workload without credentials, memory, "
                "output, or network access."
            ),
        ),
    ] = False,
    fail_on_warnings: Annotated[
        bool,
        typer.Option(
            "--fail-on-warnings",
            help="Abort before provider construction when inspection warnings are present.",
        ),
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit a machine-readable completion report.")
    ] = False,
) -> None:
    """Translate a PPTX through a validated provider and atomic OOXML patch."""

    if dry_run:
        try:
            plan, estimate, selected_model = _build_provider_preview(
                input_path=input_path,
                source_lang=source_lang,
                target_lang=target_lang,
                provider=provider,
                model=model,
                output_path=output_path,
                glossary_path=glossary_path,
                style=style,
                batch_size=batch_size,
                max_provider_units=max_provider_units,
                max_provider_calls=max_provider_calls,
                max_provider_source_characters=max_provider_source_characters,
                max_provider_request_characters=max_provider_request_characters,
                memory_path=memory_path,
                dotenv_path=dotenv_path,
                overwrite=overwrite,
                fail_on_warnings=fail_on_warnings,
            )
        except (PPTransError, OSError, ValueError) as exc:
            _abort(str(exc))

        payload = _provider_preview_payload(
            plan,
            estimate,
            provider=provider,
            model=selected_model,
        )
        if as_json:
            _write_json(payload)
        else:
            _print_provider_preview(payload)
            _print_warnings(plan)
        return

    try:
        source, destination, resolved_dotenv, resolved_glossary, resolved_memory = (
            _resolve_translation_paths(
                input_path=input_path,
                output_path=output_path,
                target_lang=target_lang,
                dotenv_path=dotenv_path,
                glossary_path=glossary_path,
                memory_path=memory_path,
                no_memory=no_memory,
            )
        )

        load_environment(resolved_dotenv)
        glossary = load_glossary(resolved_glossary) if resolved_glossary is not None else ()
        plan = inspect_deck(source, source_lang=source_lang, target_lang=target_lang)
        if fail_on_warnings and plan.warnings:
            _abort_for_warnings(plan)
        _require_translation_units(plan)
        destination = preflight_output(plan, destination, overwrite=overwrite)
        options = TranslationOptions(
            glossary=glossary,
            style=style,
            batch_size=batch_size,
            max_provider_units=max_provider_units,
            max_provider_calls=max_provider_calls,
            max_provider_source_characters=max_provider_source_characters,
            max_provider_request_characters=max_provider_request_characters,
        )
        # Deliberately conservative: require large-run opt-in before constructing a paid
        # provider client. translate_plan rechecks only cache misses after memory lookup.
        validate_provider_budget(
            plan.units,
            options,
            source_lang=plan.source_lang,
            target_lang=plan.target_lang,
        )
        translator = create_translator(
            provider.value,
            model=model,
        )
        if no_memory:
            run = translate_plan(plan, translator, options=options)
        else:
            memory_location = resolved_memory or default_memory_path().expanduser().resolve()
            with SQLiteTranslationMemory(memory_location) as memory:
                run = translate_plan(plan, translator, memory=memory, options=options)
        result = write_translated_deck(
            plan,
            run.translations,
            destination,
            overwrite=overwrite,
        )
    except (PPTransError, OSError, ValueError) as exc:
        _abort(str(exc))

    payload = {
        "output": str(result.output_path),
        "source_sha256": result.report.source_sha256,
        "output_sha256": result.report.output_sha256,
        "verified_patches": result.report.verified_patches,
        "verified_spans": result.report.verified_spans,
        "provider": translator.provider,
        "model": translator.model,
        "memory_hits": run.stats.memory_hits,
        "provider_calls": run.stats.provider_calls,
        "input_tokens": run.stats.input_tokens,
        "output_tokens": run.stats.output_tokens,
        "warnings": _warning_payload(plan),
    }
    if as_json:
        _write_json(payload)
        return
    console.print(
        Text.assemble(
            ("Translated and verified:", "green"),
            " ",
            _terminal_string(result.output_path),
        )
    )
    console.print(
        f"{result.report.verified_spans} text spans · "
        f"{run.stats.memory_hits} memory hits · {run.stats.provider_calls} provider calls"
    )
    _print_warnings(plan)


@app.command("doctor")
def doctor_command(
    provider: Annotated[
        ProviderChoice | None,
        typer.Option(
            "--provider",
            case_sensitive=False,
            help="Also check this provider's SDK and credential, when applicable.",
        ),
    ] = None,
    dotenv_path: Annotated[
        Path | None,
        typer.Option("--env-file", help="Load credentials from this local dotenv file."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Emit machine-readable results.")] = False,
) -> None:
    """Check local dependencies and optional capabilities without a network call."""

    try:
        load_environment(dotenv_path)
        checks = run_doctor(provider.value if provider is not None else None)
    except (OSError, ValueError) as exc:
        _abort(str(exc))
    if as_json:
        _write_json([check.as_dict() for check in checks])
    else:
        table = Table(title="PPTrans doctor")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Required")
        table.add_column("Detail")
        for check in checks:
            table.add_row(
                Text(_terminal_string(check.name)),
                Text(_terminal_string(check.status.upper())),
                Text("yes" if check.required else "no"),
                Text(_terminal_string(check.detail)),
            )
        console.print(table)
    if any(check.required and check.status == "fail" for check in checks):
        raise typer.Exit(code=1)


def main() -> None:
    """Console-script entry point."""

    _configure_utf8_streams()
    app()


if __name__ == "__main__":
    main()
