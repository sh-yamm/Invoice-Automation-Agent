"""Real calls to the NVIDIA endpoints. Off by default; run with:  py -3.11 -m pytest -m live tests/live -v"""
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from ap_agent.ai.gateway import Gateway
from ap_agent.core.config import REPO_ROOT, Settings

pytestmark = pytest.mark.live
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "parse"
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


@pytest.fixture(scope="module")
def gw():
    s = Settings()
    if not s.nvidia_api_key:
        pytest.skip("NVIDIA_API_KEY not set")
    return Gateway(s)


@pytest.mark.parametrize("sample", ["S01", "S13"])
def test_parse_sample_page_and_record_fixture(gw, sample, tmp_path):
    png = tmp_path / f"{sample}.png"
    pdfium.PdfDocument(str(REPO_ROOT / "samples" / "pdf" / f"{sample}.pdf"))[0].render(scale=200 / 72).to_pil().save(png)
    content = gw.parse_page(png, case_id=None)
    assert "<x_" in content and "<class_" in content
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{sample}.p1.txt").write_text(content, encoding="utf-8")


@pytest.mark.parametrize("slot", ["extract", "fast", "agent"])
def test_chat_json_each_slot(gw, slot):
    data, _ = gw.chat_json(slot, [{"role": "user", "content": 'Reply with JSON only: {"answer": "OK"}'}], SCHEMA,
                           case_id=None, node="live-test")
    assert data["answer"].upper().startswith("OK")


def test_agent_tool_call(gw):
    tool = {"type": "function", "function": {"name": "vendor_lookup", "description": "Look up a vendor by GSTIN",
                                             "parameters": {"type": "object", "properties": {"gstin": {"type": "string"}},
                                                            "required": ["gstin"]}}}
    msg = gw.chat_tools("agent", [{"role": "user", "content": "Look up the vendor with GSTIN 33ABJFS2290H1Z4."}],
                        [tool], case_id=None, node="live-test")
    assert msg.get("tool_calls") and msg["tool_calls"][0]["function"]["name"] == "vendor_lookup"


def test_embed(gw):
    a, b, c = gw.embed(["Ergonomic mesh chair", "Revolving office chair, mesh back", "MS angle 50x50x5 mm"])
    cos = lambda x, y: sum(i * j for i, j in zip(x, y)) / ((sum(i * i for i in x) ** .5) * (sum(j * j for j in y) ** .5))
    assert cos(a, b) > cos(a, c)
