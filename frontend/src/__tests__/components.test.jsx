import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/api", () => ({
  api: {
    cell: vi.fn(),
    reportSummary: vi.fn(),
    reportFile: vi.fn(),
    assistantStatus: vi.fn(),
    ask: vi.fn(),
    searchLocation: vi.fn(),
  },
  downloadBlob: vi.fn(),
  errorMessage: (err) => err.message,
}));

import AssistantPanel from "../components/AssistantPanel";
import CellPanel from "../components/CellPanel";
import Header from "../components/Header";
import Legend from "../components/Legend";
import SelectionPanel from "../components/SelectionPanel";
import Sidebar from "../components/Sidebar";
import { api, downloadBlob } from "../services/api";

const indicator = (key, label, formatted, kind = "external_estimate", extra = {}) => ({
  key, label, formatted, value: 1, display_value: 1, unit: "", kind, kind_label: kind, source: "WorldPop 2020",
  source_year: "2020", status: "available", description: "", ...extra,
});

const CELL = {
  cell_id: "RW_0500", place_name: "Rubona, Hindiro", latitude: -2.0, longitude: 29.6, district: "Ngororero", province: "Western Province",
  market_gap_score: 0.52, opportunity_score: 52, potentially_underserved: false, evidence_level: "indicative",
  interpretation: "Lower relative priority. This is a screening result.",
  drivers: [{ factor: "Population density", value: 0.9, note: "" }],
  model_status: { usable: false, reason: "Trained on synthetic labels." },
  indicators: [
    indicator("population_density", "Population density", "808 people/km²"),
    indicator("nighttime_radiance", "Nighttime radiance", "0.21 nW/cm²/sr", "observed"),
    indicator("predicted_solar_penetration", "Predicted solar penetration", "Not available", "model_prediction",
              { status: "missing" }),
  ],
};

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("Sidebar", () => {
  const layers = [
    { id: "market_gap", name: "Potential Market Gap", description: "Score", selector: true },
    { id: "population", name: "Population Density", description: "WorldPop", selector: true },
    { id: "population_total", name: "Total Population", description: "", selector: false },
  ];
  const props = {
    country: "RW", layers, layer: "market_gap", onLayer: vi.fn(), opacity: 0.8, onOpacity: vi.fn(),
    threshold: 0.55, onThreshold: vi.fn(), showInfra: false, onShowInfra: vi.fn(),
    clickSelects: false, onClickSelects: vi.fn(), onLocation: vi.fn(), adminLevel: "cell", onAdminLevel: vi.fn(),
  };

  it("lets the user choose the administrative boundary level", () => {
    render(<Sidebar {...props} />);
    const select = screen.getByLabelText("Show the map by");
    expect([...select.options].map((o) => o.textContent)).toEqual(
      ["Province", "District", "Sector", "Cell", "Village", "5 km analysis grid"]);
    fireEvent.change(select, { target: { value: "district" } });
    expect(props.onAdminLevel).toHaveBeenCalledWith("district");
  });

  it("lists only selector layers and hides Total Population", () => {
    render(<Sidebar {...props} />);
    expect(screen.getByLabelText("Potential Market Gap")).toBeTruthy();
    expect(screen.queryByText("Total Population")).toBeNull();
    expect(screen.queryByText(/demo/i)).toBeNull();
  });

  it("toggles the infrastructure overlay", () => {
    render(<Sidebar {...props} />);
    fireEvent.click(screen.getByLabelText(/mapped power lines/i));
    expect(props.onShowInfra).toHaveBeenCalledWith(true);
  });

  it("explains unmatched locations", async () => {
    api.searchLocation.mockResolvedValue({ matched: false, note: "Villages cannot be matched." });
    render(<Sidebar {...props} />);
    fireEvent.change(screen.getByLabelText("Find a location"), { target: { value: "Gikomero village" } });
    fireEvent.click(screen.getByText("Find"));
    expect(await screen.findByText("Villages cannot be matched.")).toBeTruthy();
    expect(props.onLocation).not.toHaveBeenCalled();
  });
});

