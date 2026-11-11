"""The client is a made-up demo company, and its name says so everywhere."""
from pathlib import Path

from ap_agent.core.config import REPO_ROOT
from ap_agent.core.constants import BUYER_NAME


def test_client_is_a_sample_name():
    assert BUYER_NAME == "Sample Client Retail Pvt Ltd (demo company)"
    places = [REPO_ROOT / "backend" / "src", REPO_ROOT / "ui", REPO_ROOT / "rulebook"]
    files = [p for d in places for p in d.rglob("*") if p.suffix in (".py", ".yaml")]
    files += list((REPO_ROOT / "samples").glob("*.py")) + [REPO_ROOT / "streamlit_app.py"]
    assert not [str(f) for f in files if "Zentra" in f.read_text(encoding="utf-8")]
