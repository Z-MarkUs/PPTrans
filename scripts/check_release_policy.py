#!/usr/bin/env python3
"""Fail versioned-tag CI until PPTrans's explicit release prerequisites are met."""

from __future__ import annotations

import argparse
import sys

RELEASE_STATUS = "prerelease"
MANUAL_RELEASE_AUTHORIZED = False
RELEASE_CHECKLIST_COMPLETE = False
HOST_WORKFLOW_MIGRATION_COMPLETE = False

PRERELEASE_MESSAGE = "release blocked: PPTrans v2 remains prerelease work"
AUTHORIZATION_MESSAGE = (
    "release blocked: no separate maintainer authorization is recorded for a versioned tag, "
    "GitHub release, or package-index publication"
)
CHECKLIST_MESSAGE = "release blocked: the versioned-release checklist is incomplete"
HOST_WORKFLOW_MESSAGE = (
    "release blocked: the live-host release workflow and credential migration is incomplete"
)


def release_policy_failures(
    status: str = RELEASE_STATUS,
    *,
    manual_authorized: bool = MANUAL_RELEASE_AUTHORIZED,
    checklist_complete: bool = RELEASE_CHECKLIST_COMPLETE,
    host_workflow_migration_complete: bool = HOST_WORKFLOW_MIGRATION_COMPLETE,
) -> tuple[str, ...]:
    """Return blockers for versioned releases, not ordinary public source branches."""

    failures: list[str] = []
    if status != "release-ready":
        failures.append(PRERELEASE_MESSAGE)
    if not manual_authorized:
        failures.append(AUTHORIZATION_MESSAGE)
    if not checklist_complete:
        failures.append(CHECKLIST_MESSAGE)
    if not host_workflow_migration_complete:
        failures.append(HOST_WORKFLOW_MESSAGE)
    return tuple(failures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Versioned tag that triggered this CI run.")
    arguments = parser.parse_args(argv)
    failures = release_policy_failures()
    if failures:
        for failure in failures:
            print(f"{arguments.tag}: {failure}", file=sys.stderr)
        return 1
    print(f"release policy permits {arguments.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
