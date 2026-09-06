"""Regression coverage for Unicode output on legacy console encodings."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DEMO_PATH = Path(__file__).parents[1] / "examples" / "pptrans-demo.en.pptx"


def test_cli_reconfigures_legacy_streams_for_unicode_json() -> None:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    environment["PYTHONUTF8"] = "0"

    completed = subprocess.run(  # noqa: S603 - invokes this test interpreter with fixed arguments
        [
            sys.executable,
            "-m",
            "pptrans.cli",
            "inspect",
            str(DEMO_PATH),
            "--source",
            "en",
            "--target",
            "zh-CN",
            "--json",
            "--show-text",
        ],
        check=False,
        capture_output=True,
        env=environment,
        shell=False,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    output = completed.stdout.decode("ascii")
    payload = json.loads(output)
    texts = [unit["text"] for unit in payload["units"]]
    assert any("粗体文本" in text for text in texts)
    assert any("你好 🌏" in text for text in texts)
