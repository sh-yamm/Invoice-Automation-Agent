import pytest

from ap_agent.core.config import REPO_ROOT


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture
def aop():
    from ap_agent.rulebook.loader import load_aop

    return load_aop(REPO_ROOT / "rulebook" / "aop.yaml")
