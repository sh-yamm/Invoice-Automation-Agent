"""A small tool-calling loop for the agent model.

The agent may call read-only lookup tools; every call and result goes into the case record.
It must finish with JSON matching the given schema. It has no tool that changes anything.
"""
from __future__ import annotations

import json

import jsonschema

from ap_agent.ai.gateway import _extract_json


class AgentGaveUp(RuntimeError):
    """The agent did not produce a valid final answer within its turn budget."""


def run_agent(gateway, system: str, user: str, tools: dict, *, store, case_id: str | None, node: str,
              schema: dict, max_turns: int = 6, cache_prefix: str | None = None) -> dict:
    specs = [spec for spec, _ in tools.values()]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for turn in range(max_turns):
        key = f"{cache_prefix}/{node}/turn{turn}" if cache_prefix else None
        msg = gateway.chat_tools("agent", messages, specs, case_id=case_id, node=node, cache_key=key)
        calls = msg.get("tool_calls") or []
        if calls:
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if name not in tools:
                    result = {"error": f"unknown tool {name}"}
                else:
                    try:
                        result = tools[name][1](**args)
                    except Exception as e:  # a tool error is information for the agent, not a crash
                        result = {"error": f"{type(e).__name__}: {e}"}
                if store and case_id:
                    store.add_tool_call(case_id, node, name, args, result)
                messages.append({"role": "tool", "tool_call_id": call.get("id", name),
                                 "content": json.dumps(result, ensure_ascii=False, default=str)})
            continue
        content = msg.get("content") or ""
        try:
            data = _extract_json(content)
            jsonschema.validate(data, schema)
            return data
        except (ValueError, jsonschema.ValidationError) as e:
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": f"That was not valid JSON for the required answer ({e}). "
                                                     "Reply with the JSON answer only."}]
    raise AgentGaveUp(f"no valid answer after {max_turns} turns")
