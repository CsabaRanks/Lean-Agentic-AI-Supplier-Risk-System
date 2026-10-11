"""The comparison matrix YAML is the single source of truth for the benchmark."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_spider


def test_matrix_is_valid_and_markdown_up_to_date():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_spider.py"), "--check"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_matrix_covers_all_factors_and_approaches():
    data = generate_spider.load()
    assert len(data["factors"]) == 15
    assert [a["key"] for a in data["approaches"]] == ["xls", "saas", "oss", "lean"]


def test_validation_rejects_inconsistent_example_mean():
    data = generate_spider.load()
    data["factors"][0]["ratings"]["saas"]["by_example"] = {"Prewave": 5, "Sphera": 1}  # mean 3 != 4
    with pytest.raises(ValueError, match="mean of by_example"):
        generate_spider.validate(data)


def test_chart_image_exists():
    assert (ROOT / "docs" / "images" / "spider-diagram.png").stat().st_size > 50_000
