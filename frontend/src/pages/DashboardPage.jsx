import { useEffect, useMemo, useState } from "react";
import AreaPanel from "../components/AreaPanel";
import AssistantPanel from "../components/AssistantPanel";
import AsyncView, { ErrorBox, Loading } from "../components/AsyncView";
import CellPanel from "../components/CellPanel";
import ConceptBand from "../components/ConceptBand";
import Legend from "../components/Legend";
import MapView from "../components/MapView";
import SelectionPanel from "../components/SelectionPanel";
import Sidebar from "../components/Sidebar";
import StatCards from "../components/StatCards";
import { useApi } from "../hooks/useApi";
import { useDebounce } from "../hooks/useDebounce";
import { useSelection } from "../hooks/useSelection";
import { api } from "../services/api";
import { boundsForAdminFeatures, buildAdminLayer } from "../utils/adminAreas";

const TABS = [["details", "Details"], ["selection", "Selection & report"]];

/** Selection/focus item for a clicked map feature (administrative area or 5 km grid cell). */
function itemFromFeature(p) {
  if (p.admin_key) {
    return { key: p.admin_key, name: p.admin_name, level: p.admin_level, cellIds: p.source_cell_ids || [],
             value: p.value, centreFallback: p.centre_fallback };
  }
  return { key: p.cell_id, name: p.name ?? p.cell_id, level: "grid", cellIds: [p.cell_id], value: p.value };
}

const cellItem = (id, name) => ({ key: id, name: name ?? id, level: "grid", cellIds: [id] });

