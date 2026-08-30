"""Structural tests for repository automation and contribution policy files."""

from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parents[1]


def _workflow(name: str) -> dict[str, Any]:
    path = REPO_ROOT / ".github" / "workflows" / name
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    if True in loaded:
        loaded["on"] = loaded.pop(True)
    return loaded


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = workflow["jobs"]
    return [step for job in jobs.values() for step in job["steps"]]


def test_ci_bounds_jobs_drops_checkout_credentials_and_blocks_release_tags() -> None:
    workflow = _workflow("ci.yml")

    assert workflow["on"]["push"] == {"branches": ["main"], "tags": ["v*"]}
    assert all(job.get("timeout-minutes") for job in workflow["jobs"].values())
    checkout_steps = [step for step in _steps(workflow) if step.get("name") == "Check out source"]
    assert checkout_steps
    assert all(step.get("with", {}).get("persist-credentials") is False for step in checkout_steps)
    release_steps = [
        step for step in workflow["jobs"]["quality"]["steps"] if "release gate" in step["name"]
    ]
    assert len(release_steps) == 1
    assert release_steps[0]["if"] == "github.ref_type == 'tag'"
    assert "scripts/check_release_policy.py" in release_steps[0]["run"]
    demo_steps = [
        step for step in _steps(workflow) if step.get("name") == "Verify exact demo rebuild"
    ]
    assert len(demo_steps) == 2
    assert all(step["run"] == "python scripts/rebuild_demo.py --check" for step in demo_steps)


def test_security_covers_tags_and_schedules_a_bounded_dependency_audit() -> None:
    workflow = _workflow("security.yml")

    assert workflow["on"]["push"] == {"branches": ["main"], "tags": ["v*"]}
    assert all(job.get("timeout-minutes") for job in workflow["jobs"].values())
    checkout_steps = [step for step in _steps(workflow) if step["name"].startswith("Check out")]
    assert checkout_steps
    assert all(step.get("with", {}).get("persist-credentials") is False for step in checkout_steps)
    scanner = next(
        step for step in workflow["jobs"]["secrets"]["steps"] if "Gitleaks" in step["name"]
    )
    assert scanner["env"] == {
        "GITLEAKS_VERSION": "8.30.0",
        "GITLEAKS_ARCHIVE_SHA256": (
            "79a3ab579b53f71efd634f3aaf7e04a0fa0cf206b7ed434638d1547a2470a66e"
        ),
    }
    dependency_job = workflow["jobs"]["dependencies"]
    assert dependency_job["if"] == "github.event_name == 'schedule'"
    assert "github.event_name" in workflow["concurrency"]["group"]
    install = next(
        step for step in dependency_job["steps"] if "optional dependencies" in step["name"]
    )
    assert ".[dev,review]" in install["run"]
    assert any("pip_audit" in step.get("run", "") for step in dependency_job["steps"])


