"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import { api, apiBase } from "@/lib/api";
import type {
  CameraPreset,
  DataSummary,
  IsolatableKind,
  OptimizeResponse,
  SceneSelection,
  TwinSnapshot,
  ViewMode,
  WellTelemetry,
  WellsResponse,
} from "@/lib/types";
import Inspector from "@/components/Inspector";
import Logo from "@/components/Logo";

const FieldScene = dynamic(() => import("@/components/FieldScene"), { ssr: false });

export default function Home() {
  const [wells, setWells] = useState<WellsResponse | null>(null);
  const [twins, setTwins] = useState<Record<string, TwinSnapshot>>({});
  const [telemetries, setTelemetries] = useState<Record<string, WellTelemetry>>({});
  const [opts, setOpts] = useState<Record<string, OptimizeResponse>>({});
  const [selectedWellId, setSelectedWellId] = useState<string | null>(null);
  const [selection, setSelection] = useState<SceneSelection | null>(null);
  const [preset, setPreset] = useState<CameraPreset>("FIELD");
  const [viewMode, setViewMode] = useState<ViewMode>("CUTAWAY");
  const [isolated, setIsolated] = useState<IsolatableKind | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [optLoading, setOptLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);

  const loadWell = useCallback(async (id: string) => {
    const [w, t] = await Promise.all([api.well(id), api.twin(id)]);
    setTelemetries((p) => ({ ...p, [id]: w }));
    setTwins((p) => ({ ...p, [id]: t }));
    return { w, t };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await api.health();
      setConnected(true);
      api.dataSummary().then(setDataSummary).catch(() => setDataSummary(null));
      const wl = await api.wells();
      setWells(wl);
      if (wl.wells.length > 0) {
        const id =
          selectedWellId && wl.wells.some((w) => w.well_id === selectedWellId)
            ? selectedWellId
            : wl.wells[0].well_id;
        setSelectedWellId(id);
        // Twin state for every known well drives per-well thermal glow.
        await Promise.all(
          wl.wells.map(async (w) => {
            try {
              const t = await api.twin(w.well_id);
              setTwins((p) => ({ ...p, [w.well_id]: t }));
              if (w.well_id === id) {
                const full = await api.well(w.well_id);
                setTelemetries((p) => ({ ...p, [w.well_id]: full }));
              }
            } catch {
              /* per-well failure must not break the field view */
            }
          })
        );
        setSelection((s) =>
          s && wl.wells.some((w) => w.well_id === s.wellId)
            ? s
            : { kind: "well", wellId: id, label: `Well — ${id}` }
        );
      } else {
        setSelectedWellId(null);
      }
    } catch (e) {
      setConnected(false);
      setError(e instanceof Error ? e.message : "Backend unreachable");
    } finally {
      setLoading(false);
    }
  }, [selectedWellId]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pickWell = async (id: string) => {
    setSelectedWellId(id);
    setSelection({ kind: "well", wellId: id, label: `Well — ${id}` });
    setIsolated(null);
    setPreset("WELL");
    try {
      await loadWell(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load well");
    }
  };

  const seedDemo = async () => {
    setSeeding(true);
    try {
      await api.ingestDemo("BGW-DEMO");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Demo seed failed");
    } finally {
      setSeeding(false);
    }
  };

  const runOptimize = async () => {
    if (!selectedWellId) return;
    setOptLoading(true);
    try {
      const o = await api.optimize(selectedWellId);
      setOpts((p) => ({ ...p, [selectedWellId]: o }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Optimization failed");
    } finally {
      setOptLoading(false);
    }
  };

  const twin = selectedWellId ? (twins[selectedWellId] ?? null) : null;
  const telemetry = selectedWellId ? (telemetries[selectedWellId] ?? null) : null;
  const presets: { id: CameraPreset; label: string }[] = [
    { id: "FIELD", label: "▦ FIELD" },
    { id: "WELL", label: "◉ WELL" },
    { id: "WELLBORE", label: "⛏ WELLBORE" },
    { id: "RESERVOIR", label: "▼ RESERVOIR" },
    { id: "PUMP", label: "⬣ PUMP" },
  ];
  const viewModes: ViewMode[] = ["NORMAL", "CUTAWAY", "XRAY"];

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-[#070b14]">
      {/* Top bar */}
      <header className="glass border-b border-slate-700/40 px-4 py-2.5 flex flex-wrap items-center gap-3 z-10">
        <a href="/" className="flex items-center gap-2.5" title="Back to PetroForge home">
          <Logo size={36} />
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold tracking-wide text-sm">
                <span className="text-sand">PETRO</span><span className="text-leaf">FORGE</span>
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-clay/15 text-sand border border-clay/40">
                SIH26120
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-stone-700/60 text-stone-300 border border-stone-600/50">
                Oil India Limited
              </span>
            </div>
            <div className="text-[11px] text-slate-400">
              3D Digital Twin — CSS + SRP · Baghewala heavy oil wells
            </div>
          </div>
        </a>
        <div className="flex-1" />
        <select
          value={selectedWellId ?? ""}
          onChange={(e) => e.target.value && pickWell(e.target.value)}
          className="bg-slate-800/80 border border-slate-600/60 rounded-lg text-xs px-2 py-1.5 font-mono w-52"
        >
          {(wells?.wells ?? []).map((w) => (
            <option key={w.well_id} value={w.well_id}>
              {w.well_id} · {w.css_phase}
            </option>
          ))}
          {(!wells || wells.wells.length === 0) && <option value="">— no wells —</option>}
        </select>
        <div className="flex items-center gap-1.5 text-[11px] font-mono">
          <span
            className={`h-2 w-2 rounded-full ${
              connected === null ? "bg-slate-500" : connected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
            }`}
          />
          <span className={connected ? "text-emerald-300" : "text-slate-400"}>
            {connected === null ? "CHECKING…" : connected ? "BACKEND CONNECTED" : "BACKEND OFFLINE"}
          </span>
        </div>
        <button
          onClick={refresh}
          className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg bg-slate-700/70 hover:bg-slate-600/70 border border-slate-600/60"
        >
          REFRESH
        </button>
      </header>

      {error && (
        <div className="px-4 py-2 text-xs font-mono text-rose-200 bg-rose-500/10 border-b border-rose-500/30">
          Unable to load well data: {error} — backend at {apiBase()}. Start FastAPI first.
        </div>
      )}

      {/* Main: viewport + inspector */}
      <div className="flex-1 flex min-h-0 relative">
        <div className="flex-1 relative min-w-0">
          {wells && wells.wells.length > 0 ? (
            <FieldScene
              wells={wells.wells}
              twins={twins}
              selection={selection}
              onSelect={setSelection}
              onDeselect={() => setSelection(null)}
              preset={preset}
              focusWellId={selectedWellId}
              viewMode={viewMode}
              isolated={isolated}
            />
          ) : (
            !loading && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="glass rounded-2xl p-8 text-center space-y-3 max-w-md">
                  <div className="font-bold">No well telemetry available.</div>
                  <p className="text-xs text-slate-400">
                    Ingest a well via the API, or load the BGW-DEMO baseline through the
                    real ingest endpoint.
                  </p>
                  <button
                    onClick={seedDemo}
                    disabled={seeding || connected === false}
                    className="px-4 py-2 rounded-lg bg-gradient-to-r from-forest-700 to-leaf text-white text-xs font-bold disabled:opacity-40"
                  >
                    {seeding ? "Loading…" : "Load BGW-DEMO baseline"}
                  </button>
                </div>
              </div>
            )
          )}
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-xs font-mono text-slate-400">Loading well state…</div>
            </div>
          )}
          {/* Viewport overlay: last telemetry */}
          {telemetry && (
            <div className="absolute top-3 left-3 text-[10px] font-mono text-slate-400 glass rounded-lg px-2.5 py-1.5 pointer-events-none">
              {telemetry.well_id} · last telemetry {telemetry.timestamp ?? "—"}
            </div>
          )}
        </div>
        <div className="hidden md:flex">
          <Inspector
            selection={selection}
            wellId={selectedWellId}
            telemetry={telemetry}
            twin={twin}
            opt={selectedWellId ? (opts[selectedWellId] ?? null) : null}
            optLoading={optLoading}
            onRunOptimize={runOptimize}
            isolated={isolated}
            onIsolate={setIsolated}
            onShowAll={() => setIsolated(null)}
          />
        </div>
      </div>

      {/* Bottom bar */}
      <footer className="glass border-t border-slate-700/40 px-4 py-2 flex flex-wrap items-center gap-2 z-10">
        {presets.map((p) => (
          <button
            key={p.id}
            onClick={() => setPreset(p.id)}
            className={`text-[11px] font-mono font-bold px-3 py-1.5 rounded-lg border transition-colors ${
              preset === p.id
                ? "bg-teal-400/15 text-teal-200 border-teal-300/40"
                : "bg-slate-800/60 text-slate-400 border-slate-600/50 hover:text-slate-200"
            }`}
          >
            {p.label}
          </button>
        ))}
        <div className="flex items-center gap-1 ml-2">
          <span className="text-[10px] font-mono text-slate-500 mr-1">VIEW</span>
          {viewModes.map((v) => (
            <button
              key={v}
              onClick={() => setViewMode(v)}
              className={`text-[10px] font-mono font-bold px-2 py-1.5 rounded-lg border transition-colors ${
                viewMode === v
                  ? "bg-amber-400/15 text-amber-200 border-amber-300/40"
                  : "bg-slate-800/60 text-slate-400 border-slate-600/50 hover:text-slate-200"
              }`}
            >
              {v}
            </button>
          ))}
        </div>
        {isolated && (
          <button
            onClick={() => setIsolated(null)}
            className="text-[10px] font-mono font-bold px-2.5 py-1.5 rounded-lg bg-teal-400/15 text-teal-200 border border-teal-300/40"
          >
            ◉ SHOW ALL ({isolated})
          </button>
        )}
        <div className="flex items-center gap-3 ml-3 text-[10px] font-mono text-slate-500">
          <span><span style={{ color: "#8a6844" }}>■</span> formation</span>
          <span><span className="text-amber-300">■</span> oil / thermal</span>
          <span><span className="text-teal-300">■</span> selected</span>
          <span><span className="text-slate-400">■</span> steel</span>
          <span><span style={{ color: "#1f2733" }}>■</span> rod</span>
        </div>
        <div className="flex items-center gap-1.5 ml-3 text-[10px] font-mono" title="Data foundation: cataloged sources and stored-record provenance">
          <span className="text-slate-500">DATA</span>
          {dataSummary ? (
            <>
              <span className="text-slate-300">{dataSummary.cataloged_sources} sources</span>
              {Object.entries(dataSummary.by_provenance).map(([prov, n]) => (
                <span
                  key={prov}
                  className={`px-1.5 py-0.5 rounded border ${
                    prov === "BAGHEWALA_FIELD"
                      ? "bg-leaf/15 text-leaf border-leaf/40"
                      : prov === "SYNTHETIC_BAGHEWALA"
                        ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                        : prov === "PUBLIC_REFERENCE"
                          ? "bg-sky-500/15 text-sky-300 border-sky-500/30"
                          : "bg-slate-700/60 text-slate-300 border-slate-600/50"
                  }`}
                >
                  {prov.replace("_BAGHEWALA", "")}×{n}
                </span>
              ))}
              {Object.keys(dataSummary.by_provenance).length === 0 && (
                <span className="text-slate-600">store empty</span>
              )}
            </>
          ) : (
            <span className="text-slate-600">—</span>
          )}
        </div>
        <div className="flex-1" />
        <div className="text-[10px] font-mono text-slate-500">
          Prototype visualization · relative units · data: local prototype telemetry
        </div>
      </footer>
    </div>
  );
}
