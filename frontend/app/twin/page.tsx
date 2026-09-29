"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiBase } from "@/lib/api";
import { fmt } from "@/lib/scene";
import type {
  Alert,
  CameraPreset,
  DataSummary,
  FieldOverview,
  IsolatableKind,
  OptimizeResponse,
  PublicWellDetail,
  SceneSelection,
  StreamReading,
  TwinSnapshot,
  ViewMode,
  WellTelemetry,
  WellsResponse,
} from "@/lib/types";
import Inspector from "@/components/Inspector";
import Logo from "@/components/Logo";
import AlertsDrawer from "@/components/AlertsDrawer";

const FieldScene = dynamic(() => import("@/components/FieldScene"), { ssr: false });

export default function Home() {
  const [wells, setWells] = useState<WellsResponse | null>(null);
  const [twins, setTwins] = useState<Record<string, TwinSnapshot>>({});
  const [telemetries, setTelemetries] = useState<Record<string, WellTelemetry>>({});
  const [publicDetails, setPublicDetails] = useState<Record<string, PublicWellDetail>>({});
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
  // Block 4: real-time monitoring
  const [overview, setOverview] = useState<FieldOverview | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [liveBusy, setLiveBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [lastEvent, setLastEvent] = useState<string | null>(null);

  const selectedRef = useRef<string | null>(null);
  selectedRef.current = selectedWellId;
  const knownWells = useRef<Set<string>>(new Set());

  const loadWell = useCallback(async (id: string) => {
    // Public records have no telemetry: twin fetch 404s with
    // INSUFFICIENT_PUBLIC_TELEMETRY — tolerated, twin stays null.
    const w = await api.well(id);
    if ((w as unknown as PublicWellDetail).data_status === "PUBLIC_FIELD_RECORD") {
      setPublicDetails((p) => ({ ...p, [id]: w as unknown as PublicWellDetail }));
      setTwins((p) => {
        const c = { ...p };
        delete c[id];
        return c;
      });
      return { w: null, t: null };
    }
    const t = await api.twin(id).catch(() => null);
    setTelemetries((p) => ({ ...p, [id]: w as WellTelemetry }));
    if (t) setTwins((p) => ({ ...p, [id]: t }));
    return { w, t };
  }, []);

  const loadFieldStatus = useCallback(async () => {
    try {
      const [ov, al, wl] = await Promise.all([api.overview(), api.alerts(60), api.wells()]);
      setOverview(ov);
      setAlerts(al.alerts);
      setWells(wl); // keeps phase labels in the well picker current while live
    } catch {
      /* status strip is best-effort */
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await api.health();
      setConnected(true);
      api.dataSummary().then(setDataSummary).catch(() => setDataSummary(null));
      loadFieldStatus();
      const wl = await api.wells();
      setWells(wl);
      knownWells.current = new Set(wl.wells.map((w) => w.well_id));
      if (wl.wells.length > 0) {
        const id =
          selectedWellId && wl.wells.some((w) => w.well_id === selectedWellId)
            ? selectedWellId
            : wl.wells[0].well_id;
        setSelectedWellId(id);
        // Twin state for every known well drives per-well thermal glow.
        // Public records carry no telemetry: stored separately, twin 404 tolerated.
        await Promise.all(
          wl.wells.map(async (w) => {
            try {
              const detail = await api.well(w.well_id);
              if ((detail as unknown as PublicWellDetail).data_status === "PUBLIC_FIELD_RECORD") {
                setPublicDetails((p) => ({ ...p, [w.well_id]: detail as unknown as PublicWellDetail }));
                return;
              }
              setTelemetries((p) => ({ ...p, [w.well_id]: detail as WellTelemetry }));
              try {
                const t = await api.twin(w.well_id);
                setTwins((p) => ({ ...p, [w.well_id]: t }));
              } catch {
                /* public/no-telemetry wells simply have no twin snapshot */
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
  }, [selectedWellId, loadFieldStatus]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* Server-Sent Events: every ingest (API or live field) pushes a reading. */
  useEffect(() => {
    if (!connected) return;
    const es = new EventSource(api.streamUrl());
    let statusTimer: ReturnType<typeof setTimeout> | null = null;
    const scheduleStatus = () => {
      if (statusTimer) return;
      statusTimer = setTimeout(() => {
        statusTimer = null;
        loadFieldStatus();
      }, 800);
    };
    es.addEventListener("reading", (ev) => {
      const r = JSON.parse((ev as MessageEvent).data) as StreamReading;
      setLastEvent(r.timestamp);
      if (!knownWells.current.has(r.well_id)) {
        knownWells.current.add(r.well_id);
        api.wells().then(setWells).catch(() => undefined);
      }
      api.twin(r.well_id).then((t) => setTwins((p) => ({ ...p, [r.well_id]: t }))).catch(() => undefined);
      if (r.well_id === selectedRef.current) {
        api.well(r.well_id).then((w) => setTelemetries((p) => ({ ...p, [r.well_id]: w }))).catch(() => undefined);
        setRefreshKey((k) => k + 1);
      }
      if (r.alerts.length > 0) setAlerts((prev) => [...r.alerts.slice().reverse(), ...prev].slice(0, 60));
      scheduleStatus();
    });
    es.onerror = () => {
      /* EventSource reconnects automatically */
    };
    return () => {
      es.close();
      if (statusTimer) clearTimeout(statusTimer);
    };
  }, [connected, loadFieldStatus]);

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

  const seedField = async () => {
    setSeeding(true);
    try {
      await api.seedField(45);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Field seed failed");
    } finally {
      setSeeding(false);
    }
  };

  const toggleLive = async () => {
    setLiveBusy(true);
    try {
      const st = overview?.live.running ? await api.liveStop() : await api.liveStart(2);
      setOverview((o) => (o ? { ...o, live: st } : o));
      loadFieldStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Live toggle failed");
    } finally {
      setLiveBusy(false);
    }
  };

  const ackAlert = async (id: string) => {
    await api.ackAlert(id).catch(() => undefined);
    setAlerts((prev) => prev.map((a) => (a.alert_id === id ? { ...a, acknowledged: true } : a)));
    loadFieldStatus();
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
  const live = overview?.live.running ?? false;
  const unacked = alerts.filter((a) => !a.acknowledged).length;
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
      <header className="glass border-b border-slate-700/40 px-4 py-2.5 flex flex-wrap items-center gap-3 z-20">
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

        {/* Field KPI strip */}
        {overview && overview.total_wells > 0 && (
          <div className="hidden lg:flex items-center gap-3 ml-2 text-[11px] font-mono">
            <div title="Sum of measured oil rate across producing wells">
              <span className="text-slate-500">FIELD </span>
              <span className="text-amber-200 font-bold">{fmt(overview.field_oil_rate_bopd)}</span>
              <span className="text-slate-500"> bopd</span>
            </div>
            <div title="Calibrated digital-twin estimate for the same wells">
              <span className="text-slate-500">TWIN </span>
              <span className="text-teal-200">{fmt(overview.field_calibrated_twin_oil_bopd)}</span>
            </div>
            <div className="flex gap-1">
              {Object.entries(overview.by_phase).map(([ph, n]) => (
                <span key={ph} className="px-1.5 py-0.5 rounded bg-slate-800/70 border border-slate-700/60 text-slate-300">
                  {ph.slice(0, 4)}×{n}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="flex-1" />
        <select
          value={selectedWellId ?? ""}
          onChange={(e) => e.target.value && pickWell(e.target.value)}
          className="bg-slate-800/80 border border-slate-600/60 rounded-lg text-xs px-2 py-1.5 font-mono w-52"
        >
          {(wells?.wells ?? []).map((w) => (
            <option key={w.well_id} value={w.well_id}>
              {w.well_id} · {w.css_phase ?? w.data_status}
              {w.data_status === "PUBLIC_FIELD_RECORD" ? " (public)" : ""}
            </option>
          ))}
          {(!wells || wells.wells.length === 0) && <option value="">— no wells —</option>}
        </select>

        <button
          onClick={toggleLive}
          disabled={liveBusy || !connected || !wells || wells.wells.length === 0}
          title="Stream synthetic Baghewala field readings through the real ingest pipeline"
          className={`text-[11px] font-mono font-bold px-2.5 py-1.5 rounded-lg border disabled:opacity-40 ${
            live
              ? "bg-rose-500/15 text-rose-200 border-rose-400/50"
              : "bg-slate-700/70 text-slate-200 border-slate-600/60 hover:border-teal-300/50"
          }`}
        >
          {live ? "● LIVE" : "▶ GO LIVE"}
        </button>

        <div className="relative">
          <button
            onClick={() => setAlertsOpen((o) => !o)}
            className={`text-[11px] font-mono font-bold px-2.5 py-1.5 rounded-lg border ${
              unacked > 0
                ? "bg-amber-500/15 text-amber-200 border-amber-400/50"
                : "bg-slate-700/70 text-slate-300 border-slate-600/60"
            }`}
          >
            ⚠ ALERTS {unacked > 0 && <span className="ml-1 px-1 rounded bg-amber-400 text-slate-900">{unacked}</span>}
          </button>
          {alertsOpen && (
            <AlertsDrawer
              alerts={alerts}
              onAck={ackAlert}
              onPick={(id) => {
                pickWell(id);
                setAlertsOpen(false);
              }}
              onClose={() => setAlertsOpen(false)}
            />
          )}
        </div>

        <div className="flex items-center gap-1.5 text-[11px] font-mono">
          <span
            className={`h-2 w-2 rounded-full ${
              connected === null ? "bg-slate-500" : connected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
            }`}
          />
          <span className={connected ? "text-emerald-300" : "text-slate-400"}>
            {connected === null ? "CHECKING…" : connected ? "BACKEND" : "OFFLINE"}
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
                    Load the synthetic Baghewala field (4 wells, 45 days of CSS cycles with injected
                    faults) through the real ingest pipeline, or a single BGW-DEMO baseline reading.
                  </p>
                  <div className="flex gap-2 justify-center">
                    <button
                      onClick={seedField}
                      disabled={seeding || connected === false}
                      className="px-4 py-2 rounded-lg bg-gradient-to-r from-forest-700 to-leaf text-white text-xs font-bold disabled:opacity-40"
                    >
                      {seeding ? "Loading…" : "Load synthetic field"}
                    </button>
                    <button
                      onClick={seedDemo}
                      disabled={seeding || connected === false}
                      className="px-4 py-2 rounded-lg bg-slate-700/80 border border-slate-600/60 text-slate-200 text-xs font-bold disabled:opacity-40"
                    >
                      BGW-DEMO only
                    </button>
                  </div>
                  <p className="text-[10px] text-slate-500 font-mono">
                    Synthetic demo state — clearly labeled, never real field data.
                  </p>
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
            <div className="absolute top-3 left-3 text-[10px] font-mono text-slate-400 glass rounded-lg px-2.5 py-1.5 pointer-events-none space-y-0.5">
              <div>
                {telemetry.well_id} · {telemetry.css_phase}
                {telemetry.css_phase === "PRODUCTION" && ` day ${fmt(telemetry.days_in_phase, 1)}`} · measured{" "}
                {fmt(telemetry.oil_rate_bopd)} bopd
              </div>
              <div>last telemetry {telemetry.timestamp ?? "—"}</div>
              {live && lastEvent && <div className="text-rose-300">● streaming · sim clock {lastEvent.slice(0, 16).replace("T", " ")}</div>}
            </div>
          )}
        </div>
        <div className="hidden md:flex">
          <Inspector
            selection={selection}
            wellId={selectedWellId}
            telemetry={telemetry}
            twin={twin}
            publicDetail={selectedWellId ? (publicDetails[selectedWellId] ?? null) : null}
            opt={selectedWellId ? (opts[selectedWellId] ?? null) : null}
            optLoading={optLoading}
            onRunOptimize={runOptimize}
            isolated={isolated}
            onIsolate={setIsolated}
            onShowAll={() => setIsolated(null)}
            refreshKey={refreshKey}
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
          Prototype visualization · relative units · {live ? "live synthetic field" : "local prototype telemetry"}
        </div>
      </footer>
    </div>
  );
}
