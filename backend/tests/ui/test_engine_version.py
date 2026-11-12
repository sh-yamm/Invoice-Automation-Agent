"""The cached in-process API must be rebuilt when the backend code changes (Streamlit Cloud hot-reloads on a push,
and a cache keyed only on the function's own source kept serving the previous API: /api/trails was missing)."""
import os
import time

from ui import engine


def test_code_version_changes_when_a_backend_file_changes(tmp_path):
    pkg = tmp_path / "src"
    pkg.mkdir()
    f = pkg / "mod.py"
    f.write_text("x = 1\n")
    (tmp_path / "aop.yaml").write_text("a: 1\n")
    before = engine.code_version([pkg, tmp_path / "aop.yaml"])
    assert before == engine.code_version([pkg, tmp_path / "aop.yaml"])
    f.write_text("x = 22\n")
    later = time.time() + 5
    os.utime(f, (later, later))
    assert engine.code_version([pkg, tmp_path / "aop.yaml"]) != before


def test_engine_is_keyed_by_the_code_version():
    import inspect
    assert "version" in inspect.signature(engine._engine).parameters


def test_first_build_keeps_loaded_backend_modules(monkeypatch):
    """Dropping modules on the first build would give the process two copies of every class."""
    import sys

    import ap_agent.core.models as models
    monkeypatch.delattr(sys, "_ap_agent_engine_version", raising=False)
    engine._engine.clear()
    engine._engine(engine.code_version())
    assert sys.modules["ap_agent.core.models"] is models


def test_the_demo_invoice_definitions_are_part_of_the_code_version():
    """samples/ (demo specs, edge cases) is read by the API: changing it must rebuild the API, or a new demo
    invoice raises KeyError in the old one."""
    assert engine.ROOT / "samples" in engine.CODE
