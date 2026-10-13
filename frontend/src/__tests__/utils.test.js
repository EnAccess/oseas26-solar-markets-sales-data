import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useSelection } from "../hooks/useSelection";
import { NO_DATA, normalizer, rampColor } from "../utils/colors";
import { fmtLayerValue, fmtScore } from "../utils/format";

describe("formatting", () => {
  it("shows the opportunity score as an integer out of 100, never a percentage", () => {
    expect(fmtScore(0.523)).toBe("52 / 100");
    expect(fmtScore(null)).toBe("No score");
  });

  it("formats layer values with their units", () => {
    expect(fmtLayerValue(807.8, "people/km²")).toBe("808 people/km²");
    expect(fmtLayerValue(13.6, "% of households")).toBe("13.6%");
    expect(fmtLayerValue(52, "score 0–100")).toBe("52 / 100");
    expect(fmtLayerValue(null, "km")).toBe("No data");
  });
});

describe("colour scales", () => {
  it("renders missing values in the no-data colour", () => {
    const norm = normalizer({ min: 0, max: 10, scale: "linear" });
    expect(norm(null)).toBeNull();
    expect(rampColor(["#000000", "#ffffff"], norm(null))).toBe(NO_DATA);
    expect(norm(5)).toBeCloseTo(0.5);
  });

  it("supports log scales without failing on zero", () => {
    const norm = normalizer({ min: 0.01, max: 100, scale: "log" });
    expect(norm(0)).toBe(0);
    expect(norm(100)).toBeCloseTo(1);
  });
});

const area = (key, cellIds = [key]) => ({ key, name: key, level: "district", cellIds });

describe("useSelection", () => {
  it("adds, deduplicates, toggles, removes and clears areas", () => {
    const { result } = renderHook(() => useSelection(3));
    act(() => result.current.add([area("A", ["RW_0001", "RW_0002"]), area("B", ["RW_0002"]), area("A")]));
    expect(result.current.keys).toEqual(["A", "B"]);
    expect(result.current.cellIds).toEqual(["RW_0001", "RW_0002"]);
    act(() => result.current.toggle(area("B")));
    expect(result.current.keys).toEqual(["A"]);
    act(() => result.current.toggle(area("C")));
    expect(result.current.has("C")).toBe(true);
    act(() => result.current.remove("A"));
    expect(result.current.keys).toEqual(["C"]);
    act(() => result.current.clear());
    expect(result.current.items).toEqual([]);
  });

  it("enforces the selection limit", () => {
    const { result } = renderHook(() => useSelection(2));
    act(() => result.current.add([area("A"), area("B"), area("C")]));
    expect(result.current.keys).toEqual(["A", "B"]);
    act(() => result.current.toggle(area("D")));
    expect(result.current.keys).toEqual(["A", "B"]);
  });
});
