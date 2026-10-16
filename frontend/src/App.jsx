import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import AsyncView from "./components/AsyncView";
import Header from "./components/Header";
import { useApi } from "./hooks/useApi";
import AboutPage from "./pages/AboutPage";
import DashboardPage from "./pages/DashboardPage";
import DataPage from "./pages/DataPage";
import LimitationsPage from "./pages/LimitationsPage";
import ModelPage from "./pages/ModelPage";
import { api } from "./services/api";
import { fmtDate } from "./utils/format";

export default function App() {
  const [country, setCountry] = useState("RW");
  const meta = useApi(() => api.meta(country), [country]);
  const countries = useApi(() => api.countries(), []);

  return (
    <>
      <Header />
      <main className="page" id="main">
        <AsyncView state={meta} label="Loading the processed dataset...">
          {(m) => (
            <Routes>
              <Route path="/" element={
                <DashboardPage country={country} setCountry={setCountry} meta={m} countries={countries.data ?? []} />} />
              <Route path="/about" element={<AboutPage meta={m} />} />
              <Route path="/model" element={<ModelPage country={country} meta={m} />} />
              <Route path="/data" element={<DataPage country={country} meta={m} />} />
              <Route path="/limitations" element={<LimitationsPage />} />
              <Route path="*" element={<p className="state">Page not found.</p>} />
            </Routes>
          )}
        </AsyncView>
      </main>
      {meta.data && (
        <footer className="site-footer">
          {meta.data.country_name} · 5 km analysis grid · dataset built {fmtDate(meta.data.built_at)} ·{" "}
          {meta.data.is_demo ? "synthetic demo dataset" : "real data sources, see Data sources for dates and licences"}
        </footer>
      )}
    </>
  );
}