describe("CellPanel", () => {
  it("shows the population density value, unit and source for the selected cell", async () => {
    api.cell.mockResolvedValue(CELL);
    render(<CellPanel cellId="RW_0500" threshold={0.55} layer="population" isSelected={false} onToggleSelect={vi.fn()} />);
    const highlight = await screen.findByLabelText("Population density for this cell");
    expect(highlight.textContent).toContain("808 people/km²");
    expect(highlight.textContent).toContain("WorldPop 2020");
    expect(screen.getByText("52 / 100")).toBeTruthy();
  });

  it("hides model predictions when the model is not usable, and toggles selection", async () => {
    api.cell.mockResolvedValue(CELL);
    const onToggle = vi.fn();
    render(<CellPanel cellId="RW_0500" threshold={0.55} layer="market_gap" isSelected={false} onToggleSelect={onToggle} />);
    await screen.findByText("Rubona, Hindiro");
    expect(screen.queryByText("RW_0500")).toBeNull();
    expect(screen.queryByText("Predicted solar penetration")).toBeNull();
    expect(screen.getByText(/Trained on synthetic labels/)).toBeTruthy();
    fireEvent.click(screen.getByText("Add to selection"));
    expect(onToggle).toHaveBeenCalledWith(expect.objectContaining({ key: "RW_0500", name: "Rubona, Hindiro" }));
  });

  it("prompts the user when no cell is selected", () => {
    render(<CellPanel cellId={null} threshold={0.55} layer="market_gap" />);
    expect(screen.getByText(/Click an area on the map/)).toBeTruthy();
  });
});

