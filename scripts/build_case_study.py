"""Build the one-page PPTrans engineering case study for job applications."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import statistics
import string
import sys
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import Any, cast

import yaml
from pypdf import PdfReader
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    TextStringObject,
)
from reportlab.lib.colors import Color, HexColor  # type: ignore[import-untyped]
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from reportlab.platypus import Paragraph  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "output" / "pdf" / "PPTrans-Engineering-Case-Study.pdf"
LEDGER_PATH = REPO_ROOT / "docs" / "portfolio" / "pptrans-engineering-case-study.json"
LOCAL_TEST_AUDIT_PATH = REPO_ROOT / "docs" / "qa" / "2026-08-31-local-test-audit.json"
LOCAL_TEST_AUDIT_SHA256 = "d41bbbc2885a291b50328ff180dcfe30df1b5b84580a600d3baaaaa8f23ef358"

PAGE_WIDTH, PAGE_HEIGHT = A4
FINAL_PIPELINE_STEP_INDEX = 5
SHA256_HEX_LENGTH = 64
GIT_SHA1_HEX_LENGTH = 40
ISO_DATE_LENGTH = 10
VERSION_COMPONENT_COUNT = 2
BENCHMARK_WARMUPS = 3
BENCHMARK_ITERATIONS = 30
MAX_LEDGER_DISPLAY_CHARACTERS = 80
PDF_POINT_TOLERANCE = 0.01
PDF_ID_COMPONENT_COUNT = 2
EXPECTED_PDF_SHA256 = "387f53a76eaf18e063bba8cbd5d9740abaa886632177be19884589820f276182"
EXPECTED_PDF_ID_BYTES = bytes.fromhex("ec9437ccae69cc9984c7b2483e4a70e0")
EXPECTED_SETUP_PYTHON_ACTION = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
EXPECTED_CI_WORKFLOW_SHA256 = "798255206cc27354b06767f0f59db3a24223326ca81c30ce5f09a72da0f1c8ad"
SAFE_LEDGER_TEXT_CHARACTERS = frozenset(string.ascii_letters + string.digits + " .,/-%+")
FORBIDDEN_PDF_ACTION_TYPES = {
    "/GoTo",
    "/GoToE",
    "/GoToR",
    "/Hide",
    "/ImportData",
    "/JavaScript",
    "/Launch",
    "/Movie",
    "/Named",
    "/Rendition",
    "/ResetForm",
    "/RichMediaExecute",
    "/SetOCGState",
    "/Sound",
    "/SubmitForm",
    "/Thread",
    "/Trans",
    "/URI",
}
FORBIDDEN_PDF_INTERACTIVE_KEYS = {
    "/A",
    "/AA",
    "/AF",
    "/AcroForm",
    "/Annots",
    "/Collection",
    "/EF",
    "/EmbeddedFiles",
    "/JavaScript",
    "/Metadata",
    "/OpenAction",
    "/PieceInfo",
    "/RichMedia",
    "/XFA",
}
FORBIDDEN_PDF_OBJECT_TYPES = {"/EmbeddedFile", "/Filespec"}
EXPECTED_PDF_ROOT_KEYS = {"/PageMode", "/Pages", "/Type"}
ALLOWED_PDF_TRAILER_KEYS = {"/ID", "/Info", "/Root", "/Size"}
REQUIRED_PDF_TRAILER_KEYS = {"/Info", "/Root", "/Size"}
EXPECTED_PDF_METADATA = {
    "/Author": "Hehan Zhao",
    "/CreationDate": "D:20000101000000+00'00'",
    "/Creator": "scripts/build_case_study.py",
    "/Keywords": "PPTrans, PowerPoint, OOXML, translation, Python, case study",
    "/ModDate": "D:20000101000000+00'00'",
    "/Producer": "ReportLab PDF Library - (opensource)",
    "/Subject": "One-page PPTrans v2 engineering showcase with verified package integrity",
    "/Title": "PPTrans Engineering Case Study",
    "/Trapped": "/False",
}

NAVY = HexColor("#0B1F33")
INK = HexColor("#172433")
MUTED = HexColor("#526475")
BLUE = HexColor("#246BCE")
TEAL = HexColor("#00A39A")
PALE_BLUE = HexColor("#EEF5FC")
PALE_TEAL = HexColor("#EAF8F6")
PALE_AMBER = HexColor("#FFF4D6")
AMBER = HexColor("#D98E04")
LINE = HexColor("#D6E0E8")
WHITE = HexColor("#FFFFFF")

REQUIRED_EVIDENCE_KEYS = {
    "tests",
    "coverage",
    "property_examples",
    "demo",
    "changed_members",
    "benchmark",
    "preview_units",
    "preview_calls",
    "preview_source_context_chars",
    "preview_request_chars",
    "preview_largest_request_chars",
    "supported_python",
}


def _tracked_path(relative: object) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("case-study ledger paths must be non-empty POSIX-style strings")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"case-study ledger path escapes the repository: {relative!r}")
    return REPO_ROOT / path


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {label}: {exc}") from exc
    if not isinstance(loaded, dict) or not all(isinstance(key, str) for key in loaded):
        raise TypeError(f"{label} must be a JSON object")
    return cast(dict[str, Any], loaded)


def _evidence_display(evidence: dict[str, Any], key: str) -> str:
    entry = evidence[key]
    if not isinstance(entry, dict) or not isinstance(entry.get("display"), str):
        raise TypeError(f"case-study evidence {key!r} must define a display string")
    return cast(str, entry["display"])


def _validate_plain_ledger_text(label: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_LEDGER_DISPLAY_CHARACTERS
        or not value.isascii()
        or any(character not in SAFE_LEDGER_TEXT_CHARACTERS for character in value)
    ):
        raise ValueError(f"{label} must be bounded plain ASCII text")
    return value


def _markup(value: str) -> str:
    return escape(value, quote=True)


def _python_setup_version(job: dict[str, Any], *, job_label: str) -> object:
    steps = job.get("steps")
    if not isinstance(steps, list):
        raise TypeError(f"case-study CI {job_label} steps must be a list")
    setup_steps = [
        step for step in steps if isinstance(step, dict) and step.get("name") == "Set up Python"
    ]
    if len(setup_steps) != 1:
        raise ValueError(f"case-study CI {job_label} job must define one Python setup step")
    setup_step = setup_steps[0]
    setup_inputs = setup_step.get("with")
    if (
        set(setup_step) != {"name", "uses", "with"}
        or setup_step.get("uses") != EXPECTED_SETUP_PYTHON_ACTION
        or not isinstance(setup_inputs, dict)
        or set(setup_inputs) != {"cache", "python-version"}
        or setup_inputs.get("cache") != "pip"
    ):
        raise ValueError(
            f"case-study CI {job_label} job must use the exact unconditional setup-python step"
        )
    return setup_inputs.get("python-version")


def _validate_workflow_python_support(workflow: str, minimum: str, maximum: str) -> None:
    try:
        loaded: object = yaml.safe_load(workflow)
    except yaml.YAMLError as exc:
        raise ValueError(f"case-study CI workflow is invalid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise TypeError("case-study CI workflow must be a mapping")
    jobs = loaded.get("jobs")
    if not isinstance(jobs, dict):
        raise TypeError("case-study CI workflow jobs must be a mapping")
    compatibility = jobs.get("compatibility")
    quality = jobs.get("quality")
    if not isinstance(compatibility, dict) or not isinstance(quality, dict):
        raise TypeError("case-study CI workflow is missing compatibility or quality jobs")
    strategy = compatibility.get("strategy")
    if not isinstance(strategy, dict) or not isinstance(strategy.get("matrix"), dict):
        raise TypeError("case-study CI compatibility matrix is invalid")
    matrix = cast(dict[str, Any], strategy["matrix"])
    if "exclude" in matrix:
        raise ValueError("case-study CI compatibility matrix must not define exclusions")
    matrix_python = matrix.get("python")
    included = matrix.get("include")
    if (
        matrix_python != [minimum, maximum]
        or not isinstance(included, list)
        or not all(isinstance(entry, dict) for entry in included)
    ):
        raise ValueError("case-study supported-Python endpoints differ from the CI matrix")
    compatibility_python = _python_setup_version(compatibility, job_label="compatibility")
    if compatibility_python != "${{ matrix.python }}":
        raise ValueError(
            "case-study CI compatibility job must bind one Python setup step to matrix.python"
        )
    quality_python = _python_setup_version(quality, job_label="quality")
    configured_versions = {
        *cast(list[str], matrix_python),
        *(entry.get("python") for entry in cast(list[dict[str, Any]], included)),
        quality_python,
    }
    minimum_parts = minimum.split(".")
    maximum_parts = maximum.split(".")
    if (
        len(minimum_parts) != VERSION_COMPONENT_COUNT
        or len(maximum_parts) != VERSION_COMPONENT_COUNT
        or minimum_parts[0] != maximum_parts[0]
        or not all(part.isdigit() for part in (*minimum_parts, *maximum_parts))
    ):
        raise ValueError("case-study supported-Python range is invalid")
    expected_versions = {
        f"{minimum_parts[0]}.{minor}"
        for minor in range(int(minimum_parts[1]), int(maximum_parts[1]) + 1)
    }
    if configured_versions != expected_versions:
        raise ValueError("case-study configured Python versions do not cover the declared range")
    if hashlib.sha256(workflow.encode()).hexdigest() != EXPECTED_CI_WORKFLOW_SHA256:
        raise ValueError("case-study CI workflow differs from the exact authenticated contract")


def _validate_claim_sources(  # noqa: PLR0912,PLR0915 - validates every displayed evidence family
    ledger: dict[str, Any], evidence: dict[str, Any]
) -> None:
    claim_sources = ledger.get("claim_sources")
    if (
        not isinstance(claim_sources, list)
        or not all(isinstance(source, str) for source in claim_sources)
        or len(claim_sources) != len(set(claim_sources))
        or not all(_tracked_path(source).is_file() for source in claim_sources)
    ):
        raise ValueError("case-study claim-source inventory contains a missing or unsafe path")
    claim_source_set = set(claim_sources)
    expected_sources = {
        "tests": ("docs/qa/2026-08-31-local-test-audit.json", ("/test_run/passed",)),
        "coverage": (
            "docs/qa/2026-08-31-local-test-audit.json",
            ("/test_run/coverage_branch_aware_percent",),
        ),
        "property_examples": (
            "docs/qa/2026-08-31-local-test-audit.json",
            ("/property_examples/total",),
        ),
        "demo": (
            "docs/qa/2026-08-31-exact-rebuild.json",
            ("/pipeline/curated_target",),
        ),
        "changed_members": (
            "docs/qa/2026-08-31-exact-rebuild.json",
            ("/pipeline/curated_target/changed_parts",),
        ),
        "benchmark": (
            "benchmarks/results/2026-08-31-honest-showcase-ooxml-windows-python312.json",
            ("/median_ms", "/p95_ms"),
        ),
        "preview_units": (
            "docs/qa/2026-08-31-local-test-audit.json",
            ("/provider_preview/provider_units",),
        ),
        "preview_calls": (
            "docs/qa/2026-08-31-local-test-audit.json",
            ("/provider_preview/provider_calls",),
        ),
        "preview_source_context_chars": (
            "docs/qa/2026-08-31-local-test-audit.json",
            ("/provider_preview/source_context_characters",),
        ),
        "preview_request_chars": (
            "docs/qa/2026-08-31-local-test-audit.json",
            ("/provider_preview/request_characters",),
        ),
        "preview_largest_request_chars": (
            "docs/qa/2026-08-31-local-test-audit.json",
            ("/provider_preview/largest_request_characters",),
        ),
        "supported_python": (
            ".github/workflows/ci.yml",
            (
                "jobs.compatibility.strategy.matrix",
                "jobs.compatibility.steps[name=Set up Python].uses",
                "jobs.compatibility.steps[name=Set up Python].with.python-version",
                "jobs.quality.steps[name=Set up Python].uses",
                "jobs.quality.steps[name=Set up Python].with.python-version",
            ),
        ),
    }
    for key, (expected_source, expected_locations) in expected_sources.items():
        entry = evidence[key]
        if not isinstance(entry, dict):
            raise TypeError(f"case-study evidence {key!r} must be an object")
        if (
            entry.get("source") != expected_source
            or entry.get("source_locations") != list(expected_locations)
            or expected_source not in claim_source_set
        ):
            raise ValueError(f"case-study evidence {key!r} has an invalid source binding")
        scope = entry.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError(f"case-study evidence {key!r} must define a non-empty scope")

    integer_evidence = (
        "tests",
        "property_examples",
        "changed_members",
        "preview_units",
        "preview_calls",
        "preview_source_context_chars",
        "preview_request_chars",
        "preview_largest_request_chars",
    )
    for key in integer_evidence:
        entry = cast(dict[str, Any], evidence[key])
        value = entry.get("value")
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or entry.get("display") != f"{value:,}"
        ):
            raise ValueError(f"case-study integer evidence {key!r} is inconsistent")
    coverage_entry = cast(dict[str, Any], evidence["coverage"])
    coverage_value = coverage_entry.get("value_percent")
    if (
        not isinstance(coverage_value, (int, float))
        or isinstance(coverage_value, bool)
        or coverage_entry.get("display") != f"{coverage_value:.2f}%"
    ):
        raise ValueError("case-study coverage evidence is inconsistent")

    local_audit_payload = LOCAL_TEST_AUDIT_PATH.read_bytes()
    if hashlib.sha256(local_audit_payload).hexdigest() != LOCAL_TEST_AUDIT_SHA256:
        raise ValueError("case-study local-test audit differs from the pinned source contract")
    local_audit = _read_json_object(LOCAL_TEST_AUDIT_PATH, label="case-study local-test audit")
    if (
        local_audit.get("schema_version") != "pptrans.local-test-audit/v1"
        or local_audit.get("observed_date") != ledger.get("evidence_snapshot_date")
        or local_audit.get("git_commit") != ledger.get("verification_commit")
        or local_audit.get("git_dirty") is not False
    ):
        raise ValueError("case-study local-test audit is not bound to the verification snapshot")
    test_run = local_audit.get("test_run")
    property_examples = local_audit.get("property_examples")
    preview = local_audit.get("provider_preview")
    if (
        not isinstance(test_run, dict)
        or not isinstance(property_examples, dict)
        or not isinstance(preview, dict)
    ):
        raise TypeError("case-study local-test audit has an invalid evidence contract")
    if (
        cast(dict[str, Any], evidence["tests"]).get("value") != test_run.get("passed")
        or cast(dict[str, Any], evidence["coverage"]).get("value_percent")
        != test_run.get("coverage_branch_aware_percent")
        or not isinstance(test_run.get("skipped"), int)
        or isinstance(test_run.get("skipped"), bool)
        or cast(int, test_run["skipped"]) < 0
    ):
        raise ValueError("case-study test and coverage evidence differs from the local audit")
    configured_examples = property_examples.get("configured_examples")
    property_source = property_examples.get("source")
    property_source_path = _tracked_path(property_source)
    configured_in_source = [
        int(match.replace("_", ""))
        for match in re.findall(
            r"@settings\(max_examples=([0-9_]+)",
            property_source_path.read_text(encoding="utf-8"),
        )
    ]
    if (
        property_source != "tests/test_properties.py"
        or not isinstance(configured_examples, list)
        or not configured_examples
        or not all(
            isinstance(count, int) and not isinstance(count, bool) and count > 0
            for count in configured_examples
        )
        or sum(cast(list[int], configured_examples)) != property_examples.get("total")
        or configured_examples != configured_in_source
        or cast(dict[str, Any], evidence["property_examples"]).get("value")
        != property_examples.get("total")
        or property_examples.get("deterministic") is not True
    ):
        raise ValueError("case-study property-example evidence differs from the local audit")
    preview_bindings = {
        "preview_units": "provider_units",
        "preview_calls": "provider_calls",
        "preview_source_context_chars": "source_context_characters",
        "preview_request_chars": "request_characters",
        "preview_largest_request_chars": "largest_request_characters",
    }
    if any(
        cast(dict[str, Any], evidence[ledger_key]).get("value") != preview.get(audit_key)
        for ledger_key, audit_key in preview_bindings.items()
    ):
        raise ValueError("case-study provider-preview evidence differs from the local audit")
    request_characters_per_call = preview.get("request_characters_per_call")
    source_deck = REPO_ROOT / "examples" / "pptrans-demo.en.pptx"
    if (
        not isinstance(request_characters_per_call, list)
        or not all(
            isinstance(count, int) and not isinstance(count, bool) and count >= 0
            for count in request_characters_per_call
        )
        or len(request_characters_per_call) != preview.get("provider_calls")
        or sum(cast(list[int], request_characters_per_call)) != preview.get("request_characters")
        or max(cast(list[int], request_characters_per_call), default=0)
        != preview.get("largest_request_characters")
        or preview.get("assumes_zero_memory_hits") is not True
        or preview.get("warnings") != []
        or preview.get("source_sha256") != hashlib.sha256(source_deck.read_bytes()).hexdigest()
    ):
        raise ValueError("case-study provider-preview audit is internally inconsistent")

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    readme_claims = (
        f"{_evidence_display(evidence, 'tests')} passing tests",
        f"{_evidence_display(evidence, 'coverage')} combined branch-aware coverage",
        f"{_evidence_display(evidence, 'property_examples')} generated property examples",
        (
            f"{_evidence_display(evidence, 'preview_units')} provider units in "
            f"{_evidence_display(evidence, 'preview_calls')} logical calls, "
            f"{_evidence_display(evidence, 'preview_source_context_chars')} source/context "
            f"characters, {_evidence_display(evidence, 'preview_request_chars')} serialized "
            f"request characters, and "
            f"{_evidence_display(evidence, 'preview_largest_request_chars')} characters"
        ),
    )
    missing_readme_claims = [claim for claim in readme_claims if claim not in readme]
    if missing_readme_claims:
        raise ValueError(f"case-study README claim binding failed: {missing_readme_claims}")

    benchmark = _read_json_object(
        REPO_ROOT
        / "benchmarks"
        / "results"
        / "2026-08-31-honest-showcase-ooxml-windows-python312.json",
        label="case-study benchmark source",
    )
    samples = benchmark.get("samples_ms")
    iterations = benchmark.get("iterations")
    if (
        benchmark.get("schema_version") != "pptrans.core-benchmark/v2"
        or benchmark.get("git_dirty") is not False
        or benchmark.get("warmups") != BENCHMARK_WARMUPS
        or iterations != BENCHMARK_ITERATIONS
        or not isinstance(samples, list)
        or len(samples) != iterations
        or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
            for value in samples
        )
        or benchmark.get("input_sha256") != hashlib.sha256(source_deck.read_bytes()).hexdigest()
        or benchmark.get("input_bytes") != source_deck.stat().st_size
        or benchmark.get("python_version") != "3.12.13"
        or not str(benchmark.get("operating_system", "")).startswith("Windows-11-")
    ):
        raise ValueError("case-study benchmark source has an invalid provenance contract")
    numeric_samples = [float(value) for value in samples]
    ordered_samples = sorted(numeric_samples)
    p95_index = max(0, min(len(ordered_samples) - 1, round((len(ordered_samples) - 1) * 0.95)))
    expected_summary = {
        "median_ms": round(statistics.median(numeric_samples), 3),
        "p95_ms": round(ordered_samples[p95_index], 3),
        "minimum_ms": min(numeric_samples),
        "maximum_ms": max(numeric_samples),
    }
    if any(benchmark.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("case-study benchmark summary differs from its measured samples")
    expected_benchmark = f"{benchmark['median_ms']:.3f} / {benchmark['p95_ms']:.3f} ms"
    benchmark_entry = cast(dict[str, Any], evidence["benchmark"])
    if (
        _evidence_display(evidence, "benchmark") != expected_benchmark
        or benchmark_entry.get("median_ms") != benchmark.get("median_ms")
        or benchmark_entry.get("p95_ms") != benchmark.get("p95_ms")
    ):
        raise ValueError("case-study benchmark display differs from the raw result")

    demo_qa = _read_json_object(
        REPO_ROOT / "docs" / "qa" / "2026-08-31-exact-rebuild.json",
        label="case-study exact-rebuild source",
    )
    pipeline = demo_qa.get("pipeline")
    renderer = demo_qa.get("renderer")
    slides = demo_qa.get("slides")
    if (
        not isinstance(pipeline, dict)
        or not isinstance(renderer, dict)
        or not isinstance(slides, list)
    ):
        raise TypeError("case-study exact-rebuild source has an invalid evidence contract")
    curated = pipeline.get("curated_target")
    if not isinstance(curated, dict) or not isinstance(curated.get("changed_parts"), list):
        raise TypeError("case-study curated-target source has an invalid evidence contract")
    if (
        preview.get("slides") != len(slides)
        or preview.get("translation_units") != curated.get("verified_patches")
        or preview.get("translatable_spans") != curated.get("verified_spans")
        or preview.get("provider_units") != curated.get("verified_patches")
        or preview.get("provider_calls") != curated.get("provider_calls")
        or benchmark.get("slides") != len(slides)
        or benchmark.get("translation_units") != curated.get("verified_patches")
        or benchmark.get("translated_spans") != curated.get("verified_spans")
    ):
        raise ValueError("case-study workload evidence differs from the exact-rebuild record")
    expected_demo = f"{len(slides)} / {curated['verified_patches']} / {curated['verified_spans']}"
    if _evidence_display(evidence, "demo") != expected_demo:
        raise ValueError("case-study demo display differs from the exact-rebuild record")
    demo_entry = cast(dict[str, Any], evidence["demo"])
    if (
        demo_entry.get("slides") != len(slides)
        or demo_entry.get("translation_units") != curated.get("verified_patches")
        or demo_entry.get("translated_spans") != curated.get("verified_spans")
    ):
        raise ValueError("case-study demo numeric evidence differs from the exact-rebuild record")
    if _evidence_display(evidence, "changed_members") != str(len(curated["changed_parts"])):
        raise ValueError("case-study changed-member display differs from the exact-rebuild record")

    visual_inputs = ledger.get("visual_inputs")
    if not isinstance(visual_inputs, dict):
        raise TypeError("case-study visual-input contract must be an object")
    expected_renderer = f"LibreOffice {renderer['libreoffice_version']}"
    if visual_inputs.get("renderer") != expected_renderer:
        raise ValueError("case-study renderer display differs from the exact-rebuild record")

    supported = evidence["supported_python"]
    if not isinstance(supported, dict):
        raise TypeError("case-study supported-Python evidence must be an object")
    minimum = supported.get("minimum")
    maximum = supported.get("maximum")
    expected_python_display = f"{minimum}-{maximum}"
    if supported.get("display") != expected_python_display:
        raise ValueError("case-study supported-Python display is internally inconsistent")
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    maximum_parts = str(maximum).split(".")
    if len(maximum_parts) != VERSION_COMPONENT_COUNT or not all(
        part.isdigit() for part in maximum_parts
    ):
        raise ValueError("case-study maximum Python version is invalid")
    next_minor = f"{maximum_parts[0]}.{int(maximum_parts[1]) + 1}"
    expected_python_constraint = f'requires-python = ">={minimum},<{next_minor}"'
    if expected_python_constraint not in pyproject:
        raise ValueError("case-study supported-Python range differs from pyproject.toml")
    _validate_workflow_python_support(workflow, str(minimum), str(maximum))


def _load_ledger() -> dict[str, Any]:
    ledger = _read_json_object(LEDGER_PATH, label="case-study claim ledger")
    if ledger.get("schema_version") != "pptrans.engineering-case-study/v1":
        raise ValueError("unsupported case-study claim-ledger schema")
    snapshot_date = ledger.get("evidence_snapshot_date")
    if (
        not isinstance(snapshot_date, str)
        or len(snapshot_date) != ISO_DATE_LENGTH
        or snapshot_date[4] != "-"
        or snapshot_date[7] != "-"
    ):
        raise ValueError("case-study evidence snapshot must use YYYY-MM-DD")
    verification_commit = ledger.get("verification_commit")
    if (
        not isinstance(verification_commit, str)
        or len(verification_commit) != GIT_SHA1_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in verification_commit)
    ):
        raise ValueError("case-study verification commit must be a full lowercase SHA-1")
    evidence = ledger.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != REQUIRED_EVIDENCE_KEYS:
        raise ValueError("case-study claim ledger has an unexpected evidence inventory")
    for key, entry in evidence.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("display"), str):
            raise TypeError(f"case-study evidence {key!r} must define a display string")
        _validate_plain_ledger_text(f"case-study evidence {key!r}", entry["display"])
    _validate_claim_sources(ledger, cast(dict[str, Any], evidence))
    visual_inputs = ledger.get("visual_inputs")
    if not isinstance(visual_inputs, dict):
        raise TypeError("case-study visual-input contract must be an object")
    _validate_plain_ledger_text("case-study renderer", visual_inputs.get("renderer"))
    return ledger


LEDGER = _load_ledger()
EVIDENCE = {
    key: cast(str, cast(dict[str, Any], LEDGER["evidence"])[key]["display"])
    for key in sorted(REQUIRED_EVIDENCE_KEYS)
}
SNAPSHOT_DATE = cast(str, LEDGER["evidence_snapshot_date"])
VERIFICATION_COMMIT = cast(str, LEDGER["verification_commit"])
VISUAL_INPUTS = cast(dict[str, Any], LEDGER["visual_inputs"])
SOURCE_RENDER = _tracked_path(cast(dict[str, Any], VISUAL_INPUTS["source_render"])["path"])
TARGET_RENDER = _tracked_path(cast(dict[str, Any], VISUAL_INPUTS["target_render"])["path"])
RENDERER = cast(str, VISUAL_INPUTS["renderer"])


def _style(
    name: str,
    *,
    size: float,
    leading: float,
    color: Color = INK,
    bold: bool = False,
    alignment: int = TA_LEFT,
) -> ParagraphStyle:
    return ParagraphStyle(
        name,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size,
        leading=leading,
        textColor=color,
        alignment=alignment,
        spaceAfter=0,
        spaceBefore=0,
    )


BODY = _style("body", size=8.2, leading=10.7)
BODY_SMALL = _style("body-small", size=7.4, leading=9.3, color=MUTED)
SECTION = _style("section", size=10.2, leading=12.2, color=NAVY, bold=True)
CARD_VALUE = _style(
    "card-value", size=12.3, leading=13.8, color=NAVY, bold=True, alignment=TA_CENTER
)
CARD_LABEL = _style(
    "card-label", size=6.8, leading=8.1, color=MUTED, bold=True, alignment=TA_CENTER
)


def _draw_paragraph(  # noqa: PLR0917 - compact primitive keeps page composition readable
    canvas: Canvas,
    text: str,
    style: ParagraphStyle,
    x: float,
    top: float,
    width: float,
) -> float:
    paragraph = Paragraph(text, style)
    _, wrapped_height = paragraph.wrap(width, PAGE_HEIGHT)
    height = float(wrapped_height)
    paragraph.drawOn(canvas, x, top - height)
    return height


def _draw_bullet(
    canvas: Canvas,
    text: str,
    *,
    x: float,
    top: float,
    width: float,
    color: Color = TEAL,
) -> float:
    canvas.setFillColor(color)
    canvas.circle(x + 3.2, top - 5.5, 2.2, fill=1, stroke=0)
    height = _draw_paragraph(canvas, text, BODY, x + 11, top, width - 11)
    return max(height, 11)


def _draw_image_card(
    canvas: Canvas,
    path: Path,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
) -> None:
    canvas.setFillColor(WHITE)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.7)
    canvas.roundRect(x, y, width, height, 5, fill=1, stroke=1)

    image = ImageReader(path)
    image_width, image_height = image.getSize()
    scale = min((width - 4) / image_width, (height - 4) / image_height)
    rendered_width = image_width * scale
    rendered_height = image_height * scale
    canvas.drawImage(
        image,
        x + (width - rendered_width) / 2,
        y + (height - rendered_height) / 2,
        rendered_width,
        rendered_height,
        preserveAspectRatio=True,
        mask="auto",
    )

    canvas.setFillColor(NAVY)
    canvas.roundRect(x + 8, y + height - 20, 79, 13, 4, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 6.3)
    canvas.drawString(x + 13, y + height - 16.2, label)


def _draw_pipeline(canvas: Canvas, *, x: float, y: float, width: float, height: float) -> None:
    steps = (
        ("1", "DEFEND", "ZIP + XML"),
        ("2", "PLAN", "STABLE IDS"),
        ("3", "VALIDATE", "AI OUTPUT"),
        ("4", "PATCH", "STAGED COPY"),
        ("5", "VERIFY", "ALL CHANGES"),
        ("6", "PUBLISH", "ATOMICALLY"),
    )
    step_width = width / len(steps)
    canvas.setFillColor(PALE_BLUE)
    canvas.roundRect(x, y, width, height, 7, fill=1, stroke=0)
    for index, (number, title, subtitle) in enumerate(steps):
        left = x + index * step_width
        if index:
            canvas.setStrokeColor(Color(0.58, 0.70, 0.82, alpha=1))
            canvas.setLineWidth(0.6)
            canvas.line(left, y + 8, left, y + height - 8)
        canvas.setFillColor(BLUE if index < FINAL_PIPELINE_STEP_INDEX else TEAL)
        canvas.circle(left + 13, y + height / 2, 8.2, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawCentredString(left + 13, y + height / 2 - 2.4, number)
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 6.7)
        canvas.drawString(left + 25, y + height / 2 + 2.2, title)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 5.6)
        canvas.drawString(left + 25, y + height / 2 - 6.1, subtitle)


def _draw_metric_card(
    canvas: Canvas,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    value: str,
    label: str,
) -> None:
    canvas.setFillColor(WHITE)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.roundRect(x, y, width, height, 6, fill=1, stroke=1)
    _draw_paragraph(canvas, _markup(value), CARD_VALUE, x + 4, y + height - 9, width - 8)
    _draw_paragraph(canvas, label, CARD_LABEL, x + 5, y + 18, width - 10)


def _draw_document(canvas: Canvas) -> None:  # noqa: PLR0915 - explicit one-page composition
    margin = 36
    content_width = PAGE_WIDTH - 2 * margin

    canvas.setTitle("PPTrans Engineering Case Study")
    canvas.setAuthor("Hehan Zhao")
    canvas.setSubject("One-page PPTrans v2 engineering showcase with verified package integrity")
    canvas.setCreator("scripts/build_case_study.py")
    canvas.setKeywords("PPTrans, PowerPoint, OOXML, translation, Python, case study")

    # Header.
    canvas.setFillColor(NAVY)
    canvas.rect(0, 732, PAGE_WIDTH, PAGE_HEIGHT - 732, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, 732, 7, PAGE_HEIGHT - 732, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 25)
    canvas.drawString(margin, 804, "PPTrans")
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(margin, 785, "PowerPoint translation with verified package integrity")
    canvas.setFillColor(HexColor("#B9C9D8"))
    canvas.setFont("Helvetica", 7.4)
    canvas.drawString(
        margin,
        769,
        f"HEHAN ZHAO  |  ENGINEERING CASE STUDY  |  EVIDENCE SNAPSHOT {SNAPSHOT_DATE}",
    )

    canvas.setFillColor(PALE_AMBER)
    canvas.roundRect(PAGE_WIDTH - margin - 137, 797, 137, 24, 12, fill=1, stroke=0)
    canvas.setFillColor(AMBER)
    canvas.setFont("Helvetica-Bold", 7.3)
    canvas.drawCentredString(PAGE_WIDTH - margin - 68.5, 806.2, "V2 LOCAL / UNRELEASED")

    canvas.setFillColor(HexColor("#B9C9D8"))
    canvas.setFont("Helvetica-Bold", 7.3)
    canvas.drawString(
        margin,
        746,
        "DEFENSIVE OOXML  |  STRICT AI CONTRACTS  |  TRANSACTIONAL OUTPUT",
    )

    # Product thesis and visual proof.
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 13.2)
    canvas.drawString(
        margin,
        709,
        "Change the intended text nodes - and prove everything else stayed within plan.",
    )
    _draw_paragraph(
        canvas,
        "PPTrans turns translation into a source-bound transaction across untrusted OOXML "
        "and AI output.",
        _style("thesis", size=8.6, leading=10.6, color=MUTED),
        margin,
        694,
        content_width,
    )

    card_y = 531
    card_height = 145
    card_gap = 13
    card_width = (content_width - card_gap) / 2
    _draw_image_card(
        canvas,
        SOURCE_RENDER,
        x=margin,
        y=card_y,
        width=card_width,
        height=card_height,
        label="ENGLISH SOURCE",
    )
    _draw_image_card(
        canvas,
        TARGET_RENDER,
        x=margin + card_width + card_gap,
        y=card_y,
        width=card_width,
        height=card_height,
        label="CURATED ZH-CN",
    )
    _draw_paragraph(
        canvas,
        "Real changed-text fixture through the exact-ID patch and verification path. "
        f"Native {_markup(RENDERER)} renders; this is not provider-quality evidence.",
        _style("visual-caption", size=7.2, leading=8.7, color=MUTED, alignment=TA_CENTER),
        margin,
        524,
        content_width,
    )

    _draw_pipeline(canvas, x=margin, y=459, width=content_width, height=42)

    # Two-column engineering summary.
    gap = 17
    column_width = (content_width - gap) / 2
    left_x = margin
    right_x = margin + column_width + gap

    _draw_paragraph(canvas, "WHAT I ENGINEERED", SECTION, left_x, 444, column_width)
    bullet_top = 424.0
    bullets = (
        "Led v2 product direction and the end-to-end re-architecture around immutable "
        "<b>DeckPlan</b> and <b>PatchSet</b> contracts.",
        "Built defensive ZIP/XML intake, source-hash binding, stable text addresses, and "
        "explicit support and resource limits.",
        "Made OpenAI and Anthropic adapters fail closed on partial, reordered, duplicated, "
        "invented, or schema-invalid IDs.",
        "Added staged patching, planned-and-untouched text verification, package checks, and "
        "atomic no-clobber publication.",
    )
    for bullet in bullets:
        consumed = _draw_bullet(
            canvas,
            bullet,
            x=left_x,
            top=bullet_top,
            width=column_width,
        )
        bullet_top -= consumed + 7

    preview_top = 268
    preview_height = 126
    canvas.setFillColor(PALE_TEAL)
    canvas.roundRect(
        left_x, preview_top - preview_height, column_width, preview_height, 7, fill=1, stroke=0
    )
    canvas.setFillColor(TEAL)
    canvas.rect(left_x, preview_top - preview_height, 4, preview_height, fill=1, stroke=0)
    _draw_paragraph(
        canvas,
        "NO-SPEND PROVIDER PREVIEW",
        _style("preview-title", size=8.4, leading=10, color=NAVY, bold=True),
        left_x + 13,
        preview_top - 10,
        column_width - 25,
    )
    _draw_paragraph(
        canvas,
        f"<b>{_markup(EVIDENCE['preview_units'])} units</b> in "
        f"<b>{_markup(EVIDENCE['preview_calls'])} logical calls</b> | "
        f"{_markup(EVIDENCE['preview_source_context_chars'])} source/context chars | "
        f"{_markup(EVIDENCE['preview_request_chars'])} serialized request chars | "
        f"largest {_markup(EVIDENCE['preview_largest_request_chars'])}",
        _style("preview-metrics", size=8.1, leading=10.4, color=INK),
        left_x + 13,
        preview_top - 29,
        column_width - 25,
    )
    _draw_paragraph(
        canvas,
        "Zero-memory-hit upper bounds. The preview loads no credential, provider SDK, "
        "translation memory, or output path and makes no provider/API request. Counts are "
        "not tokens, price, latency, availability, or quality estimates.",
        BODY_SMALL,
        left_x + 13,
        preview_top - 71,
        column_width - 25,
    )

    _draw_paragraph(canvas, "MEASURED EVIDENCE", SECTION, right_x, 444, column_width)
    metrics = (
        (EVIDENCE["tests"], "PASSING TESTS"),
        (EVIDENCE["coverage"], "BRANCH-AWARE COVERAGE"),
        (EVIDENCE["property_examples"], "GENERATED EXAMPLES"),
        (EVIDENCE["demo"], "SLIDES / UNITS / SPANS"),
        (EVIDENCE["changed_members"], "CHANGED SLIDE XML PARTS"),
        (EVIDENCE["benchmark"], "MEDIAN / P95 LOCAL CORE"),
    )
    metric_gap = 7
    metric_width = (column_width - metric_gap) / 2
    metric_height = 52
    metric_top = 425
    for index, (value, label) in enumerate(metrics):
        row = index // 2
        column = index % 2
        _draw_metric_card(
            canvas,
            x=right_x + column * (metric_width + metric_gap),
            y=metric_top - (row + 1) * metric_height - row * metric_gap,
            width=metric_width,
            height=metric_height,
            value=value,
            label=label,
        )

    _draw_paragraph(
        canvas,
        "EVIDENCE BOUNDARY",
        _style("boundary-title", size=8.4, leading=10, color=NAVY, bold=True),
        right_x,
        245,
        column_width,
    )
    boundary_top = 228.0
    boundaries = (
        "The synthetic, author-reviewed zh-CN deck proves changed text and package "
        "preservation, not production-provider translation quality.",
        "The benchmark covers the deterministic local core only; it excludes provider, "
        "network, memory, rendering, cost, and translation-quality time.",
        "LibreOffice evidence does not claim Microsoft PowerPoint pixel identity, automatic "
        "layout fit, universal compatibility, or maximum practical deck size.",
    )
    for boundary in boundaries:
        consumed = _draw_bullet(
            canvas,
            boundary,
            x=right_x,
            top=boundary_top,
            width=column_width,
            color=AMBER,
        )
        boundary_top -= consumed + 6

    # Status and provenance footer.
    footer_y = 38
    footer_height = 83
    canvas.setFillColor(PALE_AMBER)
    canvas.roundRect(margin, footer_y, content_width, footer_height, 7, fill=1, stroke=0)
    canvas.setFillColor(AMBER)
    canvas.rect(margin, footer_y, 4, footer_height, fill=1, stroke=0)
    _draw_paragraph(
        canvas,
        "STATUS AND PROVENANCE",
        _style("status-title", size=8.2, leading=9.8, color=NAVY, bold=True),
        margin + 13,
        footer_y + footer_height - 10,
        content_width - 26,
    )
    _draw_paragraph(
        canvas,
        "PPTrans v2 is an <b>unreleased, non-public local engineering showcase</b>. The "
        "public main branch is legacy and is intentionally not linked here. Repository "
        "history is not presented as clean-room work; another package or release remains "
        "blocked pending upstream provenance/licensing clarification documented in NOTICE.md.",
        _style("status-body", size=7.5, leading=9.5, color=INK),
        margin + 13,
        footer_y + footer_height - 28,
        content_width - 26,
    )
    _draw_paragraph(
        canvas,
        f"Configured Python support: {_markup(EVIDENCE['supported_python'])} | Skills: OOXML/XML | "
        "typed domain design | "
        "schema-bound LLM adapters | transactional I/O | property testing | CI and security",
        _style("skills", size=7.0, leading=8.5, color=MUTED, bold=True),
        margin + 13,
        footer_y + 22,
        content_width - 26,
    )

    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.6)
    canvas.drawString(
        margin,
        20,
        "Evidence basis: "
        f"{VERIFICATION_COMMIT[:7]} | local-test audit JSON | exact-rebuild QA JSON | "
        "raw benchmark JSON | CI matrix | NOTICE.md",
    )
    canvas.drawRightString(PAGE_WIDTH - margin, 20, "1 / 1")


def _validate_visual_input(path: Path, record: object) -> None:
    if not isinstance(record, dict):
        raise TypeError("case-study visual-input record must be an object")
    expected = record.get("sha256")
    if not isinstance(expected, str) or len(expected) != SHA256_HEX_LENGTH:
        raise ValueError("case-study visual input must define a SHA-256 digest")
    if not path.is_file():
        raise FileNotFoundError(f"missing case-study render: {path}")
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != expected:
        raise ValueError(f"case-study render hash mismatch: {path.relative_to(REPO_ROOT)}")


def _audit_pdf_object_graph(  # noqa: PLR0912 - exhaustive recursive PDF safety walk
    roots: Sequence[tuple[object, str]],
    expected_objects: frozenset[tuple[int, int]],
) -> tuple[tuple[str, ...], frozenset[tuple[int, int]]]:
    """Audit the complete PDF graph and return findings plus reachable object identities."""

    pending = list(roots)
    seen_indirect: set[tuple[int, int]] = set()
    seen_containers: set[int] = set()
    findings: set[str] = set()
    while pending:
        current, location = pending.pop()
        if isinstance(current, IndirectObject):
            indirect_identity = (current.idnum, current.generation)
            if indirect_identity in seen_indirect:
                continue
            if indirect_identity not in expected_objects:
                raise ValueError(
                    "case-study PDF references an object absent from the frozen xref inventory: "
                    f"{indirect_identity} at {location}"
                )
            seen_indirect.add(indirect_identity)
            pending.append((current.get_object(), location))
            continue
        if isinstance(current, DictionaryObject):
            container_identity = id(current)
            if container_identity in seen_containers:
                continue
            seen_containers.add(container_identity)
            for key in FORBIDDEN_PDF_INTERACTIVE_KEYS.intersection(current):
                findings.add(f"{location}{key}")
            action_type = current.get("/S")
            if isinstance(action_type, IndirectObject):
                action_type = action_type.get_object()
            if str(action_type) in FORBIDDEN_PDF_ACTION_TYPES:
                findings.add(f"{location}/S={action_type}")
            object_type = current.get("/Type")
            if isinstance(object_type, IndirectObject):
                object_type = object_type.get_object()
            if str(object_type) in FORBIDDEN_PDF_OBJECT_TYPES:
                findings.add(f"{location}/Type={object_type}")
            pending.extend((value, f"{location}{key}") for key, value in current.items())
        elif isinstance(current, ArrayObject):
            container_identity = id(current)
            if container_identity in seen_containers:
                continue
            seen_containers.add(container_identity)
            pending.extend((value, f"{location}[{index}]") for index, value in enumerate(current))
    return tuple(sorted(findings)), frozenset(seen_indirect)


def _in_use_pdf_objects(reader: PdfReader) -> frozenset[tuple[int, int]]:
    """Return every in-use object identity declared by classic or compressed xrefs."""

    traditional = {
        (int(object_id), int(generation))
        for generation, entries in reader.xref.items()
        for object_id in entries
        if not reader.xref_free_entry.get(generation, {}).get(object_id, False)
    }
    compressed = {(int(object_id), 0) for object_id in reader.xref_objStm}
    if any(object_id <= 0 for object_id, _generation in traditional | compressed):
        raise ValueError("case-study PDF xref contains a nonpositive in-use object identifier")
    traditional_ids = [object_id for object_id, _generation in traditional]
    if len(traditional_ids) != len(set(traditional_ids)):
        raise ValueError("case-study PDF xref repeats an object identifier across generations")
    if set(traditional_ids) & {object_id for object_id, _generation in compressed}:
        raise ValueError("case-study PDF xref duplicates classic and compressed object identities")
    if compressed:
        raise ValueError("case-study PDF must not use compressed object streams")
    if not traditional:
        raise ValueError("case-study PDF xref must contain in-use objects")
    return frozenset(traditional)


def _validate_pdf_object_inventory(
    reader: PdfReader,
    expected_objects: frozenset[tuple[int, int]],
) -> None:
    observed_trailer_keys = {str(key) for key in reader.trailer}
    if (
        not observed_trailer_keys >= REQUIRED_PDF_TRAILER_KEYS
        or not observed_trailer_keys <= ALLOWED_PDF_TRAILER_KEYS
    ):
        raise ValueError(
            "case-study PDF trailer differs from the safe allowlist: "
            f"{sorted(observed_trailer_keys)}"
        )
    raw_root = reader.trailer.raw_get("/Root")
    raw_info = reader.trailer.raw_get("/Info")
    identifier = reader.trailer.raw_get("/ID")
    if (
        not isinstance(identifier, ArrayObject)
        or len(identifier) != PDF_ID_COMPONENT_COUNT
        or any(
            not isinstance(value, TextStringObject) or value.original_bytes != EXPECTED_PDF_ID_BYTES
            for value in identifier
        )
    ):
        raise ValueError("case-study PDF trailer ID differs from the exact safe value")
    if not isinstance(raw_root, IndirectObject) or not isinstance(raw_info, IndirectObject):
        raise TypeError("case-study PDF trailer Root and Info must be indirect objects")
    root_identity = (raw_root.idnum, raw_root.generation)
    info_identity = (raw_info.idnum, raw_info.generation)
    if root_identity not in expected_objects or info_identity not in expected_objects:
        raise ValueError("case-study PDF trailer roots are absent from the frozen xref inventory")

    root = raw_root.get_object()
    if not isinstance(root, DictionaryObject):
        raise TypeError("case-study PDF trailer Root must resolve to a dictionary")
    observed_root_keys = {str(key) for key in root}
    if observed_root_keys != EXPECTED_PDF_ROOT_KEYS:
        raise ValueError(
            "case-study PDF catalog differs from the exact safe allowlist: "
            f"{sorted(observed_root_keys)}"
        )
    raw_type = root.raw_get("/Type")
    raw_page_mode = root.raw_get("/PageMode")
    raw_pages = root.raw_get("/Pages")
    if (
        not isinstance(raw_type, NameObject)
        or str(raw_type) != "/Catalog"
        or not isinstance(raw_page_mode, NameObject)
        or str(raw_page_mode) != "/UseNone"
        or not isinstance(raw_pages, IndirectObject)
        or (raw_pages.idnum, raw_pages.generation) not in expected_objects
    ):
        raise ValueError("case-study PDF catalog scalar values differ from the exact safe contract")
    forbidden_interactions, reachable_objects = _audit_pdf_object_graph(
        ((raw_root, "/Trailer/Root"), (raw_info, "/Trailer/Info")),
        expected_objects,
    )
    if forbidden_interactions:
        raise ValueError(
            f"case-study PDF has forbidden actions or interactive entries: {forbidden_interactions}"
        )
    unreachable_objects = sorted(expected_objects - reachable_objects)
    unknown_objects = sorted(reachable_objects - expected_objects)
    if unreachable_objects or unknown_objects:
        raise ValueError(
            "case-study PDF object inventory is not an exact reachable graph: "
            f"unreachable={unreachable_objects}, unknown={unknown_objects}"
        )
    declared_size = reader.trailer.get("/Size")
    expected_size = max(object_id for object_id, _generation in expected_objects) + 1
    if not isinstance(declared_size, int) or int(declared_size) != expected_size:
        raise ValueError("case-study PDF trailer Size differs from the exact object inventory")


def _validate_pdf(payload: bytes) -> None:
    reader = PdfReader(io.BytesIO(payload), strict=True)
    expected_objects = _in_use_pdf_objects(reader)
    startxref = reader._startxref
    if not isinstance(startxref, int) or payload[startxref : startxref + 4] != b"xref":
        raise ValueError("case-study PDF must use a classic cross-reference table")
    if reader.is_encrypted:
        raise ValueError("case-study PDF must not be encrypted")
    if len(reader.pages) != 1:
        raise ValueError("case-study PDF must contain exactly one page")

    page = reader.pages[0]
    media_box = page.mediabox
    observed_size = (float(media_box.width), float(media_box.height))
    if any(
        abs(actual - expected) > PDF_POINT_TOLERANCE
        for actual, expected in zip(observed_size, A4, strict=True)
    ):
        raise ValueError(f"case-study PDF must use A4 media box, got {observed_size!r}")

    metadata = reader.metadata
    observed_metadata = (
        None if metadata is None else {str(key): str(value) for key, value in metadata.items()}
    )
    if observed_metadata != EXPECTED_PDF_METADATA:
        raise ValueError("case-study PDF metadata differs from the exact safe allowlist")

    _validate_pdf_object_inventory(reader, expected_objects)

    text = page.extract_text() or ""
    required_text = (
        "PPTrans",
        "V2 LOCAL / UNRELEASED",
        "WHAT I ENGINEERED",
        "NO-SPEND PROVIDER PREVIEW",
        "MEASURED EVIDENCE",
        "EVIDENCE BOUNDARY",
        "STATUS AND PROVENANCE",
        VERIFICATION_COMMIT[:7],
        EVIDENCE["tests"],
        EVIDENCE["coverage"],
        EVIDENCE["property_examples"],
    )
    missing_text = [fragment for fragment in required_text if fragment not in text]
    if missing_text:
        raise ValueError(f"case-study PDF is missing selectable text: {missing_text}")
    forbidden_text = ("http://", "https://", "file://", str(REPO_ROOT), "github.com/Z-MarkUs")
    present_text = [fragment for fragment in forbidden_text if fragment in text]
    if present_text:
        raise ValueError(f"case-study PDF exposes a forbidden destination: {present_text}")

    forbidden_action_tokens = (
        b"/JavaScript",
        b"/JS ",
        b"/Launch",
        b"/EmbeddedFile",
        b"/OpenAction",
        b"/URI",
    )
    present_tokens = [
        token.decode("ascii") for token in forbidden_action_tokens if token in payload
    ]
    if present_tokens:
        raise ValueError(f"case-study PDF contains forbidden action tokens: {present_tokens}")
    if payload.count(b"%%EOF") != 1 or not payload.endswith(b"%%EOF\n"):
        raise ValueError("case-study PDF must end exactly at its single EOF marker")
    if hashlib.sha256(payload).hexdigest() != EXPECTED_PDF_SHA256:
        raise ValueError("case-study PDF differs from the exact authenticated artifact")


def build_pdf_bytes() -> bytes:
    """Return deterministic PDF bytes for the current case study."""

    _validate_visual_input(SOURCE_RENDER, VISUAL_INPUTS["source_render"])
    _validate_visual_input(TARGET_RENDER, VISUAL_INPUTS["target_render"])

    buffer = io.BytesIO()
    canvas = Canvas(
        buffer,
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    _draw_document(canvas)
    canvas.showPage()
    canvas.save()
    payload = buffer.getvalue()
    _validate_pdf(payload)
    return payload


def write_case_study(output: Path) -> None:
    """Write the generated PDF atomically."""

    payload = build_pdf_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(output)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="PDF destination (default: output/pdf/PPTrans-Engineering-Case-Study.pdf)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless the destination is byte-identical to a fresh deterministic build",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build or verify the case study."""

    args = _parser().parse_args(argv)
    output = args.output.resolve()
    if args.check:
        if not output.is_file():
            print(f"case-study PDF is missing: {output}", file=sys.stderr)
            return 1
        expected = build_pdf_bytes()
        observed = output.read_bytes()
        if observed != expected:
            print(
                "case-study PDF differs from a fresh deterministic build; "
                "run scripts/build_case_study.py",
                file=sys.stderr,
            )
            return 1
        print(f"case-study PDF is current: {output}")
        return 0

    write_case_study(output)
    print(f"wrote case-study PDF: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
