"""Assistant: scope guard, data grounding, provider failures. The Anthropic client is mocked."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import assistant_service as A


def settings(key=None):
    return SimpleNamespace(anthropic_api_key=key, assistant_model="claude-opus-5-5", assistant_timeout_s=5)


def block(**kw):
    return SimpleNamespace(**kw)


def message(content, stop="end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop, model="claude-opus-5-5")


@pytest.mark.parametrize("question", ["How did Ronaldo score his last goal?", "Write me a poem about cats"])
def test_unrelated_questions_are_declined_without_model_call(svc, question):
    with patch("anthropic.Anthropic") as client:
        out = A.answer(svc, settings("key"), "RW", question, [], [], None, 0.55)
    assert out["status"] == "out_of_scope" and "energy access" in out["answer"]
    client.assert_not_called()


@pytest.mark.parametrize("question", [
    "Does low nighttime radiance mean households here do not have solar?",
    "Compare Nyagatare and Bugesera",
    "What is the opportunity for RW_0500?",
])
def test_domain_questions_are_in_scope(question):
    assert A.in_scope(question, has_context=False)


def test_not_configured_returns_evidence_but_no_answer(svc):
    out = A.answer(svc, settings(None), "RW", "What does the data tell us about this location?", [],
                   ["RW_0500", "RW_0501"], "RW_0500", 0.55)
    assert out["status"] == "not_configured" and out["answer"] is None
    assert "ANTHROPIC_API_KEY" in out["message"]
    assert [e["tool"] for e in out["evidence"]] == ["get_cell_evidence", "summarize_cells"]


def test_clicked_area_is_passed_as_context(svc, client):
    r = client.post("/api/assistant/ask", json={
        "question": "What does the data tell us about this area?",
        "focused_area": {"name": "Rwimiyaga", "level": "sector", "cell_ids": ["RW_0217", "RW_0251", "RW_9999"]},
    }).json()
    if r["configured"]:
        return
    assert r["status"] == "not_configured"
    summary = r["evidence"][0]
    assert summary["tool"] == "summarize_cells" and summary["input"]["cell_ids"] == ["RW_0217", "RW_0251"]
    note = A._context_note([], None, {"name": "Rwimiyaga", "level": "sector", "cell_ids": ["RW_0217"]})
    assert "Rwimiyaga (sector" in note and "RW_0217" in note


def test_tools_return_shared_calculation_values(svc, client):
    tools = A.AssistantTools(svc, "RW", 0.55)
    evidence = tools.run("get_cell_evidence", {"cell_id": "RW_0500"})
    cell = client.get("/api/cells/RW_0500").json()
    assert evidence["opportunity_score_0_100"] == cell["opportunity_score"]
    assert evidence["interpretation"] == cell["interpretation"]


def test_tools_validate_inputs(svc):
    tools = A.AssistantTools(svc, "RW", 0.55)
    with pytest.raises(ValueError):
        tools.run("get_cell_evidence", {"cell_id": "RW_9999"})
    with pytest.raises(ValueError):
        tools.run("summarize_cells", {"cell_ids": "RW_0500"})
    with pytest.raises(ValueError):
        tools.run("compare_areas", {"queries": []})
    with pytest.raises(ValueError):
        tools.run("delete_files", {})
    assert tools.run("resolve_location", {"query": "Gikomero village"})["matched"] is False


def test_tool_loop_grounds_answer_and_prepares_report(svc):
    first = message([block(type="tool_use", id="t1", name="prepare_report", input={"cell_ids": ["RW_0500"]})],
                    stop="tool_use")
    final = message([block(type="text", text="RW_0500 scores 52/100 (relative).")])
    with patch("anthropic.Anthropic") as client:
        client.return_value.beta.messages.create.side_effect = [first, final]
        out = A.answer(svc, settings("key"), "RW", "Generate a report for RW_0500", [], [], None, 0.55)
    assert out["status"] == "ok" and out["report_cell_ids"] == ["RW_0500"]
    assert out["evidence"][0]["tool"] == "prepare_report"
    second_call = client.return_value.beta.messages.create.call_args_list[1].kwargs
    tool_result = second_call["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["is_error"] is False
    assert second_call["model"] == "claude-opus-5-5"


def test_tool_errors_are_returned_to_model_not_raised(svc):
    first = message([block(type="tool_use", id="t1", name="get_cell_evidence", input={"cell_id": "RW_9999"})],
                    stop="tool_use")
    final = message([block(type="text", text="That cell does not exist.")])
    with patch("anthropic.Anthropic") as client:
        client.return_value.beta.messages.create.side_effect = [first, final]
        out = A.answer(svc, settings("key"), "RW", "Tell me about cell RW_9999", [], [], None, 0.55)
    result = client.return_value.beta.messages.create.call_args_list[1].kwargs["messages"][-1]["content"][0]
    assert result["is_error"] is True and out["status"] == "ok"


def test_provider_failure_is_reported_not_fabricated(svc):
    import anthropic
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    with patch("anthropic.Anthropic") as client:
        client.return_value.beta.messages.create.side_effect = anthropic.APIConnectionError(request=request)
        out = A.answer(svc, settings("key"), "RW", "What is the solar evidence in Ngoma?", [], [], None, 0.55)
    assert out["status"] == "error" and out["answer"] is None and "reach" in out["message"]


def test_refusal_is_handled(svc):
    with patch("anthropic.Anthropic") as client:
        client.return_value.beta.messages.create.return_value = message([], stop="refusal")
        out = A.answer(svc, settings("key"), "RW", "Solar data for Ngoma district", [], [], None, 0.55)
    assert out["status"] == "refused"


def test_request_size_limits(client):
    assert client.post("/api/assistant/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/assistant/ask", json={"question": "x" * 1001}).status_code == 422
    r = client.post("/api/assistant/ask", json={"question": "Ronaldo goals?"})
    assert r.status_code == 200 and r.json()["status"] == "out_of_scope"
