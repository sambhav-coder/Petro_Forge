"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiBaseLabel } from "@/lib/api";
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
import { SecondaryButton } from "@/components/ui";

const FieldScene = dynamic(() => import("@/components/FieldScene"), {
  ssr: false,
});

/* 7 panel categories that appear as compact pills */
type PanelKind =
  | "WELL"
  | "CSS"
  | "SRP"
  | "ML"
  | "HISTORY"
  | "ANALYTICS"
  | "OPTIMIZATION";

const PANEL_PILLS: {
  id: PanelKind;
  label: string;
  icon: string;
  mappedTab: string;
}[] = [
  { id: "WELL", label: "WELL", icon: "◉", mappedTab: "OVERVIEW" },
  { id: "CSS", label: "CSS", icon: "♨", mappedTab: "CYCLE" },
  { id: "SRP", label: "SRP", icon: "⬣", mappedTab: "SRP" },
  { id: "ML", label: "ML", icon: "◈", mappedTab: "ML-RISK" },
  { id: "HISTORY", label: "HISTORY", icon: "⏱", mappedTab: "HISTORY" },
  { id: "ANALYTICS", label: "ANALYTICS", icon: "◬", mappedTab: "ANALYTICS" },
  { id: "OPTIMIZATION", label: "OPTIMIZATION", icon: "◎", mappedTab: "OPTIMIZATION" },
];