def test_bug_form_and_precommit_gate_enforce_safe_repository_inputs() -> None:
    issue_path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
    issue = yaml.safe_load(issue_path.read_text(encoding="utf-8"))
    assert {"name", "description", "body"} <= issue.keys()
    fields = [entry for entry in issue["body"] if "id" in entry]
    identifiers = [entry["id"] for entry in fields]
    assert len(identifiers) == len(set(identifiers))
    assert {
        "version",
        "environment",
        "stage",
        "observed",
        "expected",
        "reproduction",
        "privacy",
    } <= set(identifiers)
    privacy = next(entry for entry in fields if entry["id"] == "privacy")
    assert all(option["required"] for option in privacy["attributes"]["options"])
    chooser = yaml.safe_load(
        (REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")
    )
    assert chooser["blank_issues_enabled"] is False

    precommit = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [hook for repository in precommit["repos"] for hook in repository["hooks"]]
    documentation = next(hook for hook in hooks if hook["id"] == "documentation-links")
    assert documentation["pass_filenames"] is False
    assert documentation["always_run"] is True
    demo_rebuild = next(hook for hook in hooks if hook["id"] == "public-demo-rebuild")
    assert demo_rebuild["entry"] == "python scripts/rebuild_demo.py --check"
    assert demo_rebuild["pass_filenames"] is False
    assert demo_rebuild["always_run"] is True


def test_dependabot_groups_pep621_optional_dependencies_by_pattern() -> None:
    policy = yaml.safe_load((REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    python_updates = next(
        update for update in policy["updates"] if update["package-ecosystem"] == "pip"
    )
    assert python_updates["groups"] == {"python-dependencies": {"patterns": ["*"]}}


def test_demo_source_checkout_attributes_preserve_exact_payloads() -> None:
    git = shutil.which("git")
    assert git is not None
    completed = subprocess.run(  # noqa: S603 - resolved executable and fixed arguments
        [
            git,
            "check-attr",
            "text",
            "eol",
            "diff",
            "--",
            "examples/pptrans-demo.source/docProps/core.xml",
            "examples/pptrans-demo.en.pptx",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.splitlines() == [
        "examples/pptrans-demo.source/docProps/core.xml: text: set",
        "examples/pptrans-demo.source/docProps/core.xml: eol: lf",
        "examples/pptrans-demo.source/docProps/core.xml: diff: unspecified",
        "examples/pptrans-demo.en.pptx: text: unset",
        "examples/pptrans-demo.en.pptx: eol: unspecified",
        "examples/pptrans-demo.en.pptx: diff: unset",
    ]
    ignore_check = subprocess.run(  # noqa: S603 - resolved executable and fixed arguments
        [
            git,
            "check-ignore",
            "--no-index",
            "--quiet",
            "examples/pptrans-demo.source/docProps/core.xml",
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    assert ignore_check.returncode == 1


def test_current_benchmark_claim_matches_the_clean_raw_record() -> None:
    relative = Path("benchmarks/results/2026-08-31-honest-showcase-ooxml-windows-python312.json")
    record = json.loads((REPO_ROOT / relative).read_bytes())
    fixture = REPO_ROOT / "examples" / "pptrans-demo.en.pptx"

    assert record["schema_version"] == "pptrans.core-benchmark/v2"
    assert record["git_commit"] == "7cb4a1f496857319ab73c4c84f5f7daf7f955354"
    assert record["git_dirty"] is False
    assert record["input_sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert record["input_bytes"] == fixture.stat().st_size == 87_226
    assert (record["slides"], record["translation_units"], record["translated_spans"]) == (
        3,
        41,
        45,
    )
    assert (record["warmups"], record["iterations"]) == (3, 30)
    samples = record["samples_ms"]
    assert isinstance(samples, list) and len(samples) == record["iterations"]
    ordered = sorted(samples)
    p95_index = round((len(ordered) - 1) * 0.95)
    assert record["median_ms"] == round(statistics.median(samples), 3) == 58.77
    assert record["p95_ms"] == ordered[p95_index] == 60.972
    assert record["minimum_ms"] == min(samples) == 56.708
    assert record["maximum_ms"] == max(samples) == 61.151
    for readme_name in ("README.md", "README.zh-CN.md"):
        readme = (REPO_ROOT / readme_name).read_text(encoding="utf-8")
        for claim in (
            "58.770 ms",
            "60.972 ms",
            "`7cb4a1f`",
            "87,226",
            relative.as_posix(),
        ):
            assert claim in readme


def test_reviewed_tree_has_no_release_trigger_or_publication_workflow() -> None:
    workflow_root = REPO_ROOT / ".github" / "workflows"
    workflow_paths = sorted(path for path in workflow_root.iterdir() if path.is_file())
    assert all(path.suffix in {".yaml", ".yml"} for path in workflow_paths)
    assert [path.name for path in workflow_paths] == ["ci.yml", "security.yml"]
    for path in workflow_paths:
        workflow = _workflow(path.name)
        assert "release" not in workflow["on"]
        serialized = path.read_text(encoding="utf-8").casefold()
        assert "twine upload" not in serialized
        assert "pypi" not in serialized
