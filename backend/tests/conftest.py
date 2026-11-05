import pytest

from ap_agent.core.config import REPO_ROOT


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture
def aop():
    from ap_agent.rulebook.loader import load_aop

    return load_aop(REPO_ROOT / "rulebook" / "aop.yaml")


@pytest.fixture
def store(tmp_path):
    from ap_agent.core.config import Settings
    from ap_agent.storage.cases import Store
    from ap_agent.storage.seed import seed_history

    s = Store(tmp_path / "runs.db")
    seed_history(s, Settings().seed_path)
    return s
