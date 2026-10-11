import { useEffect, useState } from "react";
import AsyncView, { ErrorBox, Loading } from "../components/AsyncView";
import CellPanel from "../components/CellPanel";
import ConceptBand from "../components/ConceptBand";
import ExploreAssistant from "../components/ExploreAssistant";
import Legend from "../components/Legend";
import MapView from "../components/MapView";
import Sidebar from "../components/Sidebar";
import StatCards from "../components/StatCards";
import { useApi } from "../hooks/useApi";
import { useDebounce } from "../hooks/useDebounce";
import { api } from "../services/api";

export default function DashboardPage({ country, setCountry, meta, countries }) {
  const [layer, setLayer] = useState("solar_penetration");
  const [opacity, setOpacity] = useState(0.8);
  const [threshold, setThreshold] = useState(meta.underserved_threshold);
  const [showInfra, setShowInfra] = useState(false);
  const [selected, setSelected] = useState(null);
  const debounced = useDebounce(threshold, 300);

  useEffect(() => setSelected(null), [country]);

  const layers = useApi(() => api.layers(), []);
  const layerData = useApi(() => api.layer(layer, country), [layer, country]);
  const infra = useApi(() => api.infrastructure(country), [country]);
  const stats = useApi(() => api.statistics(country, debounced), [country, debounced]);
  const countryInfo = countries.find((c) => c.code === country);

  return (
    <>
      <ConceptBand />
      <div className="dash">
        <AsyncView state={layers} label="Loading layers...">
          {(ls) => (
            <Sidebar countries={countries} country={country} onCountry={setCountry} layers={ls} layer={layer}
                     onLayer={setLayer} opacity={opacity} onOpacity={setOpacity} threshold={threshold}
                     onThreshold={setThreshold} showInfra={showInfra} onShowInfra={setShowInfra} />
          )}
        </AsyncView>

        <div className="map-wrap">
          <MapView
            layerData={layerData.status === "done" ? layerData.data : null}
            infra={infra.data} showInfra={showInfra} bounds={meta.bounds}
            center={countryInfo?.center ?? [-1.95, 29.87]} zoom={countryInfo?.zoom ?? 8}
            opacity={opacity} threshold={debounced} selectedId={selected} onSelect={setSelected}
          />
          {layerData.status === "loading" && <div className="map-overlay"><Loading label="Loading layer..." /></div>}
          {layerData.status === "error" && <div className="map-overlay"><ErrorBox message={layerData.error} /></div>}
          {layerData.status === "done" && <Legend meta={layerData.data.metadata} />}
          {meta.is_demo && <span className="map-demo">DEMO DATA</span>}
        </div>

        <CellPanel cellId={selected} threshold={debounced} />
      </div>

      <AsyncView state={stats} label="Calculating statistics...">{(s) => <StatCards s={s} />}</AsyncView>
      <p className="muted disclaimer">{meta.disclaimer}</p>

      <ExploreAssistant
        layerData={layerData.status === "done" ? layerData.data : null}
        stats={stats.status === "done" ? stats.data : null}
        meta={layerData.status === "done" ? layerData.data.metadata : null}
        selectedId={selected}
        onJumpToCell={setSelected}
      />
    </>
  );
}