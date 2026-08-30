"""Regression tests for repository tooling that writes user-selected paths."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    TextStringObject,
)
from test_ooxml_helpers import create_complex_deck

REPO_ROOT = Path(__file__).parents[1]
EXPECTED_SKILL_RESOURCES = {
    "pptrans-engineering": (
        "SKILL.md",
        "agents/openai.yaml",
        "references/architecture.md",
        "references/release.md",
        "references/verification.md",
    ),
    "pptrans-operator": (
        "SKILL.md",
        "agents/openai.yaml",
        "references/offline-operation.md",
        "references/provider-operation.md",
    ),
}
EXPECTED_PACKAGED_SKILL_RESOURCES = {
    f"{root}/skills/{skill_name}/{resource}"
    for root in (".agents", ".claude")
    for skill_name, resources in EXPECTED_SKILL_RESOURCES.items()
    for resource in resources
}


def _load_script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"test_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _demo_sdist_fixture(tmp_path: Path, mutation: str | None = None) -> Path:
    fixture_root = tmp_path / f"fixture-{mutation or 'valid'}"
    source = fixture_root / "examples" / "pptrans-demo.source"
    shutil.copytree(REPO_ROOT / "examples" / "pptrans-demo.source", source)
    deck = fixture_root / "examples" / "pptrans-demo.en.pptx"
    deck.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "examples" / "pptrans-demo.en.pptx", deck)

    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "payload":
        member = source.joinpath(*Path(manifest["entries"][0]["path"]).parts)
        payload = bytearray(member.read_bytes())
        payload[0] ^= 1
        member.write_bytes(payload)
    elif mutation == "entry":
        manifest["entries"][0] = "not-an-object"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    elif mutation == "archive":
        manifest["archive"]["compression"] = "deflated"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    elif mutation == "schema":
        manifest["schema_version"] = True
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    archive_path = tmp_path / f"pptrans-{mutation or 'valid'}.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        if mutation == "split_root":
            archive.add(
                manifest_path,
                arcname="pptrans-2.0/examples/pptrans-demo.source/manifest.json",
            )
            for member in source.rglob("*"):
                if member.is_file() and member != manifest_path:
                    relative = member.relative_to(source).as_posix()
                    archive.add(
                        member,
                        arcname=f"other-root/examples/pptrans-demo.source/{relative}",
                    )
            archive.add(deck, arcname="other-root/examples/pptrans-demo.en.pptx")
        else:
            archive.add(source, arcname="pptrans-2.0/examples/pptrans-demo.source")
            archive.add(deck, arcname="pptrans-2.0/examples/pptrans-demo.en.pptx")
    return archive_path


def _inspect_demo_fixture(checker: ModuleType, path: Path) -> tuple[str, ...]:
    with tarfile.open(path, mode="r:gz") as archive:
        archive_members = tuple(archive.getmembers())
        members = tuple(member.name.replace("\\", "/") for member in archive_members)
        return checker._demo_source_failures(archive, archive_members, members)


def _qa_sdist_fixture(tmp_path: Path, mutation: str | None = None) -> Path:
    fixture_root = tmp_path / f"qa-fixture-{mutation or 'valid'}"
    qa_relative = Path("docs/qa/2026-08-31-exact-rebuild.json")
    qa_path = fixture_root / qa_relative
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / qa_relative, qa_path)
    record = json.loads(qa_path.read_text(encoding="utf-8"))
    artifact_paths = {
        record["exact_rebuild"]["builder_path"],
        record["exact_rebuild"]["manifest_path"],
        record["pipeline"]["curated_target"]["builder_path"],
        record["renderer"]["replay_script_path"],
        record["presentations"]["source"]["path"],
        record["presentations"]["curated_target"]["path"],
    }
    for slide in record["slides"]:
        number = slide["slide_number"]
        artifact_paths.update(
            {
                f"docs/assets/pptrans-demo-libreoffice-en-slide-{number:02d}.png",
                f"docs/assets/pptrans-demo-libreoffice-zh-CN-slide-{number:02d}.png",
            }
        )
    for relative in artifact_paths:
        destination = fixture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)

    if mutation in {"target", "png"}:
        relative = (
            record["presentations"]["curated_target"]["path"]
            if mutation == "target"
            else "docs/assets/pptrans-demo-libreoffice-en-slide-01.png"
        )
        artifact = fixture_root / relative
        payload = bytearray(artifact.read_bytes())
        payload[-1] ^= 1
        artifact.write_bytes(payload)
    elif mutation == "record":
        record["scope"].append("tampered")
        qa_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    archive_path = tmp_path / f"pptrans-qa-{mutation or 'valid'}.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        archive.add(fixture_root, arcname="pptrans-2.0")
    return archive_path


def _packaged_builder_snapshot(tmp_path: Path, *, mutate_builder: bool = False) -> bytes:
    fixture_root = tmp_path / ("packaged-builder-mutated" if mutate_builder else "packaged-builder")
    source = fixture_root / "examples" / "pptrans-demo.source"
    shutil.copytree(REPO_ROOT / "examples" / "pptrans-demo.source", source)
    for relative in (
        "scripts/rebuild_demo.py",
        "docs/qa/2026-08-31-exact-rebuild.json",
        "examples/pptrans-demo.en.pptx",
    ):
        destination = fixture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)
    if mutate_builder:
        (fixture_root / "scripts" / "rebuild_demo.py").write_text(
            "raise RuntimeError('unpinned builder must not execute')\n",
            encoding="utf-8",
        )

    archive_path = tmp_path / f"packaged-builder-{'mutated' if mutate_builder else 'valid'}.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        archive.add(fixture_root, arcname="pptrans-2.0")
    return archive_path.read_bytes()


def _packaged_case_study_snapshot(
    tmp_path: Path,
    checker: ModuleType,
    *,
    mutate_builder: bool = False,
) -> bytes:
    fixture_root = tmp_path / (
        "packaged-case-study-mutated" if mutate_builder else "packaged-case-study"
    )
    for relative in checker.CASE_STUDY_PACKAGED_INPUTS:
        destination = fixture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)
    if mutate_builder:
        (fixture_root / "scripts" / "build_case_study.py").write_text(
            "raise RuntimeError('unpinned builder must not execute')\n",
            encoding="utf-8",
        )

    archive_path = tmp_path / (
        "packaged-case-study-mutated.tar.gz" if mutate_builder else "packaged-case-study.tar.gz"
    )
    with tarfile.open(archive_path, mode="w:gz") as archive:
        archive.add(fixture_root, arcname="pptrans-2.0")
    return archive_path.read_bytes()


def _inspect_qa_fixture(checker: ModuleType, path: Path) -> tuple[str, ...]:
    with tarfile.open(path, mode="r:gz") as archive:
        archive_members = tuple(archive.getmembers())
        members = tuple(member.name.replace("\\", "/") for member in archive_members)
        return checker._qa_evidence_failures(archive, archive_members, members)


def _case_study_sdist_fixture(tmp_path: Path, mutation: str | None = None) -> Path:
    fixture_root = tmp_path / f"case-study-fixture-{mutation or 'valid'}"
    qa_relative = Path("docs/qa/2026-08-31-case-study.json")
    qa_path = fixture_root / qa_relative
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / qa_relative, qa_path)
    record = json.loads(qa_path.read_text(encoding="utf-8"))
    contracts = (
        record["artifact"],
        record["source"]["builder"],
        record["source"]["claim_ledger"],
        record["source"]["local_test_audit"],
        record["source"]["benchmark_result"],
        record["source"]["ci_workflow"],
    )
    for contract in contracts:
        relative = contract["path"]
        destination = fixture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)

    mutation_paths = {
        "pdf": record["artifact"]["path"],
        "builder": record["source"]["builder"]["path"],
        "ledger": record["source"]["claim_ledger"]["path"],
        "local_audit": record["source"]["local_test_audit"]["path"],
        "benchmark": record["source"]["benchmark_result"]["path"],
        "workflow": record["source"]["ci_workflow"]["path"],
    }
    if mutation is not None and mutation in mutation_paths:
        artifact = fixture_root / mutation_paths[mutation]
        payload = bytearray(artifact.read_bytes())
        payload[-1] ^= 1
        artifact.write_bytes(payload)
    elif mutation == "record":
        record["scope"] += " tampered"
        qa_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    elif mutation == "extra_pdf":
        extra = fixture_root / "private" / "resume.pdf"
        extra.parent.mkdir(parents=True)
        extra.write_bytes(b"%PDF-1.4\nprivate")

    archive_path = tmp_path / f"pptrans-case-study-{mutation or 'valid'}.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        archive.add(fixture_root, arcname="pptrans-2.0")
    return archive_path


def _inspect_case_study_fixture(checker: ModuleType, path: Path) -> tuple[str, ...]:
    with tarfile.open(path, mode="r:gz") as archive:
        archive_members = tuple(archive.getmembers())
        members = tuple(member.name.replace("\\", "/") for member in archive_members)
        return checker._case_study_evidence_failures(archive, archive_members, members)


def _pdf_writer_payload(writer: PdfWriter) -> bytes:
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_source_distribution_policy_requires_complete_agent_skills() -> None:
    checker = _load_script("check_wheel.py")

    assert EXPECTED_PACKAGED_SKILL_RESOURCES <= checker.SDIST_REQUIRED_SUFFIXES
    assert {
        "AGENTS.md",
        "CLAUDE.md",
        "scripts/sync_agent_skills.py",
        "scripts/validate_agent_skills.py",
    } <= checker.SDIST_REQUIRED_SUFFIXES


def test_agent_skill_validator_covers_the_complete_inventory() -> None:
    validator = _load_script("validate_agent_skills.py")

    assert tuple(EXPECTED_SKILL_RESOURCES) == validator.SKILL_NAMES
    errors: list[str] = []
    for skill_name in validator.SKILL_NAMES:
        for root in validator._skill_roots(skill_name):
            validator._validate_skill(root, skill_name, errors)
        validator._validate_mirror(skill_name, errors)
    validator._validate_discovery(errors)

    assert errors == []


def test_agent_skill_validator_rejects_missing_operator_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _load_script("validate_agent_skills.py")
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "AGENTS.md").write_text(
        ".agents/skills/pptrans-engineering/\n"
        "$pptrans-engineering\n"
        "scripts/sync_agent_skills.py\n"
        "scripts/validate_agent_skills.py\n",
        encoding="utf-8",
    )
    (repository / "CLAUDE.md").write_text(
        "@AGENTS.md\n/pptrans-engineering\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "REPO_ROOT", repository)
    errors: list[str] = []

    validator._validate_discovery(errors)

    assert errors == [
        "AGENTS.md: missing agent discovery reference '.agents/skills/pptrans-operator/'",
        "AGENTS.md: missing agent discovery reference '$pptrans-operator'",
        "CLAUDE.md: missing agent discovery reference '/pptrans-operator'",
    ]


def test_source_distribution_policy_requires_deterministic_showcase_artifacts(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")

    assert {
        "README.md",
        "docs/DEMO.md",
        "docs/qa/2026-08-31-exact-rebuild.json",
        "examples/pptrans-demo.source/manifest.json",
        "scripts/rebuild_demo.py",
        "tests/test_demo_rebuild.py",
    } <= checker.SDIST_REQUIRED_SUFFIXES
    assert "scripts/build_demo.mjs" not in checker.SDIST_REQUIRED_SUFFIXES
    assert "scripts/render_demo_comparison.mjs" not in checker.SDIST_REQUIRED_SUFFIXES
    assert checker._forbidden_sdist_path(".env") is True
    assert checker._forbidden_sdist_path(".env.example") is False
    record = json.loads((REPO_ROOT / checker.CURRENT_QA_SUFFIX).read_bytes())
    canonical = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == checker.CURRENT_QA_CANONICAL_SHA256

    assert checker.CASE_STUDY_PACKAGED_INPUTS <= checker.SDIST_REQUIRED_SUFFIXES
    case_study_record = json.loads((REPO_ROOT / checker.CASE_STUDY_QA_SUFFIX).read_bytes())
    case_study_canonical = json.dumps(
        case_study_record,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert (
        hashlib.sha256(case_study_canonical.encode()).hexdigest()
        == checker.CASE_STUDY_QA_CANONICAL_SHA256
    )
    assert checker._forbidden_sdist_path("private/resume.pdf") is True
    assert checker._forbidden_sdist_path(checker.CASE_STUDY_PDF_SUFFIX) is False

    builder = _load_script("build_case_study.py")
    payload = builder.build_pdf_bytes()
    builder._validate_pdf(payload)

    def set_case_study_identifier(writer: PdfWriter) -> None:
        writer._ID = ArrayObject(
            [
                ByteStringObject(builder.EXPECTED_PDF_ID_BYTES),
                ByteStringObject(builder.EXPECTED_PDF_ID_BYTES),
            ]
        )

    with pytest.raises(ValueError, match="bounded plain ASCII"):
        builder._validate_plain_ledger_text(
            "hostile display",
            '<img src="https://example.invalid/private.png">',
        )

    def unexpected_socket(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("case-study build must not create a network socket")

    monkeypatch.setattr("socket.socket", unexpected_socket)
    assert builder.build_pdf_bytes() == payload

    encrypted = PdfWriter()
    encrypted.add_blank_page(width=builder.A4[0], height=builder.A4[1])
    encrypted.encrypt("fixture")
    with pytest.raises(ValueError, match="must not be encrypted"):
        builder._validate_pdf(_pdf_writer_payload(encrypted))

    two_pages = PdfWriter()
    two_pages.add_blank_page(width=builder.A4[0], height=builder.A4[1])
    two_pages.add_blank_page(width=builder.A4[0], height=builder.A4[1])
    with pytest.raises(ValueError, match="exactly one page"):
        builder._validate_pdf(_pdf_writer_payload(two_pages))

    wrong_size = PdfWriter()
    wrong_size.add_blank_page(width=100, height=100)
    wrong_size.add_metadata({"/Title": "PPTrans Engineering Case Study", "/Author": "Hehan Zhao"})
    with pytest.raises(ValueError, match="A4 media box"):
        builder._validate_pdf(_pdf_writer_payload(wrong_size))

    annotation = PdfWriter()
    annotation.add_blank_page(width=builder.A4[0], height=builder.A4[1])
    annotation.root_object[NameObject("/PageMode")] = NameObject("/UseNone")
    annotation.add_metadata(builder.EXPECTED_PDF_METADATA)
    set_case_study_identifier(annotation)
    annotation.add_uri(0, "https://example.invalid", (0, 0, 10, 10))
    with pytest.raises(ValueError, match="forbidden actions or interactive entries"):
        builder._validate_pdf(_pdf_writer_payload(annotation))

    automatic_action = PdfWriter()
    automatic_page = automatic_action.add_blank_page(width=builder.A4[0], height=builder.A4[1])
    automatic_action.root_object[NameObject("/PageMode")] = NameObject("/UseNone")
    automatic_action.add_metadata(builder.EXPECTED_PDF_METADATA)
    set_case_study_identifier(automatic_action)
    automatic_page[NameObject("/AA")] = DictionaryObject(
        {
            NameObject("/O"): DictionaryObject(
                {
                    NameObject("/S"): NameObject("/URI"),
                    NameObject("/URI"): TextStringObject("https://example.invalid"),
                }
            )
        }
    )
    with pytest.raises(ValueError, match="forbidden actions or interactive entries"):
        builder._validate_pdf(_pdf_writer_payload(automatic_action))

    associated_file = PdfWriter()
    associated_file.add_blank_page(width=builder.A4[0], height=builder.A4[1])
    associated_file.root_object[NameObject("/PageMode")] = NameObject("/UseNone")
    associated_file.add_metadata(builder.EXPECTED_PDF_METADATA)
    set_case_study_identifier(associated_file)
    private_stream = DecodedStreamObject()
    private_stream.set_data(b"private attachment payload")
    private_stream_reference = associated_file._add_object(private_stream)
    file_specification = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Filespec"),
            NameObject("/F"): TextStringObject("private.txt"),
            NameObject("/EF"): DictionaryObject({NameObject("/F"): private_stream_reference}),
        }
    )
    file_specification_reference = associated_file._add_object(file_specification)
    associated_file.root_object[NameObject("/AF")] = ArrayObject([file_specification_reference])
    with pytest.raises(ValueError, match="catalog differs"):
        builder._validate_pdf(_pdf_writer_payload(associated_file))

    orphan_object = PdfWriter()
    orphan_object.clone_document_from_reader(PdfReader(io.BytesIO(payload), strict=True))
    set_case_study_identifier(orphan_object)
    orphan_stream = DecodedStreamObject()
    orphan_stream.set_data(b"private unreferenced payload")
    orphan_reference = orphan_object._add_object(orphan_stream)
    with pytest.raises(ValueError, match="exact reachable graph") as orphan_error:
        builder._validate_pdf(_pdf_writer_payload(orphan_object))
    assert f"({orphan_reference.idnum}, 0)" in str(orphan_error.value)

    missing_text = PdfWriter()
    missing_text.add_blank_page(width=builder.A4[0], height=builder.A4[1])
    missing_text.root_object[NameObject("/PageMode")] = NameObject("/UseNone")
    missing_text.add_metadata(builder.EXPECTED_PDF_METADATA)
    set_case_study_identifier(missing_text)
    with pytest.raises(ValueError, match="missing selectable text"):
        builder._validate_pdf(_pdf_writer_payload(missing_text))

    metadata_writer = PdfWriter()
    metadata_writer.clone_document_from_reader(PdfReader(io.BytesIO(payload), strict=True))
    set_case_study_identifier(metadata_writer)
    tampered_metadata = dict(builder.EXPECTED_PDF_METADATA)
    tampered_metadata["/Subject"] = f"{REPO_ROOT} applicant@example.invalid"
    metadata_writer.add_metadata(tampered_metadata)
    with pytest.raises(ValueError, match="exact safe allowlist"):
        builder._validate_pdf(_pdf_writer_payload(metadata_writer))

    identifier_writer = PdfWriter()
    identifier_writer.clone_document_from_reader(PdfReader(io.BytesIO(payload), strict=True))
    identifier_writer._ID = ArrayObject(
        [ByteStringObject(b"private-applicant-id-a"), ByteStringObject(b"private-applicant-id-b")]
    )
    with pytest.raises(ValueError, match="trailer ID differs"):
        builder._validate_pdf(_pdf_writer_payload(identifier_writer))

    root_value_writer = PdfWriter()
    root_value_writer.clone_document_from_reader(PdfReader(io.BytesIO(payload), strict=True))
    set_case_study_identifier(root_value_writer)
    root_value_writer.root_object[NameObject("/PageMode")] = TextStringObject(
        "private-applicant-root-value"
    )
    with pytest.raises(ValueError, match="catalog scalar values differ"):
        builder._validate_pdf(_pdf_writer_payload(root_value_writer))

    with pytest.raises(ValueError, match="forbidden action tokens"):
        builder._validate_pdf(payload + b"\n/JavaScript\n")
    with pytest.raises(ValueError, match="single EOF marker"):
        builder._validate_pdf(payload + b"private trailing payload")

    tampered_ledger = copy.deepcopy(builder.LEDGER)
    tampered_evidence = tampered_ledger["evidence"]
    tampered_evidence["benchmark"]["display"] = "0.001 / 0.002 ms"
    with pytest.raises(ValueError, match="benchmark"):
        builder._validate_claim_sources(tampered_ledger, tampered_evidence)

    tampered_ledger = copy.deepcopy(builder.LEDGER)
    tampered_evidence = tampered_ledger["evidence"]
    tampered_evidence["tests"].update({"display": "540", "value": 540})
    with pytest.raises(ValueError, match="local audit"):
        builder._validate_claim_sources(tampered_ledger, tampered_evidence)

    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    decoy_workflow = workflow.replace(
        'python: ["3.10", "3.13"]',
        'python: ["3.11", "3.12"] # python: ["3.10", "3.13"]',
    )
    assert decoy_workflow != workflow
    with pytest.raises(ValueError, match="endpoints differ from the CI matrix"):
        builder._validate_workflow_python_support(decoy_workflow, "3.10", "3.13")

    fixed_python_workflow = workflow.replace(
        "python-version: ${{ matrix.python }}",
        'python-version: "3.12"',
    )
    assert fixed_python_workflow != workflow
    with pytest.raises(ValueError, match=r"bind one Python setup step to matrix\.python"):
        builder._validate_workflow_python_support(fixed_python_workflow, "3.10", "3.13")

    excluded_workflow = workflow.replace(
        "        include:\n",
        "        exclude:\n"
        '          - {os: ubuntu-latest, python: "3.10"}\n'
        '          - {os: windows-latest, python: "3.10"}\n'
        '          - {os: macos-latest, python: "3.10"}\n'
        '          - {os: ubuntu-latest, python: "3.13"}\n'
        '          - {os: windows-latest, python: "3.13"}\n'
        '          - {os: macos-latest, python: "3.13"}\n'
        "        include:\n",
    )
    assert excluded_workflow != workflow
    with pytest.raises(ValueError, match="must not define exclusions"):
        builder._validate_workflow_python_support(excluded_workflow, "3.10", "3.13")

    wrong_setup_action = workflow.replace(
        builder.EXPECTED_SETUP_PYTHON_ACTION,
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    )
    assert wrong_setup_action != workflow
    with pytest.raises(ValueError, match="exact unconditional setup-python step"):
        builder._validate_workflow_python_support(wrong_setup_action, "3.10", "3.13")

    conditional_setup = workflow.replace(
        "      - name: Set up Python\n        uses: actions/setup-python@",
        "      - name: Set up Python\n        if: false\n        uses: actions/setup-python@",
    )
    assert conditional_setup != workflow
    with pytest.raises(ValueError, match="exact unconditional setup-python step"):
        builder._validate_workflow_python_support(conditional_setup, "3.10", "3.13")

    disabled_compatibility = workflow.replace(
        "  compatibility:\n    name:",
        "  compatibility:\n    if: false\n    name:",
    )
    assert disabled_compatibility != workflow
    with pytest.raises(ValueError, match="exact authenticated contract"):
        builder._validate_workflow_python_support(disabled_compatibility, "3.10", "3.13")

    disabled_test_step = workflow.replace(
        "      - name: Run deterministic suite\n        run:",
        "      - name: Run deterministic suite\n        if: false\n        run:",
    )
    assert disabled_test_step != workflow
    with pytest.raises(ValueError, match="exact authenticated contract"):
        builder._validate_workflow_python_support(disabled_test_step, "3.10", "3.13")

    original_read_json_object = builder._read_json_object

    def tampered_benchmark(path: Path, *, label: str) -> dict[str, object]:
        record = original_read_json_object(path, label=label)
        if path.name == "2026-08-31-honest-showcase-ooxml-windows-python312.json":
            record = copy.deepcopy(record)
            samples = record["samples_ms"]
            assert isinstance(samples, list)
            samples[0] = 999
        return record

    with monkeypatch.context() as context:
        context.setattr(builder, "_read_json_object", tampered_benchmark)
        with pytest.raises(ValueError, match="benchmark summary"):
            builder._validate_claim_sources(builder.LEDGER, builder.LEDGER["evidence"])

    mismatched = tmp_path / "mismatched-case-study.pdf"
    mismatched.write_bytes(payload + b"\n")
    assert builder.main(["--output", str(mismatched), "--check"]) == 1


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        (None, None),
        ("payload", "member differs from manifest"),
        ("entry", "entry 0 must be an object"),
        ("archive", "archive.compression must be 'stored'"),
        ("schema", "schema_version must be 1"),
        ("split_root", "do not share one distribution root"),
    ],
)
def test_source_distribution_demo_payloads_match_their_manifest(
    tmp_path: Path,
    mutation: str | None,
    expected_failure: str | None,
) -> None:
    checker = _load_script("check_wheel.py")

    failures = _inspect_demo_fixture(checker, _demo_sdist_fixture(tmp_path, mutation))

    if expected_failure is None:
        assert failures == ()
    else:
        assert any(expected_failure in failure for failure in failures)


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        (None, None),
        ("target", "QA artifact differs from record"),
        ("png", "QA artifact differs from record"),
        ("record", "QA record differs from the pinned contract"),
    ],
)
def test_source_distribution_qa_artifacts_match_the_current_record(
    tmp_path: Path,
    mutation: str | None,
    expected_failure: str | None,
) -> None:
    checker = _load_script("check_wheel.py")

    failures = _inspect_qa_fixture(checker, _qa_sdist_fixture(tmp_path, mutation))

    if expected_failure is None:
        assert failures == ()
        case_study_expectations = {
            None: None,
            "pdf": "case-study PDF differs from QA record",
            "builder": "case-study builder differs from QA record",
            "ledger": "case-study claim ledger differs from QA record",
            "local_audit": "case-study local-test audit differs from QA record",
            "benchmark": "case-study benchmark result differs from QA record",
            "workflow": "case-study CI workflow differs from QA record",
            "record": "case-study QA record differs from the pinned contract",
        }
        for case_study_mutation, case_study_failure in case_study_expectations.items():
            case_study_failures = _inspect_case_study_fixture(
                checker,
                _case_study_sdist_fixture(tmp_path, case_study_mutation),
            )
            if case_study_failure is None:
                assert case_study_failures == ()
            else:
                assert any(case_study_failure in failure for failure in case_study_failures)

        extra_pdf_failures = checker.inspect_sdist(_case_study_sdist_fixture(tmp_path, "extra_pdf"))
        assert "source distribution must contain only the canonical recruiter PDF" in (
            extra_pdf_failures
        )
    else:
        assert any(expected_failure in failure for failure in failures)


def test_wheel_checker_requires_exact_safe_package_paths(tmp_path: Path) -> None:
    checker = _load_script("check_wheel.py")
    valid = tmp_path / "valid.whl"
    with zipfile.ZipFile(valid, mode="w") as archive:
        for member in checker.REQUIRED_SUFFIXES:
            archive.writestr(member, b"fixture")
    assert checker.inspect_wheel(valid) == ()

    decoy = tmp_path / "decoy.whl"
    with zipfile.ZipFile(decoy, mode="w") as archive:
        for member in checker.REQUIRED_SUFFIXES:
            archive.writestr(f"decoy/{member}", b"fixture")
    decoy.write_bytes(decoy.read_bytes().replace(b"/", b"\\"))
    failures = checker.inspect_wheel(decoy)
    assert any("unsafe wheel member" in failure for failure in failures)
    assert any("missing required wheel member" in failure for failure in failures)


def test_wheel_checker_rejects_case_insensitive_forbidden_fragments(tmp_path: Path) -> None:
    checker = _load_script("check_wheel.py")
    wheel = tmp_path / "uppercase-private.whl"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        for member in checker.REQUIRED_SUFFIXES:
            archive.writestr(member, b"fixture")
        archive.writestr("examples/PRIVATE.PPTX", b"private")

    assert "forbidden wheel member: examples/PRIVATE.PPTX" in checker.inspect_wheel(wheel)


@pytest.mark.parametrize(
    ("member_names", "expected_failure"),
    [
        (("pptrans-2.0/README.md", "other-root/file.txt"), "one top-level"),
        (("pptrans-2.0\\README.md",), "unsafe source-distribution member"),
    ],
)
def test_sdist_checker_rejects_split_roots_and_backslash_names(
    tmp_path: Path,
    member_names: tuple[str, ...],
    expected_failure: str,
) -> None:
    checker = _load_script("check_wheel.py")
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        for member_name in member_names:
            info = tarfile.TarInfo(member_name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))

    failures = checker.inspect_sdist(archive_path)

    assert any(expected_failure in failure for failure in failures)


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        "secrets/.env",
        ".env.local",
        ".env.production",
        "scripts/build_demo.mjs",
        "docs/assets/pptrans-demo-preview.webp",
        "private.sqlite3",
        "cache.sqlite3-wal",
        "cache.sqlite3-journal",
        "cache.db-shm",
        "ppt_translator/main.py",
        ".tmp-private/deck.pptx",
        "PPT_TRANSLATOR/main.py",
        "SCRIPTS/BUILD_DEMO.MJS",
        "private/resume.pdf",
    ],
)
def test_sdist_checker_rejects_private_or_retired_artifacts(
    tmp_path: Path,
    relative: str,
) -> None:
    checker = _load_script("check_wheel.py")
    archive_path = tmp_path / "forbidden.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        info = tarfile.TarInfo(f"pptrans-2.0/{relative}")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))

    failures = checker.inspect_sdist(archive_path)

    assert f"forbidden source-distribution artifact: {relative}" in failures


@pytest.mark.parametrize("relative", [".git", ".VENV", ".TMP-PRIVATE"])
def test_sdist_checker_rejects_empty_private_directories(
    tmp_path: Path,
    relative: str,
) -> None:
    checker = _load_script("check_wheel.py")
    archive_path = tmp_path / "forbidden-directory.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        info = tarfile.TarInfo(f"pptrans-2.0/{relative}")
        info.type = tarfile.DIRTYPE
        archive.addfile(info)

    failures = checker.inspect_sdist(archive_path)

    assert f"forbidden source-distribution artifact: {relative}" in failures


def test_packaged_demo_builder_authenticates_before_isolated_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")
    manifest = json.loads(
        (REPO_ROOT / "examples" / "pptrans-demo.source" / "manifest.json").read_bytes()
    )
    expected_output = {
        "bytes": manifest["expected_package"]["bytes"],
        "entries": len(manifest["entries"]),
        "result": "byte-identical",
        "sha256": manifest["expected_package"]["sha256"],
    }
    observed: dict[str, object] = {}
    monkeypatch.setenv("PYTHON_CHECK_WHEEL_SENTINEL", "must-not-propagate")

    def fake_run(command: list[str], **kwargs: object) -> object:
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        return checker.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(expected_output),
            stderr="",
        )

    monkeypatch.setattr(checker.subprocess, "run", fake_run)

    assert checker.verify_packaged_demo_builder(_packaged_builder_snapshot(tmp_path)) == ()
    command = observed["command"]
    environment = observed["environment"]
    assert isinstance(command, list)
    assert command[1:4] == ["-I", "-X", "utf8"]
    assert isinstance(environment, dict)
    assert not any(key.upper().startswith("PYTHON") for key in environment)

    case_observed: dict[str, object] = {}

    def fake_case_run(command: list[str], **kwargs: object) -> object:
        case_observed["command"] = command
        case_observed["environment"] = kwargs["env"]
        return checker.subprocess.CompletedProcess(
            command,
            0,
            stdout="case-study PDF is current: isolated fixture\n",
            stderr="",
        )

    monkeypatch.setattr(checker.subprocess, "run", fake_case_run)
    assert (
        checker.verify_packaged_case_study_builder(_packaged_case_study_snapshot(tmp_path, checker))
        == ()
    )
    case_command = case_observed["command"]
    case_environment = case_observed["environment"]
    assert isinstance(case_command, list)
    assert case_command[1:4] == ["-I", "-X", "utf8"]
    assert case_command[-1] == "--check"
    assert isinstance(case_environment, dict)
    assert not any(key.upper().startswith("PYTHON") for key in case_environment)


def test_packaged_demo_builder_rejects_unpinned_code_without_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")

    def unexpected_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("unpinned packaged code was executed")

    monkeypatch.setattr(checker.subprocess, "run", unexpected_run)

    failures = checker.verify_packaged_demo_builder(
        _packaged_builder_snapshot(tmp_path, mutate_builder=True)
    )

    assert failures == ("refusing to execute an unpinned packaged demo builder",)
    case_failures = checker.verify_packaged_case_study_builder(
        _packaged_case_study_snapshot(tmp_path, checker, mutate_builder=True)
    )
    assert case_failures == ("refusing to execute with an unpinned case-study builder",)


def test_distribution_checker_accepts_a_disposable_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")
    (tmp_path / "pptrans.whl").write_bytes(b"fixture")
    (tmp_path / "pptrans.tar.gz").write_bytes(b"fixture")
    monkeypatch.setattr(checker, "inspect_wheel", lambda _path: ())
    monkeypatch.setattr(checker, "_inspect_sdist_snapshot", lambda _snapshot: ())
    monkeypatch.setattr(checker, "verify_packaged_demo_builder", lambda _snapshot: ())
    monkeypatch.setattr(checker, "verify_packaged_case_study_builder", lambda _snapshot: ())

    assert checker.main(["--dist-dir", str(tmp_path)]) == 0


def test_distribution_checker_validates_and_executes_one_sdist_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")
    (tmp_path / "pptrans.whl").write_bytes(b"fixture")
    sdist = tmp_path / "pptrans.tar.gz"
    first_generation = b"first immutable source-distribution generation"
    sdist.write_bytes(first_generation)
    observed: list[bytes] = []
    monkeypatch.setattr(checker, "inspect_wheel", lambda _path: ())

    def inspect_snapshot(snapshot: bytes) -> tuple[()]:
        observed.append(snapshot)
        sdist.write_bytes(b"replacement generation")
        return ()

    def verify_snapshot(snapshot: bytes) -> tuple[()]:
        observed.append(snapshot)
        return ()

    def verify_case_study_snapshot(snapshot: bytes) -> tuple[()]:
        observed.append(snapshot)
        return ()

    monkeypatch.setattr(checker, "_inspect_sdist_snapshot", inspect_snapshot)
    monkeypatch.setattr(checker, "verify_packaged_demo_builder", verify_snapshot)
    monkeypatch.setattr(
        checker,
        "verify_packaged_case_study_builder",
        verify_case_study_snapshot,
    )

    assert checker.main(["--dist-dir", str(tmp_path)]) == 0
    assert observed == [first_generation, first_generation, first_generation]


def test_minimal_install_checker_detects_optional_provider_sdks() -> None:
    checker = _load_script("check_minimal_install.py")

    assert checker.provider_sdk_presence_failures(lambda _module_name: None) == ()
    assert checker.provider_sdk_presence_failures(
        lambda module_name: object() if module_name == "openai" else None
    ) == ("base install unexpectedly exposes optional provider SDK: openai",)


def test_native_demo_reproducer_pins_the_committed_libreoffice_assets() -> None:
    reproducer = _load_script("reproduce_native_demo.py")

    contract = reproducer.load_contract()
    assert (contract.libreoffice_version, contract.pymupdf_version, contract.dpi) == (
        "26.8.0.3",
        "1.28.2",
        144,
    )
    assert len(contract.slides) == 3
    assert all((slide.width, slide.height) == (1921, 1080) for slide in contract.slides)
    reproducer.verify_committed_assets(contract, REPO_ROOT / "docs" / "assets")


def test_installed_version_checker_requires_runtime_metadata_and_exact_tag_agreement() -> None:
    checker = _load_script("check_installed_version.py")

    assert checker.version_failures("2.0.0a1", "2.0.0a1", "v2.0.0a1") == ()
    assert checker.version_failures("2.0.0a2", "2.0.0a1") == (
        "runtime version '2.0.0a2' != installed metadata '2.0.0a1'",
    )
    assert checker.version_failures("2.0.0a1", "2.0.0a1", "2.0.0a1") == (
        "release tag '2.0.0a1' != installed version tag v2.0.0a1",
    )


def test_release_policy_machine_enforces_the_recorded_provenance_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checker = _load_script("check_release_policy.py")

    assert checker.release_policy_failures("cleared") == ()
    assert checker.release_policy_failures() == (checker.BLOCK_MESSAGE,)
    assert checker.main(["--tag", "v2.0.0a1"]) == 1
    assert "v2.0.0a1: release blocked" in capsys.readouterr().err


def test_benchmark_output_guards_source_aliases_and_existing_files(tmp_path: Path) -> None:
    benchmark = _load_script("benchmark_core.py")
    source = tmp_path / "source.pptx"
    create_complex_deck(source)
    original = source.read_bytes()

    with pytest.raises(ValueError, match="input presentation"):
        benchmark._prepare_output(source, source, overwrite=True)
    assert source.read_bytes() == original

    alias = tmp_path / "source-hard-link.json"
    try:
        os.link(source, alias)
    except OSError as exc:
        pytest.skip(f"hard links unavailable on this filesystem: {exc}")
    with pytest.raises(ValueError, match="input presentation"):
        benchmark._prepare_output(source, alias, overwrite=True)
    assert source.read_bytes() == original

    existing = tmp_path / "result.json"
    existing.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        benchmark._prepare_output(source, existing, overwrite=False)
    assert existing.read_text(encoding="utf-8") == "preserve"


def test_benchmark_summaries_are_recomputable_from_recorded_samples() -> None:
    benchmark = _load_script("benchmark_core.py")

    samples, median, p95, minimum, maximum = benchmark._summarize_durations(
        [6.0004, 1.0004, 4.0004, 2.0004, 5.0004, 3.0004]
    )

    assert samples == (6.0, 1.0, 4.0, 2.0, 5.0, 3.0)
    assert median == 3.5
    assert p95 == 6.0
    assert minimum == 1.0
    assert maximum == 6.0


def test_benchmark_output_rejects_symlink_target(tmp_path: Path) -> None:
    benchmark = _load_script("benchmark_core.py")
    source = tmp_path / "source.pptx"
    sentinel = tmp_path / "sentinel.json"
    output = tmp_path / "output.json"
    create_complex_deck(source)
    sentinel.write_text("preserve", encoding="utf-8")
    try:
        output.symlink_to(sentinel)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable on this filesystem: {exc}")

    with pytest.raises(ValueError, match="symbolic link"):
        benchmark._prepare_output(source, output, overwrite=True)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_skill_sync_updates_every_declared_skill_and_prunes_stale_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = _load_script("sync_agent_skills.py")
    repository = tmp_path / "repository"
    canonical_root = repository / ".agents" / "skills"
    mirror_root = repository / ".claude" / "skills"
    skill_names = tuple(EXPECTED_SKILL_RESOURCES)
    for skill_name in skill_names:
        canonical = canonical_root / skill_name
        mirror = mirror_root / skill_name
        (canonical / "references").mkdir(parents=True)
        mirror.mkdir(parents=True)
        (canonical / "SKILL.md").write_text(f"canonical {skill_name}\n", encoding="utf-8")
        (canonical / "references" / "workflow.md").write_text(
            f"workflow {skill_name}\n", encoding="utf-8"
        )
        (mirror / "SKILL.md").write_text("stale\n", encoding="utf-8")
        (mirror / "remove-me.txt").write_text("stale\n", encoding="utf-8")

    monkeypatch.setattr(sync, "REPO_ROOT", repository)
    monkeypatch.setattr(sync, "SKILL_NAMES", skill_names)
    monkeypatch.setattr(sync, "CANONICAL_ROOT", canonical_root)
    monkeypatch.setattr(sync, "MIRROR_ROOT", mirror_root)

    sync.synchronize()

    assert sync.differences() == []
    for skill_name in skill_names:
        canonical = canonical_root / skill_name
        mirror = mirror_root / skill_name
        assert (mirror / "SKILL.md").read_bytes() == (canonical / "SKILL.md").read_bytes()
        assert (mirror / "references" / "workflow.md").read_bytes() == (
            canonical / "references" / "workflow.md"
        ).read_bytes()
        assert not (mirror / "remove-me.txt").exists()


def test_skill_sync_preflights_the_complete_inventory_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = _load_script("sync_agent_skills.py")
    repository = tmp_path / "repository"
    canonical_root = repository / ".agents" / "skills"
    mirror_root = repository / ".claude" / "skills"
    engineering = canonical_root / "pptrans-engineering"
    engineering_mirror = mirror_root / "pptrans-engineering"
    engineering.mkdir(parents=True)
    engineering_mirror.mkdir(parents=True)
    (engineering / "SKILL.md").write_text("new canonical\n", encoding="utf-8")
    mirrored_skill = engineering_mirror / "SKILL.md"
    mirrored_skill.write_text("preserve until preflight passes\n", encoding="utf-8")

    monkeypatch.setattr(sync, "REPO_ROOT", repository)
    monkeypatch.setattr(sync, "SKILL_NAMES", tuple(EXPECTED_SKILL_RESOURCES))
    monkeypatch.setattr(sync, "CANONICAL_ROOT", canonical_root)
    monkeypatch.setattr(sync, "MIRROR_ROOT", mirror_root)

    with pytest.raises(ValueError, match="pptrans-operator"):
        sync.synchronize()

    assert mirrored_skill.read_text(encoding="utf-8") == "preserve until preflight passes\n"


def test_skill_sync_rejects_symlinked_ancestor_without_touching_external_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = _load_script("sync_agent_skills.py")
    repository = tmp_path / "repository"
    canonical = repository / ".agents" / "skills" / "pptrans-engineering"
    external = tmp_path / "external"
    canonical.mkdir(parents=True)
    external.mkdir()
    (canonical / "SKILL.md").write_text("canonical", encoding="utf-8")
    marker = external / "keep.txt"
    marker.write_text("do not touch", encoding="utf-8")
    try:
        (repository / ".claude").symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable on this filesystem: {exc}")

    monkeypatch.setattr(sync, "REPO_ROOT", repository)
    monkeypatch.setattr(sync, "SKILL_NAMES", ("pptrans-engineering",))
    monkeypatch.setattr(sync, "CANONICAL_ROOT", repository / ".agents" / "skills")
    monkeypatch.setattr(sync, "MIRROR_ROOT", repository / ".claude" / "skills")

    with pytest.raises(ValueError, match="must not be symlinks"):
        sync.synchronize()
    assert marker.read_text(encoding="utf-8") == "do not touch"
    assert not (external / "skills").exists()
