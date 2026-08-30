"""Benchmark the deterministic OOXML core with the committed synthetic deck."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics

# Used only for a fixed, non-shell git provenance query.
import subprocess  # nosec B404
import sys
import tempfile
import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from pptrans.adapters.providers.identity import IdentityTranslator
from pptrans.application.deck import write_translated_deck
from pptrans.application.translate import translate_plan
from pptrans.ooxml import inspect_deck


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    schema_version: str
    generated_at_utc: str
    command: str
    git_commit: str
    git_dirty: bool
    operating_system: str
    machine: str
    processor: str
    python_version: str
    renderer: str
    input_path: str
    input_sha256: str
    input_bytes: int
    slides: int
    translation_units: int
    translated_spans: int
    warmups: int
    iterations: int
    samples_ms: tuple[float, ...]
    median_ms: float
    p95_ms: float
    minimum_ms: float
    maximum_ms: float


def _git(*arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git is required to record benchmark provenance")
    # The executable is resolved by shutil.which and every argument is repository-owned.
    completed = subprocess.run(  # noqa: S603  # nosec B603
        [executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    return completed.stdout.strip()


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _summarize_durations(
    durations: Sequence[float],
) -> tuple[tuple[float, ...], float, float, float, float]:
    if not durations:
        raise ValueError("at least one benchmark duration is required")
    samples = tuple(round(value, 3) for value in durations)
    return (
        samples,
        round(statistics.median(samples), 3),
        round(_percentile(samples, 0.95), 3),
        min(samples),
        max(samples),
    )


def _run_once(source: Path, output: Path) -> tuple[int, int]:
    plan = inspect_deck(source, source_lang="en", target_lang="en")
    run = translate_plan(plan, IdentityTranslator())
    result = write_translated_deck(plan, run.translations, output)
    return result.report.verified_patches, result.report.verified_spans


def benchmark(source: Path, *, warmups: int, iterations: int) -> BenchmarkResult:
    source = source.expanduser().resolve()
    if warmups < 0 or iterations < 1:
        raise ValueError("warmups must be non-negative and iterations must be positive")
    plan = inspect_deck(source, source_lang="en", target_lang="en")
    durations: list[float] = []
    with tempfile.TemporaryDirectory(prefix="pptrans-benchmark-") as temp_name:
        root = Path(temp_name)
        for index in range(warmups + iterations):
            start = time.perf_counter()
            patches, spans = _run_once(source, root / f"output-{index:04d}.pptx")
            elapsed_ms = (time.perf_counter() - start) * 1_000
            if patches != len(plan.units):
                raise RuntimeError("benchmark did not verify every translation unit")
            if spans != sum(len(unit.translatable_span_ids) for unit in plan.units):
                raise RuntimeError("benchmark did not verify every translated span")
            if index >= warmups:
                durations.append(elapsed_ms)

    try:
        display_source = source.relative_to(Path.cwd()).as_posix()
    except ValueError:
        display_source = source.name
    command = (
        "python scripts/benchmark_core.py "
        f"--input {display_source} --warmups {warmups} --iterations {iterations}"
    )
    samples_ms, median_ms, p95_ms, minimum_ms, maximum_ms = _summarize_durations(durations)
    return BenchmarkResult(
        schema_version="pptrans.core-benchmark/v2",
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        command=command,
        git_commit=_git("rev-parse", "HEAD"),
        git_dirty=bool(_git("status", "--porcelain")),
        operating_system=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor() or "not reported",
        python_version=platform.python_version(),
        renderer="not used; this benchmark measures deterministic OOXML processing only",
        input_path=source.name,
        input_sha256=plan.input_sha256,
        input_bytes=source.stat().st_size,
        slides=len(plan.slide_parts),
        translation_units=len(plan.units),
        translated_spans=sum(len(unit.translatable_span_ids) for unit in plan.units),
        warmups=warmups,
        iterations=iterations,
        samples_ms=samples_ms,
        median_ms=median_ms,
        p95_ms=p95_ms,
        minimum_ms=minimum_ms,
        maximum_ms=maximum_ms,
    )


def _output_leaf(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.parent.resolve(strict=False) / expanded.name


def _prepare_output(source: Path, output: Path, *, overwrite: bool) -> Path:
    source = source.expanduser().resolve()
    destination = _output_leaf(output)
    if destination.is_symlink():
        raise ValueError("benchmark output must not be a symbolic link")
    same_file = source == destination
    with suppress(FileNotFoundError, OSError):
        same_file = same_file or source.samefile(destination)
    if same_file:
        raise ValueError("benchmark output must not identify the input presentation")
    if destination.exists() and destination.is_dir():
        raise IsADirectoryError(destination)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"benchmark output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _publish_result(serialized: str, destination: Path, *, overwrite: bool) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.pptrans-",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.is_symlink():
            raise ValueError("benchmark output became a symbolic link before publish")
        if overwrite:
            temporary.replace(destination)
        else:
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"benchmark output appeared before publish: {destination}"
                ) from exc
            except OSError as exc:
                raise RuntimeError(
                    "filesystem cannot atomically publish a no-overwrite benchmark result"
                ) from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("examples/pptrans-demo.en.pptx"))
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Atomically replace an existing benchmark JSON output (never the input deck).",
    )
    raw_arguments = sys.argv[1:] if argv is None else argv
    arguments = parser.parse_args(raw_arguments)
    destination = (
        _prepare_output(arguments.input, arguments.output, overwrite=arguments.overwrite)
        if arguments.output is not None
        else None
    )
    result = benchmark(arguments.input, warmups=arguments.warmups, iterations=arguments.iterations)
    result = replace(
        result,
        command=subprocess.list2cmdline(["python", "scripts/benchmark_core.py", *raw_arguments]),
    )
    serialized = json.dumps(asdict(result), indent=2, ensure_ascii=False) + "\n"
    if destination is not None:
        _publish_result(serialized, destination, overwrite=arguments.overwrite)
    sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
