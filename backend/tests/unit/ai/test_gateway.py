import json

import httpx
import pytest
import respx

from ap_agent.ai.gateway import AiUnavailable, Gateway, InvalidModelOutput
from ap_agent.core.config import Settings

BASE = "https://llm.test/v1"
PARSE = "https://parse.test/parse"
SCHEMA = {"type": "object", "properties": {"total": {"type": "number"}}, "required": ["total"]}


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def chat_reply(content, reasoning=None):
    msg = {"role": "assistant", "content": content}
    if reasoning:
        msg["reasoning_content"] = reasoning
    return httpx.Response(200, json={"choices": [{"message": msg, "finish_reason": "stop"}],
                                     "usage": {"total_tokens": 42}})


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def gw(tmp_path, store, clock):
    s = Settings(nvidia_api_key="k", nvidia_base_url=BASE, parse_url=PARSE, llm_max_rpm=600)
    store.create_case("c1", "f.pdf", "h", None)
    return Gateway(s, store, tmp_path / "cache", clock=clock.now, sleep=clock.sleep)


@respx.mock
def test_chat_json_parses_and_logs(gw, store):
    respx.post(f"{BASE}/chat/completions").mock(return_value=chat_reply('```json\n{"total": 58275}\n```', "thinking..."))
    data, reasoning = gw.chat_json("extract", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="extract")
    assert data == {"total": 58275} and reasoning == "thinking..."
    call = store.get_case("c1")["llm_calls"][0]
    assert call["node"] == "extract" and call["reasoning"] == "thinking..." and call["model"] == gw.models["extract"]


@respx.mock
def test_reasoning_logged(gw, store):
    respx.post(f"{BASE}/chat/completions").mock(return_value=chat_reply('{"total": 1}', "step by step"))
    gw.chat_json("agent", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="decide")
    assert store.get_case("c1")["llm_calls"][0]["reasoning"] == "step by step"


@respx.mock
def test_cache_hit_skips_http(gw, tmp_path):
    route = respx.post(f"{BASE}/chat/completions").mock(return_value=chat_reply('{"total": 7}'))
    first = gw.chat_json("extract", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="extract",
                         cache_key="S01/extract")
    second = gw.chat_json("extract", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="extract",
                          cache_key="S01/extract")
    assert first == second and route.call_count == 1
    assert (tmp_path / "cache" / "S01_extract.json").exists()


@respx.mock
def test_retry_then_success(gw, clock):
    route = respx.post(f"{BASE}/chat/completions").mock(side_effect=[
        httpx.Response(429), httpx.Response(429), chat_reply('{"total": 3}')])
    data, _ = gw.chat_json("fast", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="n")
    assert data == {"total": 3} and route.call_count == 3
    assert 1 in clock.slept and 2 in clock.slept


@respx.mock
def test_timeout_is_retried(gw):
    route = respx.post(f"{BASE}/chat/completions").mock(side_effect=[
        httpx.ReadTimeout("slow"), chat_reply('{"total": 3}')])
    gw.chat_json("fast", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="n")
    assert route.call_count == 2


@respx.mock
def test_ai_unavailable_after_retries(gw):
    route = respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(503))
    with pytest.raises(AiUnavailable):
        gw.chat_json("fast", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="n")
    assert route.call_count == 5  # first attempt + 4 retries


@respx.mock
def test_bad_request_not_retried(gw):
    route = respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(400, json={"error": "bad"}))
    with pytest.raises(AiUnavailable):
        gw.chat_json("fast", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="n")
    assert route.call_count == 1


@respx.mock
def test_schema_retry_appends_error(gw):
    route = respx.post(f"{BASE}/chat/completions").mock(side_effect=[chat_reply('{"amount": 5}'),
                                                                      chat_reply('{"total": 5}')])
    data, _ = gw.chat_json("extract", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="extract")
    assert data == {"total": 5}
    second = json.loads(route.calls[1].request.content)
    assert "total" in second["messages"][-1]["content"] and second["messages"][-2]["role"] == "assistant"
    assert second["temperature"] == 0


@respx.mock
def test_schema_fails_twice_raises(gw):
    respx.post(f"{BASE}/chat/completions").mock(return_value=chat_reply("not json at all"))
    with pytest.raises(InvalidModelOutput):
        gw.chat_json("extract", [{"role": "user", "content": "x"}], SCHEMA, case_id="c1", node="extract")


@respx.mock
def test_throttle_spacing(tmp_path, store, clock):
    s = Settings(nvidia_api_key="k", nvidia_base_url=BASE, parse_url=PARSE, llm_max_rpm=60)
    g = Gateway(s, store, tmp_path / "c", clock=clock.now, sleep=clock.sleep)
    respx.post(f"{BASE}/chat/completions").mock(return_value=chat_reply('{"total": 1}'))
    start = clock.now()
    for _ in range(3):
        g.chat_json("fast", [{"role": "user", "content": "x"}], SCHEMA, case_id=None, node="n")
    assert clock.now() - start >= 2


@respx.mock
def test_parse_page_multipart(gw, tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"\x89PNG fake")
    route = respx.post(PARSE).mock(return_value=httpx.Response(200, json={"content": "<x_0.1><y_0.1>Hi<x_0.2><y_0.2><class_Text>"}))
    out = gw.parse_page(png, case_id="c1", cache_key="S01/p1")
    assert out.startswith("<x_0.1>")
    body = route.calls[0].request.content
    assert b'name="document"' in body and b'name="options"' in body and b"max_output_tokens" in body


@respx.mock
def test_chat_tools_returns_message(gw):
    msg = {"role": "assistant", "content": None,
           "tool_calls": [{"id": "1", "type": "function", "function": {"name": "vendor_lookup", "arguments": "{}"}}]}
    respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(200, json={"choices": [{"message": msg}]}))
    out = gw.chat_tools("agent", [{"role": "user", "content": "x"}], [{"type": "function"}], case_id="c1", node="classify")
    assert out["tool_calls"][0]["function"]["name"] == "vendor_lookup"


@respx.mock
def test_embed_caches_per_text(gw):
    route = respx.post(f"{BASE}/embeddings").mock(side_effect=lambda req: httpx.Response(200, json={
        "data": [{"embedding": [float(i), 1.0]} for i, _ in enumerate(json.loads(req.content)["input"])]}))
    a = gw.embed(["chair", "desk"])
    b = gw.embed(["desk", "chair"])
    assert route.call_count == 1 and a[0] == b[1] and a[1] == b[0]
    assert json.loads(route.calls[0].request.content)["input_type"] == "query"
