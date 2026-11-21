"""requirements.txt (used by Render) must match uv.lock exactly."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPORT = [
    "uv", "export", "--frozen", "--no-dev", "--no-emit-project",
    "--format", "requirements.txt",
]  # fmt: skip


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_requirements_txt_matches_uv_lock() -> None:
    expected = subprocess.run(
        EXPORT, cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout

    def packages(text: str) -> list[str]:
        """Package and hash lines only; comment lines repeat the command used."""
        return [line for line in text.splitlines() if not line.lstrip().startswith("#")]

    current = (ROOT / "requirements.txt").read_text()
    assert packages(current) == packages(expected), (
        "requirements.txt is out of date. Run: "
        "uv export --frozen --no-dev --no-emit-project "
        "--format requirements.txt -o requirements.txt"
    )