export default function Home() {
  /* ===== EXISTING STATE — preserved exactly ===== */
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
  const [overview, setOverview] = useState<FieldOverview | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [liveBusy, setLiveBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [lastEvent, setLastEvent] = useState<string | null>(null);

  /* ===== NEW UI STATE ===== */
  // Inspector panel expanded / collapsed
  const [inspectorOpen, setInspectorOpen] = useState<boolean>(false);
  // Single command dock (collapsed by default) + footer view popover
  const [dockOpen, setDockOpen] = useState<boolean>(false);
  const [viewPop, setViewPop] = useState<boolean>(false);
  // When the user clicks a pill, we force a specific Inspector tab
  const [forcedTab, setForcedTab] = useState<string | null>(null);
  const forcedTabRef = useRef<string | null>(null);

  const selectedRef = useRef<string | null>(null);
  selectedRef.current = selectedWellId;
  const knownWells = useRef<Set<string>>(new Set());

  /* ===== EXISTING LOGIC — preserved exactly ===== */

  const loadWell = useCallback(async (id: string) => {
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
      setWells(wl);
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
                /* per-well best-effort */
              }
            } catch {
              /* per-well best-effort */
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

  /* Server-Sent Events */
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
      /* reconnect auto */
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

  /* ===== OPEN PANEL FROM DOCK ===== */
  const handlePillClick = (p: (typeof PANEL_PILLS)[number]) => {
    forcedTabRef.current = p.mappedTab;
    setForcedTab(p.mappedTab);
    setInspectorOpen(true);
    setDockOpen(false); // menu auto-collapses; panel stays visible
  };

  const dockActiveLabel =
    inspectorOpen && forcedTab
      ? PANEL_PILLS.find((p) => p.mappedTab === forcedTab)?.label ?? "PANEL"
      : inspectorOpen
        ? "FULL"
        : null;

  /* ===== DERIVED ===== */
  const twin = selectedWellId ? twins[selectedWellId] ?? null : null;
  const telemetry = selectedWellId ? telemetries[selectedWellId] ?? null : null;
  const live = overview?.live.running ?? false;
  const unacked = alerts.filter((a) => !a.acknowledged).length;
  const presets: { id: CameraPreset; label: string }[] = [
    { id: "FIELD", label: "▦ FIELD" },
    { id: "WELL", label: "◉ WELL" },
    { id: "WELLBORE", label: "⛏ BORE" },
    { id: "RESERVOIR", label: "▼ RESV" },
    { id: "PUMP", label: "⬣ PUMP" },
  ];
  const viewModes: ViewMode[] = ["NORMAL", "CUTAWAY", "XRAY"];

  /* ============================================================
     RENDER
     ============================================================ */
  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-oil-black relative text-cream-soft">
      {/* =======================================================
         TOP BAR — very compact, logo + status + selector
         ======================================================= */}
      <header
        className="relative z-30 px-3 md:px-4 py-2 flex flex-wrap items-center gap-2 md:gap-3
          bg-gradient-to-b from-forest-deep/70 to-oil-black/60
          border-b border-natural/10
          backdrop-blur-md"
      >
        {/* Logo + brand */}
        <Link
          href="/"
          className="flex items-center gap-2.5 shrink-0"
          title="Back to PetroForge landing"
          aria-label="PetroForge home"
        >
          <Logo size={30} animated />
          <div className="leading-tight hidden sm:block">
            <div className="flex items-center gap-1.5">
              <span className="font-display font-bold tracking-[0.14em] text-[12.5px]">
                <span className="text-sand">PETRO</span>
                <span className="text-natural">FORGE</span>
              </span>
            </div>
            <div className="text-[9.5px] font-mono tracking-wide text-sand/40">
              Digital Twin Control Room
            </div>
          </div>
        </Link>

        {/* Field KPI strip — compact */}
        {overview && overview.total_wells > 0 && (
          <div className="hidden xl:flex items-center gap-3 ml-2 text-[10.5px] font-mono pl-3 border-l border-natural/10">
            <div title="Sum of measured oil rate across producing wells">
              <span className="text-sand/40">FIELD </span>
              <span className="text-amber-warm font-semibold">
                {fmt(overview.field_oil_rate_bopd)}
              </span>
              <span className="text-sand/40"> bopd</span>
            </div>
            <div title="Calibrated twin estimate">
              <span className="text-sand/40">TWIN </span>
              <span className="text-natural">{fmt(overview.field_calibrated_twin_oil_bopd)}</span>
            </div>
            <div className="flex gap-1">
              {Object.entries(overview.by_phase).map(([ph, n]) => (
                <span
                  key={ph}
                  className="px-1.5 py-0.5 rounded bg-oil-black/50 border border-natural/10 text-sand/70 text-[9.5px]"
                >
                  {ph.slice(0, 4)}×{n}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Live + synthetic flag */}
        {live && (
          <span
            className="px-2 py-0.5 rounded text-[9.5px] font-mono font-bold tracking-[0.1em] uppercase
              bg-amber-warm/12 text-amber-warm border border-amber-warm/30"
            title="SYNTHETIC DEMO LIVE STREAM — clearly labelled, never real SCADA"
          >
            ● SYNTHETIC DEMO
          </span>
        )}

        <div className="flex-1 min-w-0" />

        {/* Well selector — premium compact */}
        <div className="relative">
          <select
            value={selectedWellId ?? ""}
            onChange={(e) => e.target.value && pickWell(e.target.value)}
            className="appearance-none bg-oil-black/50 border border-natural/15 rounded-lg
              text-[10.5px] font-mono px-3 py-1.5 pr-8 text-cream-soft/95
              focus:outline-none focus:border-natural/35
              hover:border-natural/25 transition-colors cursor-pointer"
            aria-label="Select well"
          >
            {(wells?.wells ?? []).map((w) => (
              <option key={w.well_id} value={w.well_id}>
                {w.well_id} · {w.css_phase ?? w.data_status}
                {w.data_status === "PUBLIC_FIELD_RECORD" ? " · PUBLIC" : ""}
              </option>
            ))}
            {(!wells || wells.wells.length === 0) && (
              <option value="">— no wells loaded —</option>
            )}
          </select>
          <svg
            className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-sand/40"
            width="12"
            height="12"
            viewBox="0 0 12 12"
            aria-hidden="true"
          >
            <polyline points="2,4 6,8 10,4" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </div>

        {/* Live toggle */}
        <button
          onClick={toggleLive}
          disabled={liveBusy || !connected || !wells || wells.wells.length === 0}
          title="Stream synthetic field readings through the ingest pipeline"
          className={`pill-btn text-[10px] font-mono font-bold tracking-[0.1em] uppercase px-2.5 py-1.5 rounded-lg border disabled:opacity-40 ${
            live
              ? "bg-rose-500/12 text-rose-300 border-rose-500/30"
              : "bg-oil-black/40 text-sand/85 border-natural/15 hover:border-natural/30"
          }`}
        >
          {live ? "● LIVE" : "▶ LIVE"}
        </button>

        {/* Alerts */}
        <div className="relative">
          <button
            onClick={() => setAlertsOpen((o) => !o)}
            aria-label={`Alerts — ${unacked} unacknowledged`}
            className={`pill-btn text-[10px] font-mono font-bold tracking-[0.1em] uppercase px-2.5 py-1.5 rounded-lg border ${
              unacked > 0
                ? "bg-amber-warm/12 text-amber-warm border-amber-warm/30"
                : "bg-oil-black/40 text-sand/75 border-natural/15"
            }`}
          >
            ⚠ {unacked > 0 && <span className="ml-0.5">{unacked}</span>}
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

        {/* Connection status */}
        <div className="hidden md:flex items-center gap-1.5 text-[10px] font-mono">
          <span
            className={`status-dot ${connected === true ? "pulse text-natural" : "text-sand/40"}`}
            style={{ background: "currentColor" }}
          />
          <span
            className={
              connected === true
                ? "text-natural/90"
                : connected === false
                  ? "text-rose-300/80"
                  : "text-sand/45"
            }
          >
            {connected === null
              ? "CHECKING…"
              : connected
                ? "BACKEND"
                : "OFFLINE"}
          </span>
        </div>

      </header>

      {/* Error bar */}
      {error && (
        <div className="px-4 py-2 text-[11px] font-mono text-rose-300 bg-rose-500/8 border-b border-rose-500/25">
          Unable to load well data: {error} — backend at {apiBaseLabel()}. Start FastAPI first.
        </div>
      )}

      {/* =======================================================
         MAIN — 3D scene + collapsible inspector
         ======================================================= */}
      <div className="flex-1 flex min-h-0 relative">
        {/* Command dock — ONE collapsed control; expands on demand */}
        <aside
          className="shrink-0 relative z-30 flex items-center justify-center
            px-1.5 py-2 md:px-2 md:py-0 md:self-stretch
            border-r border-natural/8
            bg-gradient-to-r from-forest-deep/40 to-transparent
            max-md:fixed max-md:bottom-3 max-md:left-1/2 max-md:-translate-x-1/2
            max-md:rounded-2xl max-md:border-natural/20 max-md:bg-oil-black/85
            max-md:backdrop-blur-md max-md:shadow-glow"
          aria-label="Command dock"
        >
          <div className="relative">
            <button
              onClick={() => setDockOpen((o) => !o)}
              aria-expanded={dockOpen}
              aria-label={dockOpen ? "Close command dock" : "Open command dock"}
              title="Command dock — panels, views, system actions"
              className={`pill-btn flex flex-col items-center gap-0.5 w-12 h-12 rounded-full border
                text-[8.5px] font-mono font-bold tracking-[0.1em] uppercase transition-all duration-200
                ${dockOpen || inspectorOpen
                  ? "bg-gradient-to-br from-petroleum to-forest-deep text-cream-soft border-natural/45 shadow-glow"
                  : "bg-oil-black/50 text-sand/75 border-natural/20 hover:text-cream-soft hover:border-natural/40"}`}
            >
              <span className="text-[15px] leading-none mt-1">◉</span>
              <span>{dockActiveLabel ?? "CTRL"}</span>
            </button>

            {dockOpen && (
              <div
                className="absolute z-40 w-48 rounded-xl border border-natural/25 bg-oil-black/95 backdrop-blur-md shadow-glow p-1.5 space-y-0.5
                  left-1/2 -translate-x-1/2 bottom-full mb-3
                  md:left-full md:translate-x-0 md:bottom-auto md:mb-0 md:ml-3 md:top-1/2 md:-translate-y-1/2"
                role="menu"
                aria-label="Command options"
              >
                {PANEL_PILLS.map((p) => {
                  const active =
                    inspectorOpen &&
                    (forcedTab === p.mappedTab || (p.id === "WELL" && !forcedTab));
                  return (
                    <button
                      key={p.id}
                      role="menuitem"
                      onClick={() => {
                        if (active) {
                          setInspectorOpen(false);
                          setForcedTab(null);
                          forcedTabRef.current = null;
                          setDockOpen(false);
                        } else {
                          handlePillClick(p);
                        }
                      }}
                      className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg border text-left
                        text-[10px] font-mono font-bold tracking-[0.12em] uppercase transition-colors
                        ${active
                          ? "bg-petroleum/60 text-cream-soft border-natural/35"
                          : "text-sand/70 border-transparent hover:text-cream-soft hover:bg-natural/10"}`}
                    >
                      <span className="text-sm leading-none w-5 text-center">{p.icon}</span>
                      {p.label}
                      {active && <span className="ml-auto text-natural">●</span>}
                    </button>
                  );
                })}
                <div className="h-px bg-natural/15 my-1" />
                <button
                  role="menuitem"
                  onClick={() => {
                    setInspectorOpen((o) => !o);
                    setForcedTab(null);
                    forcedTabRef.current = null;
                    setDockOpen(false);
                  }}
                  className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left text-[10px] font-mono font-bold tracking-[0.12em] uppercase text-sand/70 hover:text-cream-soft hover:bg-natural/10"
                >
                  <span className="text-sm leading-none w-5 text-center">▤</span>
                  {inspectorOpen ? "COLLAPSE PANEL" : "FULL PANEL"}
                </button>
                <button
                  role="menuitem"
                  onClick={() => {
                    refresh();
                    setDockOpen(false);
                  }}
                  className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left text-[10px] font-mono font-bold tracking-[0.12em] uppercase text-sand/70 hover:text-cream-soft hover:bg-natural/10"
                >
                  <span className="text-sm leading-none w-5 text-center">⟳</span>
                  REFRESH DATA
                </button>
              </div>
            )}
          </div>
        </aside>

        {/* 3D scene */}
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
              <div className="absolute inset-0 flex items-center justify-center p-4">
                <div className="glass rounded-2xl p-8 text-center space-y-4 max-w-md border-gradient">
                  <div className="flex flex-col items-center">
                    <Logo size={54} animated />
                    <div className="mt-4 font-display font-semibold tracking-[0.06em] text-cream-soft">
                      No well telemetry available.
                    </div>
                  </div>
                  <p className="text-[11px] text-sand/55 leading-relaxed">
                    Load the synthetic Baghewala field (4 wells, 45 days of CSS cycles with
                    injected faults) through the real ingest pipeline, or a single BGW-DEMO
                    baseline reading.
                  </p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    <SecondaryButton
                      onClick={seedField}
                      disabled={seeding || connected === false}
                      className={
                        "!bg-gradient-to-r !from-petroleum/60 !to-crude/60 !text-cream-soft !border-natural/30"
                      }
                    >
                      {seeding ? "Loading…" : "Load synthetic field"}
                    </SecondaryButton>
                    <SecondaryButton
                      onClick={seedDemo}
                      disabled={seeding || connected === false}
                    >
                      BGW-DEMO only
                    </SecondaryButton>
                  </div>
                  <p className="text-[9.5px] font-mono text-amber-warm/70 tracking-wide">
                    Synthetic demo state — clearly labelled, never real field data.
                  </p>
                </div>
              </div>
            )
          )}

          {loading && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-[11px] font-mono text-sand/50 tracking-[0.2em] uppercase">
                <span className="status-dot pulse text-natural mr-2" style={{ background: "currentColor" }} />
                Loading well state…
              </div>
            </div>
          )}

          {/* Viewport compact overlay */}
          {telemetry && (
            <div
              className="absolute top-3 left-3 text-[10px] font-mono text-sand/75
                glass-soft rounded-lg px-3 py-2 space-y-0.5 pointer-events-none
                border border-natural/10"
            >
              <div>
                <span className="text-natural font-semibold">{telemetry.well_id}</span>
                <span className="text-sand/45"> · </span>
                <span>{telemetry.css_phase}</span>
                {telemetry.css_phase === "PRODUCTION" && telemetry.days_in_phase > 0 && (
                  <>
                    <span className="text-sand/45"> · day </span>
                    <span className="text-amber-warm">
                      {fmt(telemetry.days_in_phase, 1)}
                    </span>
                  </>
                )}
                <span className="text-sand/45"> · </span>
                <span className="text-cream-soft">
                  {fmt(telemetry.oil_rate_bopd)} bopd
                </span>
              </div>
              <div className="text-sand/40">
                last telemetry {telemetry.timestamp ?? "—"}
              </div>
              {live && lastEvent && (
                <div className="text-amber-warm/90">
                  ● streaming · sim {lastEvent.slice(0, 16).replace("T", " ")}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Inspector panel — smooth collapse / expand */}
        <div
          className="panel-expand shrink-0 min-h-0 relative
            border-l border-natural/8"
          style={{
            width: inspectorOpen ? "min(400px, 34vw)" : "0px",
            borderLeftWidth: inspectorOpen ? "1px" : "0px",
          }}
        >
          {inspectorOpen && (
            <Inspector
              selection={selection}
              wellId={selectedWellId}
              telemetry={telemetry}
              twin={twin}
              publicDetail={
                selectedWellId ? publicDetails[selectedWellId] ?? null : null
              }
              opt={selectedWellId ? opts[selectedWellId] ?? null : null}
              optLoading={optLoading}
              onRunOptimize={runOptimize}
              isolated={isolated}
              onIsolate={setIsolated}
              onShowAll={() => setIsolated(null)}
              refreshKey={refreshKey}
              alerts={alerts}
              onAckAlert={ackAlert}
              onClose={() => {
                setInspectorOpen(false);
                setForcedTab(null);
                forcedTabRef.current = null;
              }}
              forceTab={forcedTab}
              onTabConsumed={() => {
                setForcedTab(null);
                forcedTabRef.current = null;
              }}
            />
          )}
        </div>
      </div>

      {/* =======================================================
         BOTTOM BAR — compact presets + legend + provenance
         ======================================================= */}
      <footer
        className="relative z-20 px-3 md:px-4 py-2 flex flex-wrap items-center gap-2
          bg-gradient-to-t from-forest-deep/60 to-oil-black/50
          border-t border-natural/8
          backdrop-blur-md"
      >
        {/* Camera + view — single VIEW popover */}
        <div className="relative">
          <button
            onClick={() => setViewPop((o) => !o)}
            aria-expanded={viewPop}
            aria-label="Camera and view options"
            className="pill-btn text-[10px] font-mono font-bold tracking-[0.08em] uppercase
              px-2.5 py-1.5 rounded-md border transition-all duration-200
              bg-oil-black/35 text-sand/70 border-natural/15 hover:text-cream-soft hover:border-natural/30"
          >
            ▦ {preset} · {viewMode} ▾
          </button>
          {viewPop && (
            <div
              className="absolute z-40 bottom-full mb-2 left-0 w-56 rounded-xl border border-natural/25 bg-oil-black/95 backdrop-blur-md shadow-glow p-2 space-y-2"
              role="menu"
              aria-label="Camera and view"
            >
              <div>
                <div className="px-1.5 pb-1 text-[9px] font-mono tracking-[0.2em] text-sand/40 uppercase">Camera</div>
                {presets.map((p) => (
                  <button
                    key={p.id}
                    role="menuitemradio"
                    aria-checked={preset === p.id}
                    onClick={() => { setPreset(p.id); setViewPop(false); }}
                    className={`w-full text-left px-2.5 py-1.5 rounded-md text-[10px] font-mono font-bold tracking-[0.1em]
                      ${preset === p.id ? "bg-petroleum/60 text-cream-soft" : "text-sand/65 hover:text-cream-soft hover:bg-natural/10"}`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <div className="h-px bg-natural/15" />
              <div>
                <div className="px-1.5 pb-1 text-[9px] font-mono tracking-[0.2em] text-sand/40 uppercase">View mode</div>
                {viewModes.map((v) => (
                  <button
                    key={v}
                    role="menuitemradio"
                    aria-checked={viewMode === v}
                    onClick={() => { setViewMode(v); setViewPop(false); }}
                    className={`w-full text-left px-2.5 py-1.5 rounded-md text-[10px] font-mono font-bold tracking-[0.1em]
                      ${viewMode === v ? "bg-amber-warm/15 text-amber-warm" : "text-sand/65 hover:text-cream-soft hover:bg-natural/10"}`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* De-isolate */}
        {isolated && (
          <button
            onClick={() => setIsolated(null)}
            className="pill-btn text-[9.5px] font-mono font-bold tracking-[0.12em] uppercase
              px-2.5 py-1.5 rounded-md border
              bg-natural/10 text-natural border-natural/25"
          >
            ◉ SHOW ALL ({isolated})
          </button>
        )}

        {/* Color legend */}
        <div className="hidden md:flex items-center gap-3 ml-2 pl-2 border-l border-natural/10 text-[9.5px] font-mono text-sand/45">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: "#7A5234" }} />
            formation
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-sm bg-amber-warm" />
            oil/thermal
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-sm bg-natural" />
            selected
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-sm bg-sand/40" />
            steel
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: "#1a2a20" }} />
            rod
          </span>
        </div>

        {/* Provenance strip */}
        <div className="hidden lg:flex items-center gap-2 ml-2 pl-2 border-l border-natural/10 text-[9.5px] font-mono" title="Data catalog + provenance">
          <span className="text-sand/40 tracking-[0.16em] uppercase">Data</span>
          {dataSummary ? (
            <>
              <span className="text-sand/70">
                {dataSummary.cataloged_sources} src
              </span>
              {Object.entries(dataSummary.by_provenance).map(([prov, n]) => {
                let cls =
                  "bg-oil-black/40 text-sand/65 border border-natural/10";
                if (prov === "BAGHEWALA_FIELD")
                  cls = "bg-natural/10 text-natural border-natural/20";
                else if (prov === "SYNTHETIC_BAGHEWALA")
                  cls = "bg-amber-warm/10 text-amber-warm border-amber-warm/20";
                else if (prov === "PUBLIC_REFERENCE")
                  cls = "bg-sky-500/10 text-sky-300 border-sky-500/20";
                return (
                  <span
                    key={prov}
                    className={`px-1.5 py-0.5 rounded text-[9px] border ${cls}`}
                  >
                    {prov.replace("_BAGHEWALA", "")}×{n}
                  </span>
                );
              })}
              {Object.keys(dataSummary.by_provenance).length === 0 && (
                <span className="text-sand/40">store empty</span>
              )}
            </>
          ) : (
            <span className="text-sand/40">—</span>
          )}
        </div>

        <div className="flex-1" />

        {/* Prototype footer note */}
        <div className="text-[9.5px] font-mono text-sand/40 tracking-wide whitespace-nowrap">
          Prototype · relative units ·{" "}
          {live ? "synthetic live stream" : "local twin telemetry"}
        </div>
      </footer>
    </div>
  );
}
