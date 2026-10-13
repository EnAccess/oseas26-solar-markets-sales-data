"""Data-grounded assistant: Claude answers using read-only tools over the project's own services.

Design:
  * Tools call the same services as the map, cell API and reports (no separate analytics).
  * Tools are a fixed allow-list of read-only functions with validated, size-limited inputs:
    no code, SQL, shell or file access is reachable from natural language.
  * A deterministic scope guard declines clearly unrelated questions before any model call.
  * Without ANTHROPIC_API_KEY the endpoint still returns the retrieved evidence, but no generated
    answer, and says how to enable the assistant. No AI answer is ever simulated.
  * Only aggregated project data (cell indicators, scores, source notes) is sent to the provider.
"""
from __future__ import annotations

import json
import logging
import re

from ..config import Settings
from . import location_service, report_service
from .market_gap import METHOD

logger = logging.getLogger(__name__)

MAX_TOOL_TURNS = 6
MAX_CELLS = report_service.MAX_REPORT_CELLS
OUT_OF_SCOPE = (
    "I can only help with energy access and off-grid solar market analysis for Rwanda using this "
    "tool's data, for example: \"What does the data tell us about Nyagatare?\", \"Which indicators "
    "suggest the selected cells may be underserved?\" or \"Does low nighttime radiance mean households "
    "here do not have solar?\""
)
DOMAIN_WORDS = re.compile(
    r"solar|energy|electri|grid|power|light|radiance|dark|night|population|density|people|wealth|rwi|"
    r"market|gap|opportunit|underserved|survey|household|district|province|village|sector|cell|"
    r"location|area|place|region|data|indicator|report|compar|penetration|minigrid|mini-grid|off-grid|"
    r"offgrid|access|need|missing|coverage|select|map|layer|model|evidence|source|limitation|"
    r"invest|priorit|kigali|rwanda|coordinate|latitude|longitude|this|here",
    re.IGNORECASE,
)

SYSTEM_PROMPT = f"""You are the Solar Market Reality assistant. You help energy-access planners understand
where Rwanda's off-grid solar market may be underserved, using only this project's data via the tools.

Scope: energy access, off-grid solar markets, the project's datasets and map layers, locations in
Rwanda, data coverage, and reports. For anything else, reply briefly that you only cover these topics
and suggest a relevant question. Do not answer general-knowledge questions.

Grounding rules:
- Always call a tool before stating any number about a location. Never invent locations, household
  counts, sales figures, statistics or percentages. If a tool returns no value, say it is not available.
- Resolve place names with resolve_location. Only districts, provinces, 5 km grid cell IDs and
  coordinates can be matched. Villages and sectors cannot; say so. A grid cell is not a village.
- Label every figure by evidence type: observed (NASA radiance, MTF survey, mapped OSM lines),
  external estimate (WorldPop population, Meta RWI), derived (energy need, opportunity score), or
  model prediction. Give units and source dates when the tool provides them.
- The market opportunity score is a relative 0-100 priority for field investigation. Never call it
  a percentage of households, a market size, or proof of commercial viability.
- Nighttime darkness indicates limited grid electricity, not absence of solar: solar home systems
  are below the satellite's detection floor. Mapped grid lines do not mean households are connected.
- Survey solar ownership is a district-wide estimate from small samples; it cannot describe
  individual cells. Missing evidence is not evidence of an underserved market.
- Model status: predicted penetration is only available if the model was trained on real survey
  labels; get_methodology tells you whether it is. Do not claim the model is validated otherwise.
- To create a report, call prepare_report with the cell IDs; the user downloads it from the app.

Naming: refer to places by their names (the "name" field, e.g. "Cyembogo, Matimba"), never by internal
IDs such as RW_0412; those IDs are only for calling tools.

Style: plain English, short paragraphs or bullets, lead with the answer, then the evidence, then
caveats and what to verify in the field. Method summary: {METHOD['formula']}."""