export default function DashboardPage({ country, meta, countries }) {
  const [layer, setLayer] = useState("market_gap");
  const [adminLevel, setAdminLevel] = useState("cell");
  const [opacity, setOpacity] = useState(0.8);
  const [threshold, setThreshold] = useState(meta.underserved_threshold);
  const [showInfra, setShowInfra] = useState(false);
  const [clickSelects, setClickSelects] = useState(false);
  const [focused, setFocused] = useState(null);
  const [tab, setTab] = useState("details");
  const [flyTo, setFlyTo] = useState(null);
  const selection = useSelection(500);
  const debounced = useDebounce(threshold, 300);

  const layers = useApi(() => api.layers(country), [country]);
  const gridLayer = useApi(() => api.layer(layer, country), [layer, country]);
  const layerData = useApi(
    async () => (gridLayer.status === "done" ? buildAdminLayer(gridLayer.data, adminLevel, country) : null),
    [gridLayer.status, gridLayer.data, adminLevel, country],
  );
  const infra = useApi(() => (showInfra ? api.infrastructure(country) : Promise.resolve(null)), [country, showInfra]);
  const stats = useApi(() => api.statistics(country, debounced), [country, debounced]);
  const countryInfo = countries.find((c) => c.code === country);
  const activeLayer = layerData.status === "done" ? layerData.data : null;
  const mapLoading = gridLayer.status === "loading" || layerData.status === "loading";
  const mapError = gridLayer.status === "error" ? gridLayer.error : layerData.status === "error" ? layerData.error : null;

  // A different boundary level shows different areas: the focused one no longer exists.
  useEffect(() => setFocused(null), [adminLevel]);

  // Keep the focused area's displayed value in step with the active layer.
  const focusedItem = useMemo(() => {
    if (!focused || !activeLayer) return focused;
    const feature = activeLayer.features.find((f) => (f.properties.admin_key ?? f.properties.cell_id) === focused.key);
    return feature ? itemFromFeature(feature.properties) : focused;
  }, [focused, activeLayer]);

  const onAreaClick = (props, event) => {
    const item = itemFromFeature(props);
    const toggles = clickSelects || event?.ctrlKey || event?.metaKey;
    if (toggles) selection.toggle(item);
    setFocused(item);
    if (!toggles && tab === "selection") setTab("details");
  };

  const onLocation = (result, addAll) => {
    const item = { key: `search:${result.type}:${result.name}`, name: result.name, level: result.type,
                   cellIds: result.cell_ids };
    if (addAll) {
      selection.add([item]);
      setTab("selection");
    } else {
      setFocused(result.cell_ids.length === 1 ? cellItem(result.cell_ids[0], result.name) : item);
      setTab("details");
    }
    if (gridLayer.data) {
      const ids = new Set(result.cell_ids);
      setFlyTo(boundsForAdminFeatures(gridLayer.data.features.filter((f) => ids.has(f.properties.cell_id))));
    }
  };

  const toggleItem = (item) => selection.toggle(item);

  return (
    <>
      <ConceptBand />
      <div className="dash">
        <AsyncView state={layers} label="Loading layers...">
          {(ls) => (
            <Sidebar
              country={country} layers={ls} layer={layer} onLayer={setLayer}
              opacity={opacity} onOpacity={setOpacity} threshold={threshold} onThreshold={setThreshold}
              showInfra={showInfra} onShowInfra={setShowInfra}
              clickSelects={clickSelects} onClickSelects={setClickSelects} onLocation={onLocation}
              adminLevel={adminLevel} onAdminLevel={setAdminLevel}
            />
          )}
        </AsyncView>

        <div className="map-wrap">
          <MapView
            layerData={activeLayer} infra={infra.data} showInfra={showInfra} bounds={meta.bounds} flyTo={flyTo}
            center={countryInfo?.center ?? [-1.95, 29.87]} zoom={countryInfo?.zoom ?? 8}
            opacity={opacity} threshold={debounced} focusedKey={focusedItem?.key} selectedKeys={selection.keys}
            onAreaClick={onAreaClick} adminLevel={adminLevel}
          />
          {mapLoading && (
            <div className="map-overlay">
              <Loading label={adminLevel === "grid" ? "Loading layer..." : "Loading administrative boundaries..."} />
            </div>
          )}
          {mapError && <div className="map-overlay"><ErrorBox message={mapError} /></div>}
          {showInfra && infra.status === "error" && <div className="map-note" role="alert">Infrastructure could not be loaded.</div>}
          {activeLayer && <Legend meta={activeLayer.metadata} showInfra={showInfra} infraMeta={infra.data?.metadata} />}
          {showInfra && infra.data?.metadata && <div className="map-note">{infra.data.metadata.caveat}</div>}
        </div>

        <div className="side-stack">
          <div className="tabs" role="tablist" aria-label="Panels">
            {TABS.map(([id, label]) => (
              <button key={id} role="tab" id={`tab-${id}`} aria-selected={tab === id} aria-controls={`panel-${id}`}
                      className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
                {label}{id === "selection" && selection.items.length ? ` (${selection.items.length})` : ""}
              </button>
            ))}
          </div>
          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === "details" && (focusedItem && focusedItem.level !== "grid" ? (
              <AreaPanel area={focusedItem} layerMeta={activeLayer?.metadata} country={country} threshold={debounced}
                         isSelected={selection.has(focusedItem.key)} onToggleSelect={toggleItem}
                         onOpenCell={(id, name) => setFocused(cellItem(id, name))} />
            ) : (
              <CellPanel cellId={focusedItem?.key ?? null} threshold={debounced} layer={layer}
                         isSelected={focusedItem != null && selection.has(focusedItem.key)} onToggleSelect={toggleItem} />
            ))}
            {tab === "selection" && (
              <SelectionPanel country={country} items={selection.items} limit={selection.limit} threshold={debounced}
                              onRemove={selection.remove} onClear={selection.clear}
                              onFocus={(item) => { setFocused(item); setTab("details"); }} />
            )}
          </div>
        </div>
      </div>

      <AssistantPanel country={country} focusedId={focusedItem?.level === "grid" ? focusedItem.key : null}
                      focusedArea={focusedItem && focusedItem.level !== "grid" ? focusedItem : null}
                      selectedIds={selection.cellIds} threshold={debounced} />

      <AsyncView state={stats} label="Calculating statistics...">{(s) => <StatCards s={s} />}</AsyncView>
      <p className="muted disclaimer">{meta.disclaimer}</p>
    </>
  );
}
