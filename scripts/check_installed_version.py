"""Verify installed PPTrans runtime, metadata, and optional release-tag versions."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from importlib.metadata import version as distribution_version

import pptrans


def version_failures(
    runtime_version: str,
    metadata_version: str,
    expected_tag: str | None = None,
) -> tuple[str, ...]:
    """Return explicit failures without relying on optimization-sensitive assertions."""

    failures: list[str] = []
    if runtime_version != metadata_version:
        failures.append(
            f"runtime version {runtime_version!r} != installed metadata {metadata_version!r}"
        )
    if expected_tag is not None and expected_tag != f"v{metadata_version}":
        failures.append(
            f"release tag {expected_tag!r} != installed version tag v{metadata_version}"
        )
    return tuple(failures)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expected-tag",
        default=os.getenv("PPTRANS_RELEASE_TAG"),
        help="Optional exact release tag; defaults to PPTRANS_RELEASE_TAG when set.",
    )
    args = parser.parse_args(argv)
    metadata_version = distribution_version("pptrans")
    failures = version_failures(pptrans.__version__, metadata_version, args.expected_tag)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"installed version verified: {metadata_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
