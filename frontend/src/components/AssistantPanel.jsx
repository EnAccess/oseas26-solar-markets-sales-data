import { useEffect, useRef, useState } from "react";
import { useApi } from "../hooks/useApi";
import { api, downloadBlob, errorMessage } from "../services/api";

const SUGGESTIONS = [
  "What does the data tell us about this area?",
  "Which indicators suggest the selected places may be underserved?",
  "Does low nighttime radiance mean households here do not have solar?",
  "Compare Nyagatare and Bugesera using the available solar-market evidence.",
  "Which data is missing for this area?",
];

const TOOL_LABELS = {
  resolve_location: "Looked up a place",
  get_cell_evidence: "Read area indicators",
  summarize_cells: "Summarised areas",
  compare_areas: "Compared places",
  get_methodology: "Checked method and sources",
  prepare_report: "Prepared a report",
};

/** Human-readable description of one lookup (names, never internal IDs). */
function describe(e) {
  const r = e.result || {};
  const name = r.name || r.summary?.districts?.map((d) => d.district).join(", ")
    || r.areas?.map((a) => a.name || a.query).join(" vs ") || e.input?.query;
  const count = Array.isArray(e.input?.cell_ids) ? ` (${e.input.cell_ids.length} analysis areas)` : "";
  return `${TOOL_LABELS[e.tool] ?? e.tool}${name ? `: ${name}` : ""}${count}`;
}

function Evidence({ items }) {
  if (!items?.length) return null;
  return (
    <details className="evidence-list">
      <summary>Data used ({items.length})</summary>
      <ul>{items.map((e, i) => <li key={i}>{describe(e)}</li>)}</ul>
    </details>
  );
}

/** Docked chat window (bottom-right), collapsible like a messaging bar. */
export default function AssistantPanel({ country, focusedId, focusedArea, selectedIds, threshold }) {
  const status = useApi(() => api.assistantStatus(), []);
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const configured = status.data?.configured;
  const context = focusedArea ? `${focusedArea.name} (${focusedArea.level})` : null;

  useEffect(() => { if (open) inputRef.current?.focus?.(); }, [open]);

  const newChat = () => { setMessages([]); setError(null); setMenu(false); setOpen(true); };

  const ask = async (text) => {
    const q = (text ?? question).trim();
    if (!q || busy) return;
    setQuestion("");
    setError(null);
    setBusy(true);
    const history = messages.filter((m) => m.text).map((m) => ({ role: m.role, content: m.text }));
    setMessages((m) => [...m, { role: "user", text: q }]);
    try {
      const res = await api.ask({
        question: q, history, selected_cell_ids: selectedIds, focused_cell_id: focusedId, threshold,
        focused_area: focusedArea
          ? { name: focusedArea.name, level: focusedArea.level, cell_ids: focusedArea.cellIds }
          : null,
      }, country);
      setMessages((m) => [...m, { role: "assistant", text: res.answer, status: res.status, message: res.message,
                                  evidence: res.evidence, reportIds: res.report_cell_ids }]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
      setTimeout(() => endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" }), 50);
    }
  };

  const downloadReport = async (ids) => {
    try {
      downloadBlob(await api.reportFile("pdf", ids, threshold, country), `solar-market-report-${ids.length}-areas.pdf`);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <section className={`chat-dock ${open ? "open" : ""}`} aria-label="AI assistant">
      <header className="dock-head">
        <button className="dock-title" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="dock-body">
          <span className="dock-avatar" aria-hidden="true">
            <span className={`dock-status ${configured ? "on" : "off"}`} />
          </span>
          <span className="dock-name">Solar Assistant</span>
        </button>
        <div className="dock-actions">
          <button className="dock-icon" aria-label="More options" aria-expanded={menu} onClick={() => setMenu(!menu)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>
          </button>
          <button className="dock-icon" aria-label="New conversation" onClick={newChat}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10.5-10.5-4-4L4 16v4zM16 3.5l4 4" fill="none" strokeWidth="2" strokeLinejoin="round" /></svg>
          </button>
          <button className="dock-icon" aria-label={open ? "Minimise assistant" : "Open assistant"} onClick={() => setOpen(!open)}>
            <svg viewBox="0 0 24 24" aria-hidden="true" className={open ? "flip" : ""}><path d="M6 15l6-6 6 6" fill="none" strokeWidth="2.4" strokeLinecap="round" /></svg>
          </button>
        </div>
        {menu && (
          <ul className="dock-menu" role="menu">
            <li role="menuitem"><button onClick={newChat}>New conversation</button></li>
            <li role="menuitem" className="dock-menu-note">
              {configured ? `Model: ${status.data.model}` : "Not configured: set ANTHROPIC_API_KEY in backend/.env"}
            </li>
          </ul>
        )}
      </header>

      {open && (
        <div className="dock-body" id="dock-body">
          <p className="dock-context">
            Answers use only this tool's data{context ? `, starting from ${context}` : ""}
            {selectedIds.length ? " and your selection" : ""}.
          </p>
          {status.data && !configured && (
            <p className="hint">The language model is not configured (set ANTHROPIC_API_KEY on the backend). You will still see the data each question looks up.</p>
          )}
          <div className="chat" role="log" aria-live="polite">
            {!messages.length && (
              <div className="suggestions">
                {SUGGESTIONS.map((s) => <button key={s} className="suggestion" onClick={() => ask(s)}>{s}</button>)}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg msg-${m.role}`}>
                {m.text && <p className="msg-text">{m.text}</p>}
                {!m.text && m.message && <p className="msg-text muted">{m.message}</p>}
                {m.role === "assistant" && <Evidence items={m.evidence} />}
                {m.reportIds?.length > 0 && (
                  <button className="secondary" onClick={() => downloadReport(m.reportIds)}>Download report (PDF)</button>
                )}
              </div>
            ))}
            {busy && <div className="msg msg-assistant"><span className="spinner" aria-hidden="true" /> Looking up the data...</div>}
            <div ref={endRef} />
          </div>
          {error && <p className="error-text" role="alert">{error}</p>}
          <form className="dock-input" onSubmit={(e) => { e.preventDefault(); ask(); }}>
            <label htmlFor="assistant-q" className="visually-hidden">Question</label>
            <input id="assistant-q" ref={inputRef} value={question} maxLength={1000}
                   onChange={(e) => setQuestion(e.target.value)} placeholder="Write a question..." />
            <button type="submit" className="primary" disabled={busy || !question.trim()}>Ask</button>
          </form>
        </div>
      )}
    </section>
  );
}