describe("SelectionPanel", () => {
  const report = {
    title: "Solar market reality: 2 selected locations", generated_at: "2026-10-12 21:00 UTC", threshold_score: 55,
    national: { median: 49 }, method: { interpretation: "Relative score." },
    summary: { n_cells: 2, area_km2: 50, population_total: 30000, population_density: 600, score_min: 41, score_max: 52 },
    interpretation: ["None of the 2 scored cells reaches the priority cut-off."],
    cells: ["RW_0500", "RW_0501"].map((id, i) => ({
      cell_id: id, name: ["Rubona, Hindiro", "Gashubi, Kabaya"][i], district: "Ngororero", opportunity_score: 41 + i * 11, flagged: false,
      indicators: { population_density: { value: 600 }, nighttime_radiance: { value: 0.2 },
                    distance_to_grid_km: { value: 4 }, survey_solar_share: { display_value: 13.6 } },
    })),
  };

  it("shows an empty state without a selection", () => {
    render(<SelectionPanel country="RW" items={[]} limit={500} threshold={0.55} />);
    expect(screen.getByText(/Nothing selected/)).toBeTruthy();
    expect(screen.queryByText("Generate report")).toBeNull();
  });

  it("generates a report for exactly the selected cells and downloads the PDF", async () => {
    api.reportSummary.mockResolvedValue(report);
    api.reportFile.mockResolvedValue(new Blob(["%PDF"]));
    const onRemove = vi.fn();
    const items = [{ key: "cell:1", name: "Kabuga", level: "cell", cellIds: ["RW_0500"] },
                   { key: "cell:2", name: "Rugende", level: "cell", cellIds: ["RW_0501", "RW_0500"] }];
    render(<SelectionPanel country="RW" items={items} limit={500} threshold={0.55}
                           onRemove={onRemove} onClear={vi.fn()} onFocus={vi.fn()} />);
    fireEvent.click(screen.getByText("Generate report"));
    expect(await screen.findByText(report.title)).toBeTruthy();
    expect(screen.getAllByText("Rubona, Hindiro").length).toBeGreaterThan(0);
    expect(screen.queryByText("RW_0500")).toBeNull();
    expect(api.reportSummary).toHaveBeenCalledWith(["RW_0500", "RW_0501"], 0.55, "RW",
      "Solar market reality: Kabuga, Rugende");
    fireEvent.click(screen.getByText("Download PDF"));
    await waitFor(() => expect(downloadBlob).toHaveBeenCalled());
    expect(api.reportFile).toHaveBeenCalledWith("pdf", ["RW_0500", "RW_0501"], 0.55, "RW",
      "Solar market reality: Kabuga, Rugende");
    fireEvent.click(screen.getByLabelText("Remove Rugende"));
    expect(onRemove).toHaveBeenCalledWith("cell:2");
  });

  it("shows API errors", async () => {
    api.reportSummary.mockRejectedValue(new Error("Unknown cell IDs: RW_9999"));
    render(<SelectionPanel country="RW" items={[{ key: "x", name: "X", level: "grid", cellIds: ["RW_9999"] }]}
                           limit={500} threshold={0.55} />);
    fireEvent.click(screen.getByText("Generate report"));
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});

describe("AssistantPanel (docked)", () => {
  it("is collapsed by default and opens like a messaging bar", async () => {
    api.assistantStatus.mockResolvedValue({ configured: true, model: "gemini-3.6-flash" });
    render(<AssistantPanel country="RW" focusedId={null} selectedIds={[]} threshold={0.55} />);
    expect(screen.getByText("Solar Assistant")).toBeTruthy();
    expect(screen.queryByLabelText("Question")).toBeNull();
    fireEvent.click(screen.getByLabelText("Open assistant"));
    expect(screen.getByLabelText("Question")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Minimise assistant"));
    expect(screen.queryByLabelText("Question")).toBeNull();
  });

  it("shows the not-configured state and the data looked up, by name", async () => {
    api.assistantStatus.mockResolvedValue({ configured: false });
    api.ask.mockResolvedValue({ status: "not_configured", answer: null, message: "Set ANTHROPIC_API_KEY.",
                                evidence: [{ tool: "summarize_cells", input: { cell_ids: ["RW_0217"] },
                                             result: { summary: { districts: [{ district: "Gatsibo" }] } } }] });
    const area = { name: "Rwimiyaga", level: "sector", cellIds: ["RW_0217"] };
    render(<AssistantPanel country="RW" focusedArea={area} selectedIds={[]} threshold={0.55} />);
    fireEvent.click(screen.getByLabelText("Open assistant"));
    expect(await screen.findByText(/not configured/)).toBeTruthy();
    expect(screen.getByText(/starting from Rwimiyaga \(sector\)/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "What about this area?" } });
    fireEvent.click(screen.getByText("Ask"));
    expect(await screen.findByText("Set ANTHROPIC_API_KEY.")).toBeTruthy();
    expect(screen.getByText("Summarised areas: Gatsibo (1 analysis areas)")).toBeTruthy();
    expect(api.ask.mock.calls[0][0]).toMatchObject({
      focused_area: { name: "Rwimiyaga", level: "sector", cell_ids: ["RW_0217"] } });
  });

  it("renders answers, request errors and starts a new conversation", async () => {
    api.assistantStatus.mockResolvedValue({ configured: true, model: "gemini-3.6-flash" });
    api.ask.mockResolvedValueOnce({ status: "ok", answer: "Ngoma scores 40/100.", evidence: [] })
           .mockRejectedValueOnce(new Error("The request timed out."));
    render(<AssistantPanel country="RW" focusedId={null} selectedIds={["RW_0500"]} threshold={0.55} />);
    fireEvent.click(screen.getByLabelText("Open assistant"));
    fireEvent.click(screen.getByText(/Does low nighttime radiance/));
    expect(await screen.findByText("Ngoma scores 40/100.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "And Bugesera?" } });
    fireEvent.click(screen.getByText("Ask"));
    expect(await screen.findByText("The request timed out.")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("New conversation"));
    expect(screen.queryByText("Ngoma scores 40/100.")).toBeNull();
  });
});

describe("Legend and navigation", () => {
  it("shows units, no-data cells and infrastructure symbols", () => {
    const meta = { layer: "population", name: "Population Density", unit: "people/km²", scale: "log", min: 50, max: 5000,
                   legend: { low: "Sparse", mid: "Medium", high: "Dense" }, n_missing: 166, kind: "External modelled estimate",
                   source: "WorldPop", source_date: "2020" };
    render(<Legend meta={meta} showInfra infraMeta={{ counts: { grid_line: 138 } }} />);
    expect(screen.getByText(/No data \(166 cells\)/)).toBeTruthy();
    expect(screen.getByText("Power line (OSM)")).toBeTruthy();
    expect(screen.getByText(/No verified minigrid dataset/)).toBeTruthy();
  });

  it("includes an About link and no demo badge", () => {
    render(<MemoryRouter><Header /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "About" }).getAttribute("href")).toBe("/about");
    expect(screen.queryByText(/demo data/i)).toBeNull();
  });
});
