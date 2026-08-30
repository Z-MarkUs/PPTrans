#!/usr/bin/env python3
"""Fail versioned-tag CI while PPTrans's provenance release gate is unresolved."""

from __future__ import annotations

import argparse
import sys

PROVENANCE_STATUS = "unresolved"
BLOCK_MESSAGE = (
    "release blocked: NOTICE.md requires written upstream licensing clarification before "
    "another package, versioned tag, or release is published"
)


def release_policy_failures(status: str = PROVENANCE_STATUS) -> tuple[str, ...]:
    """Return explicit release-policy failures for the repository's recorded status."""

    if status != "cleared":
        return (BLOCK_MESSAGE,)
    return ()


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
