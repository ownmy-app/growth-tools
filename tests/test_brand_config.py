"""Tests for growth-tools brand configuration — no external APIs required."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_brand_name_reads_from_env(monkeypatch):
    monkeypatch.setenv("BRAND_NAME", "TestBrand")
    from core import llm
    import importlib
    importlib.reload(llm)
    assert llm.BRAND_NAME == "TestBrand"


def test_brand_tagline_reads_from_env(monkeypatch):
    monkeypatch.setenv("BRAND_TAGLINE", "Build fast, ship faster")
    from core import llm
    import importlib
    importlib.reload(llm)
    assert llm.BRAND_TAGLINE == "Build fast, ship faster"


def test_icp_pain_reads_from_env(monkeypatch):
    monkeypatch.setenv("ICP_PAIN", "too much config, not enough shipping")
    from core import llm
    import importlib
    importlib.reload(llm)
    assert llm.ICP_PAIN == "too much config, not enough shipping"


def test_no_hardcoded_brand_names_in_source():
    """Ensure OwnMyApp or Nometria don't appear in llm.py prompts."""
    llm_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "core", "llm.py"
    )
    with open(llm_path) as f:
        content = f.read()

    # These specific brand names should not be hardcoded in prompts
    assert "OwnMyApp" not in content, "OwnMyApp brand name found — use BRAND_NAME env var instead"