TOOLS = [
    {
        "name": "resolve_location",
        "description": "Match a place in Rwanda (district, province, grid cell ID like RW_0412, or 'lat, lon') "
                       "to grid cells in the dataset. Returns matched type, name, cell count and IDs.",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Place name, cell ID or coordinates"}},
            "required": ["query"], "additionalProperties": False},
    },
    {
        "name": "get_cell_evidence",
        "description": "All indicators for one 5 km grid cell: values, units, evidence type, source, "
                       "opportunity score, drivers, missing inputs and an evidence-based interpretation.",
        "input_schema": {"type": "object", "properties": {
            "cell_id": {"type": "string", "description": "Grid cell ID, e.g. RW_0412"}},
            "required": ["cell_id"], "additionalProperties": False},
    },
    {
        "name": "summarize_cells",
        "description": "Aggregate evidence for a set of grid cells (e.g. the user's selection or a district): "
                       "population, density, radiance, grid distance, district survey shares, score range, "
                       "highest-priority cells and cells with missing evidence.",
        "input_schema": {"type": "object", "properties": {
            "cell_ids": {"type": "array", "items": {"type": "string"}, "description": f"Up to {MAX_CELLS} cell IDs"}},
            "required": ["cell_ids"], "additionalProperties": False},
    },
    {
        "name": "compare_areas",
        "description": "Compare two to five districts, provinces or cells side by side using the same summary.",
        "input_schema": {"type": "object", "properties": {
            "queries": {"type": "array", "items": {"type": "string"}, "description": "Place names or cell IDs"}},
            "required": ["queries"], "additionalProperties": False},
    },
    {
        "name": "get_methodology",
        "description": "Market-gap formula, data sources with dates and licences, model status and known limitations.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "prepare_report",
        "description": "Prepare a downloadable PDF/CSV report for the given cell IDs. Returns a summary; the app "
                       "shows the download button.",
        "input_schema": {"type": "object", "properties": {
            "cell_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["cell_ids"], "additionalProperties": False},
    },
]


class AssistantTools:
    """Read-only tool implementations. Every result is plain JSON built from shared services."""

    def __init__(self, svc, code: str, threshold: float):
        self.svc, self.code, self.threshold = svc, code, threshold
        self.cells = svc.cells(code)
        self.evidence: list[dict] = []   # what was retrieved, returned to the UI for traceability
        self.report_cell_ids: list[str] | None = None

    def run(self, name: str, args: dict) -> dict:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            raise ValueError(f"Unknown tool '{name}'")
        result = handler(**args)
        self.evidence.append({"tool": name, "input": args, "result": result})
        return result

    def _ids(self, cell_ids) -> list[str]:
        if not isinstance(cell_ids, list) or not all(isinstance(c, str) for c in cell_ids):
            raise ValueError("cell_ids must be a list of strings")
        return report_service.validate_selection(self.svc, self.code, cell_ids)

    def tool_resolve_location(self, query: str) -> dict:
        result = location_service.resolve(str(query)[:120], self.cells, self.svc.spec(self.code))
        ids = result.get("cell_ids", [])
        return {**result, "cell_count": len(ids), "cell_ids": ids[:MAX_CELLS]}

    def tool_get_cell_evidence(self, cell_id: str) -> dict:
        from .prediction_service import cell_details

        ids = self._ids([cell_id])
        row = self.cells.loc[self.cells["cell_id"] == ids[0]].iloc[0]
        d = cell_details(row, self.cells, self.code, self.svc.meta(self.code), self.svc.model_info(self.code),
                         self.threshold)
        return {
            "cell_id": d.cell_id, "name": d.place_name, "district": d.district, "province": d.province,
            "centre": [round(d.latitude, 4), round(d.longitude, 4)],
            "indicators": [{"label": i.label, "value": i.formatted, "type": i.kind_label, "source": i.source,
                            "date": i.source_year} for i in d.indicators],
            "opportunity_score_0_100": d.opportunity_score, "priority_cutoff_0_100": round(self.threshold * 100),
            "solar_uptake_evidence": d.uptake_source_label, "evidence_level": d.evidence_level,
            "missing_inputs": d.missing_inputs,
            "drivers_0_1_higher_raises_score": [{"factor": x.factor, "value": x.value} for x in d.drivers],
            "interpretation": d.interpretation,
        }

    def tool_summarize_cells(self, cell_ids: list) -> dict:
        report = report_service.build_report(self.svc, self.code, self._ids(cell_ids), self.threshold)
        cells = report["cells"]
        ranked = sorted((c for c in cells if c["opportunity_score"] is not None),
                        key=lambda c: -c["opportunity_score"])
        return {
            "summary": report["summary"],
            "rwanda_score_median_0_100": report["national"]["median"],
            "priority_cutoff_0_100": report["threshold_score"],
            "highest_priority": [{"cell_id": c["cell_id"], "name": c["name"], "district": c["district"],
                                  "score": c["opportunity_score"], "evidence": c["evidence_level"]}
                                 for c in ranked[:8]],
            "cells_without_score": [{"cell_id": c["cell_id"], "name": c["name"], "missing": c["missing_inputs"]}
                                    for c in cells if c["opportunity_score"] is None][:10],
            "interpretation": report["interpretation"],
        }

    def tool_compare_areas(self, queries: list) -> dict:
        if not isinstance(queries, list) or not 1 <= len(queries) <= 5:
            raise ValueError("Provide between one and five places to compare")
        out = []
        for query in queries:
            loc = self.tool_resolve_location(str(query))
            if not loc.get("matched"):
                out.append({"query": query, "matched": False, "note": loc.get("note")})
                continue
            s = self.tool_summarize_cells(loc["cell_ids"])
            out.append({"query": query, "matched": True, "name": loc["name"], "type": loc["type"],
                        "summary": s["summary"], "highest_priority": s["highest_priority"][:3]})
        return {"areas": out}

    def tool_get_methodology(self) -> dict:
        from ..data_sources import LIMITATIONS
        from .indicators import source_date

        sources = self.svc.meta(self.code).get("sources", {})
        return {
            "method": METHOD,
            "priority_cutoff_0_100": round(self.threshold * 100),
            "model_status": self.svc.model_info(self.code),
            "sources": {k: {"dataset": v.get("dataset") or v.get("source"), "status": v.get("status"),
                            "date": source_date(v), "note": v.get("note")} for k, v in sources.items()},
            "limitations": LIMITATIONS,
        }

    def tool_prepare_report(self, cell_ids: list) -> dict:
        ids = self._ids(cell_ids)
        self.report_cell_ids = ids
        summary = report_service.build_report(self.svc, self.code, ids, self.threshold)["summary"]
        return {"prepared": True, "n_cells": len(ids), "summary": summary,
                "note": "The user can download the PDF or CSV from the assistant panel."}


def in_scope(question: str, has_context: bool) -> bool:
    if DOMAIN_WORDS.search(question) or re.search(r"\b[A-Z]{2}_\d{4}\b", question, re.IGNORECASE):
        return True
    return has_context and len(question.split()) <= 6  # short follow-ups like "and the next one?"


def _context_note(selected: list[str], focused: str | None, area: dict | None = None) -> str:
    parts = []
    if area:
        ids = area["cell_ids"]
        parts.append(f"The user is looking at {area['name']} ({area['level']}, official administrative boundary). "
                     f"Its data comes from {len(ids)} 5 km analysis cell(s): {', '.join(ids[:50])}.")
    if focused:
        parts.append(f"The user is currently inspecting grid cell {focused}.")
    if selected:
        shown = ", ".join(selected[:50]) + (" ..." if len(selected) > 50 else "")
        parts.append(f"The user has selected {len(selected)} grid cell(s): {shown}.")
    return " ".join(parts)


def answer(svc, settings: Settings, code: str, question: str, history: list[dict], selected: list[str],
           focused: str | None, threshold: float, focused_area: dict | None = None) -> dict:
    tools = AssistantTools(svc, code, threshold)
    base = {"configured": bool(settings.anthropic_api_key), "evidence": [], "report_cell_ids": None}

    if not in_scope(question, bool(history or selected or focused or focused_area)):
        return {**base, "status": "out_of_scope", "answer": OUT_OF_SCOPE}

    if not settings.anthropic_api_key:
        # Still useful: return the data the assistant would have used, clearly without an AI answer.
        if focused:
            tools.run("get_cell_evidence", {"cell_id": focused})
        if focused_area and focused_area["cell_ids"]:
            tools.run("summarize_cells", {"cell_ids": focused_area["cell_ids"]})
        if selected:
            tools.run("summarize_cells", {"cell_ids": selected})
        return {**base, "status": "not_configured", "evidence": tools.evidence, "answer": None,
                "message": "The AI assistant is not configured. Set ANTHROPIC_API_KEY in backend/.env and restart "
                           "the API. The evidence below comes directly from the project data."}

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=settings.assistant_timeout_s,
                                 max_retries=2)
    context = _context_note(selected, focused, focused_area)
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
    messages.append({"role": "user", "content": f"{question}\n\n[App context: {context}]" if context else question})

    try:
        for _ in range(MAX_TOOL_TURNS):
            response = client.beta.messages.create(
                model=settings.assistant_model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if response.stop_reason == "refusal":
                return {**base, "status": "refused", "evidence": tools.evidence,
                        "answer": "The model declined to answer this request. " + OUT_OF_SCOPE}
            if response.stop_reason != "tool_use":
                text = "\n".join(b.text for b in response.content if b.type == "text").strip()
                return {**base, "status": "ok", "answer": text or "No answer was returned.",
                        "evidence": tools.evidence, "report_cell_ids": tools.report_cell_ids,
                        "model": response.model}
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    content, is_error = json.dumps(tools.run(block.name, dict(block.input)), default=str), False
                except (ValueError, KeyError, TypeError) as exc:
                    content, is_error = f"Error: {exc}", True
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content,
                                "is_error": is_error})
            messages.append({"role": "user", "content": results})
        return {**base, "status": "incomplete", "evidence": tools.evidence,
                "answer": "The question needed more lookups than allowed. Please ask about fewer places."}
    except anthropic.AuthenticationError:
        return {**base, "status": "error", "evidence": tools.evidence,
                "answer": None, "message": "The configured ANTHROPIC_API_KEY was rejected."}
    except anthropic.RateLimitError:
        return {**base, "status": "error", "evidence": tools.evidence,
                "answer": None, "message": "The language-model service is rate limited. Try again shortly."}
    except anthropic.APITimeoutError:
        return {**base, "status": "error", "evidence": tools.evidence,
                "answer": None, "message": "The language-model service timed out."}
    except anthropic.APIStatusError as exc:
        logger.warning("Assistant API error %s: %s", exc.status_code, exc.message)
        return {**base, "status": "error", "evidence": tools.evidence,
                "answer": None, "message": f"The language-model service returned an error ({exc.status_code})."}
    except anthropic.APIConnectionError:
        return {**base, "status": "error", "evidence": tools.evidence,
                "answer": None, "message": "Could not reach the language-model service."}
