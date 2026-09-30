"use client";

import { useState, useEffect } from "react";
import { OBJECT_META, fmt } from "@/lib/scene";
import { COMPONENTS, isIsolatable } from "@/lib/components";
import { api } from "@/lib/api";
import type {
  IsolatableKind,
  ObjectKind,
  OptimizeResponse,
  PublicWellDetail,
  ScenarioResult,
  SceneSelection,
  TwinSnapshot,
  WellTelemetry,
  HistoryResponse,
  WellCoverageSummary,
  MLStatus,
  MLForecastResult,
  MLAnomalyResult,
  MLHealthResult,
  MLFailureResult,
} from "@/lib/types";
import { Pill, Rows } from "./ui";
import { AnalyticsPanel, CyclePanel, MlPanel, SrpPanel, WhatIfPanel } from "./TwinPanels";

/* Pareto frontier section: production-vs-SOR trade-off scatter over the
 * non-dominated candidate set. Frontier points are ringed and linked;
 * selecting one reveals its full operating point. No uncertainty bands
 * are drawn — the backend does not quantify uncertainty. */
function ParetoSection({
  frontier,
  paretoCount,
  policy,
  uncertainty,
  constraints,
  selected,
  onSelect,
}: {
  frontier: ScenarioResult[];
  paretoCount: number;
  policy?: string;
  uncertainty?: string;
  constraints?: Array<{ variable: string; label: string; min: number; max: number; kind: string; note: string }>;
  selected: number | null;
  onSelect: (rank: number | null) => void;
}) {
  const plotted = frontier.filter((f) => f.steam_oil_ratio_t_per_bbl !== null);
  const prods = plotted.map((f) => f.estimated_oil_production_bopd);
  const sors = plotted.map((f) => f.steam_oil_ratio_t_per_bbl as number);
  const pMin = Math.min(...prods);
  const pMax = Math.max(...prods);
  const sMin = Math.min(...sors);
  const sMax = Math.max(...sors);
  const X = (p: number) => (pMax > pMin ? 24 + ((p - pMin) / (pMax - pMin)) * 252 : 150);
  const Y = (s: number) => (sMax > sMin ? 148 - ((s - sMin) / (sMax - sMin)) * 124 : 86);
  const ordered = [...plotted].sort((a, b) => a.estimated_oil_production_bopd - b.estimated_oil_production_bopd);
  const sel = frontier.find((f) => f.rank === selected) ?? null;
  return (
    <div className="space-y-2 rounded-lg border border-amber-500/25 bg-amber-500/5 p-2.5">
      <div className="text-[11px] font-bold text-amber-200">
        PARETO FRONTIER · {paretoCount} non-dominated candidate{paretoCount === 1 ? "" : "s"}
      </div>
      {policy && <p className="text-[10.5px] text-slate-400 leading-snug">{policy}</p>}
      {plotted.length > 0 ? (
        <svg viewBox="0 0 300 170" className="w-full h-auto" role="img" aria-label="Pareto trade-off: production versus SOR">
          <text x="8" y="14" fontSize="9" fill="rgba(148,163,184,0.8)" fontFamily="monospace">SOR ↓</text>
          <polyline
            points={ordered.map((f) => `${X(f.estimated_oil_production_bopd)},${Y(f.steam_oil_ratio_t_per_bbl as number)}`).join(" ")}
            fill="none" stroke="rgba(217,154,61,0.65)" strokeWidth="1.4" strokeDasharray="4 3"
          />
          {plotted.map((f) => {
            const isSel = f.rank === selected;
            return (
              <g key={f.rank} onClick={() => onSelect(isSel ? null : f.rank)} style={{ cursor: "pointer" }}>
                <title>{`#${f.rank}: ${f.estimated_oil_production_bopd.toFixed(1)} bopd, SOR ${f.steam_oil_ratio_t_per_bbl}`}</title>
                <circle
                  cx={X(f.estimated_oil_production_bopd)} cy={Y(f.steam_oil_ratio_t_per_bbl as number)}
                  r={isSel ? 6 : 4} fill={isSel ? "#D99A3D" : "rgba(63,166,107,0.75)"}
                  stroke={isSel ? "#E8DDC8" : "#D99A3D"} strokeWidth="1.2"
                />
              </g>
            );
          })}
          <text x="236" y="164" fontSize="9" fill="rgba(148,163,184,0.8)" fontFamily="monospace">PROD →</text>
        </svg>
      ) : (
        <p className="text-[10.5px] font-mono text-slate-500">No finite-SOR frontier points to plot.</p>
      )}
      {frontier.length !== plotted.length && (
        <p className="text-[10px] font-mono text-slate-500">
          {frontier.length - plotted.length} frontier candidate(s) have undefined SOR (zero production) and are listed only.
        </p>
      )}
      <div className="space-y-0.5">
        {frontier.map((f) => (
          <button
            key={f.rank}
            onClick={() => onSelect(f.rank === selected ? null : f.rank)}
            className={`w-full font-mono text-[11px] flex justify-between rounded px-1.5 py-0.5 text-left ${
              f.rank === selected ? "bg-amber-500/15 text-amber-200" : "text-slate-300 hover:bg-slate-700/40"
            }`}
          >
            <span>#{f.rank} {fmt(f.inputs.steam_volume_t, 0)}t/{fmt(f.inputs.soak_time_h, 0)}h/{fmt(f.inputs.spm)}spm</span>
            <span>{fmt(f.estimated_oil_production_bopd)} bopd · {f.steam_oil_ratio_t_per_bbl !== null ? `SOR ${fmt(f.steam_oil_ratio_t_per_bbl, 4)}` : "SOR —"}</span>
          </button>
        ))}
      </div>
      {sel && (
        <div className="rounded-md border border-slate-600/50 bg-slate-800/40 p-2">
          <div className="text-[10px] font-bold font-mono text-slate-200 mb-1">CANDIDATE #{sel.rank} · PARETO-OPTIMAL</div>
          <Rows
            rows={[
              ["Steam", `${fmt(sel.inputs.steam_volume_t, 0)} t @ ${fmt(sel.inputs.steam_injection_pressure_bar, 0)} bar`],
              ["Soak", `${fmt(sel.inputs.soak_time_h, 0)} h`],
              ["SPM / Stroke", `${fmt(sel.inputs.spm)} / ${fmt(sel.inputs.stroke_in, 0)} in`],
              ["VFD setpoint", `${fmt(sel.inputs.vfd_setpoint_percent, 0)} % (mapped from SPM)`],
              ["Production", `${fmt(sel.estimated_oil_production_bopd)} BOPD`],
              ["SOR", sel.steam_oil_ratio_t_per_bbl !== null ? fmt(sel.steam_oil_ratio_t_per_bbl, 4) : "undefined (zero production)"],
              ["Energy", `${fmt(sel.total_energy_kwh, 0)} kWh total`],
              ["Mean risk", sel.mean_risk !== undefined ? fmt(sel.mean_risk, 3) : "—"],
              ["Status", sel.overall_engineering_status],
            ]}
          />
        </div>
      )}
      {constraints && constraints.length > 0 && (
        <p className="text-[10px] font-mono text-slate-500 leading-snug">
          Constraints: prototype input-safety ranges ({constraints.map((c) => c.label).join(" · ")}); out-of-range
          grids rejected, never clamped. Not field-validated limits.
        </p>
      )}
      {uncertainty && (
        <p className="text-[10px] font-mono text-slate-500 leading-snug">Uncertainty: {uncertainty}</p>
      )}
    </div>
  );
}

type Tab =
  | "OVERVIEW" | "WHAT-IF" | "CYCLE" | "SRP" | "HISTORY" | "ANALYTICS"
  | "ML-RISK" | "ML-FIELD" | "OPTIMIZATION" | "PHYSICS" | "TELEMETRY";

/* Per-object sections: future components expose data here without
   rewriting the inspector. Values come from the backend only. */
const OBJECT_SECTIONS: Record<
  ObjectKind,
  (t: TwinSnapshot, w: WellTelemetry) => { heading: string; rows: [string, string][] }
> = {
  well: (t) => ({
    heading: "Well performance",
    rows: [
      ["Production", `${fmt(t.estimated_oil_production_bopd)} BOPD`],
      ["Limiting side", t.production_limiting_factor],
      ["Status", t.overall_engineering_status],
    ],
  }),
  wellhead: (t) => ({
    heading: "Pressure boundary",
    rows: [
      ["Wellhead pressure", `${fmt(t.wellhead_pressure_bar)} bar`],
      ["Reservoir pressure", `${fmt(t.reservoir_pressure_bar)} bar`],
      ["Drawdown", `${fmt(t.drawdown_bar)} bar`],
    ],
  }),
  srp: (t) => ({
    heading: "Surface pumping unit",
    rows: [
      ["SPM", fmt(t.spm)],
      ["Stroke", `${fmt(t.stroke_in, 0)} in`],
      ["Impact loading", `${t.impact_risk.risk_level} (${fmt(t.impact_risk.risk_score, 2)})`],
    ],
  }),
  casing: () => ({
    heading: "Structural liner",
    rows: [
      ["Casing diameter", "Not available"],
      ["Role", "Wellbore structure (prototype visualization)"],
      ["Twin link", "Hosts tubing + rod string"],
    ],
  }),
  tubing: (t) => ({
    heading: "Production path",
    rows: [
      ["Reservoir inflow", `${fmt(t.estimated_reservoir_inflow_bopd)} BOPD`],
      ["Mobility factor", fmt(t.mobility_factor, 3)],
      ["Tubing diameter", "Not available"],
    ],
  }),
  rod: (t) => ({
    heading: "Mechanical state",
    rows: [
      ["SPM", fmt(t.spm)],
      ["Rod float", `${t.rod_float_risk.risk_level} (${fmt(t.rod_float_risk.risk_score, 2)})`],
    ],
  }),
  pump: (t) => ({
    heading: "Pump performance",
    rows: [
      ["Actual capacity", `${fmt(t.pump_capacity_bopd)} BOPD`],
      ["Theoretical", `${fmt(t.pump_theoretical_capacity_bopd)} BOPD`],
      ["Fillage / efficiency", `${t.pump_fillage} / ${t.pump_efficiency} (prototype)`],
      ["Pump depth", "Not available"],
    ],
  }),
  reservoir: (t) => ({
    heading: "Thermal / pressure state",
    rows: [
      ["Temperature", `${fmt(t.estimated_temperature_c)} °C`],
      ["Reservoir pressure", `${fmt(t.reservoir_pressure_bar)} bar (backend)`],
      ["Viscosity", `${fmt(t.estimated_viscosity_cp)} cP`],
      ["Mobility", fmt(t.mobility_factor, 3)],
      ["Heating intensity", fmt(t.heating_intensity, 2)],
    ],
  }),
  thermal: (t) => ({
    heading: "Scalar thermal mapping",
    rows: [
      ["Estimated temp", `${fmt(t.estimated_temperature_c)} °C`],
      ["Baseline temp", `${fmt(t.baseline_reservoir_temperature_c)} °C`],
      ["Spatial field", "Not available (visual mapping only)"],
    ],
  }),
  formation: () => ({
    heading: "Structural context",
    rows: [
      ["Type", "Cap / base rock layer"],
      ["Backend metrics", "Not available"],
      ["Role", "Geological context for the oil zone"],
    ],
  }),
};

export default function Inspector({
  selection,
  wellId,
  telemetry,
  twin,
  publicDetail,
  opt,
  optLoading,
  onRunOptimize,
  isolated,
  onIsolate,
  onShowAll,
  refreshKey,
  onClose,
  forceTab,
  onTabConsumed,
}: {
  selection: SceneSelection | null;
  wellId: string | null;
  telemetry: WellTelemetry | null;
  twin: TwinSnapshot | null;
  publicDetail: PublicWellDetail | null;
  opt: OptimizeResponse | null;
  optLoading: boolean;
  onRunOptimize: () => void;
  isolated: IsolatableKind | null;
  onIsolate: (kind: IsolatableKind) => void;
  onShowAll: () => void;
  refreshKey: number;
  onClose?: () => void;
  forceTab?: string | null;
  onTabConsumed?: () => void;
}) {
  const [tab, setTab] = useState<Tab>("OVERVIEW");
  const [paretoSel, setParetoSel] = useState<number | null>(null);
  const [historyData, setHistoryData] = useState<HistoryResponse | null>(null);
  const [coverageData, setCoverageData] = useState<WellCoverageSummary | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [mlStatus, setMlStatus] = useState<MLStatus | null>(null);
  const [mlForecast, setMlForecast] = useState<MLForecastResult | null>(null);
  const [mlAnomaly, setMlAnomaly] = useState<MLAnomalyResult | null>(null);
  const [mlHealth, setMlHealth] = useState<MLHealthResult | null>(null);
  const [mlFailure, setMlFailure] = useState<MLFailureResult | null>(null);
  const [mlLoading, setMlLoading] = useState(false);
  const tabs: Tab[] = [
    "OVERVIEW", "WHAT-IF", "CYCLE", "SRP", "HISTORY", "ANALYTICS",
    "ML-RISK", "ML-FIELD", "OPTIMIZATION", "PHYSICS", "TELEMETRY",
  ];
  /* Compact segmented navigation: primary state row + systems row. */
  const primaryTabs: Tab[] = ["OVERVIEW", "TELEMETRY", "HISTORY", "PHYSICS", "ML-RISK"];
  const systemTabs: Tab[] = ["CYCLE", "SRP", "WHAT-IF", "ANALYTICS", "OPTIMIZATION", "ML-FIELD"];
  const allTabs: Tab[] = [...primaryTabs, ...systemTabs];

  // Command-dock forced tab: jump once, then release back to manual control.
  useEffect(() => {
    if (forceTab && (allTabs as string[]).includes(forceTab)) {
      setTab(forceTab as Tab);
      onTabConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forceTab]);

  // Load historical data when HISTORY tab is selected
  useEffect(() => {
    if (tab === "HISTORY" && wellId) {
      setHistoryLoading(true);
      Promise.all([
        api.history({ well_id: wellId, include_derived: false, include_synthetic: false, include_live: true, limit: 100 }),
        api.historyCoverage(wellId),
      ])
        .then(([history, coverage]) => {
          setHistoryData(history);
          setCoverageData(coverage);
        })
        .catch(() => {
          setHistoryData(null);
          setCoverageData(null);
        })
        .finally(() => {
          setHistoryLoading(false);
        });
    }
  }, [tab, wellId]);

  // Load ML data when ML tab is selected
  useEffect(() => {
    if (tab === "ML-FIELD") {
      setMlLoading(true);
      Promise.all([
        api.mlStatus(),
        wellId ? api.mlForecast({ well_id: wellId, horizon_days: 30 }) : Promise.resolve(null),
        wellId && telemetry ? api.mlAnomaly({ variable: "spm", value: telemetry.spm, well_id: wellId }) : Promise.resolve(null),
        wellId ? api.mlHealth({ well_id: wellId, features: { spm: telemetry?.spm, stroke: telemetry?.stroke_in } }) : Promise.resolve(null),
        wellId ? api.mlFailure({ well_id: wellId }) : Promise.resolve(null),
      ])
        .then(([status, forecast, anomaly, health, failure]) => {
          setMlStatus(status);
          setMlForecast(forecast);
          setMlAnomaly(anomaly);
          setMlHealth(health);
          setMlFailure(failure);
        })
        .catch(() => {
          setMlStatus(null);
          setMlForecast(null);
          setMlAnomaly(null);
          setMlHealth(null);
          setMlFailure(null);
        })
        .finally(() => {
          setMlLoading(false);
        });
    }
  }, [tab, wellId, telemetry]);

  return (
    <aside className="glass rounded-none border-l border-slate-700/40 w-[400px] shrink-0 flex flex-col min-h-0 relative">
      {onClose && (
        <button
          onClick={onClose}
          aria-label="Close panel"
          className="absolute top-2 right-2 z-10 px-2 py-1 rounded-md text-[11px] font-mono text-slate-500 hover:text-cream-soft hover:bg-slate-700/50 border border-transparent hover:border-slate-600/60"
        >
          ✕
        </button>
      )}
      <div className="px-4 pt-4 pb-2">
        {!selection || !wellId ? (
          <div>
            <div className="text-sm font-bold tracking-wide text-slate-200">SELECT AN OBJECT</div>
            <p className="text-xs text-slate-400 mt-1">
              Click a wellhead, SRP unit, tubing, rod string, pump, or reservoir volume in
              the 3D scene to inspect its live twin state.
            </p>
          </div>
        ) : (
          <div>
            <div className="text-[11px] font-mono text-teal-300">
              {OBJECT_META[selection.kind].title.toUpperCase()} · {selection.wellId}
            </div>
            <div className="text-sm font-bold text-slate-100">
              {selection.kind === "well" ? `${wellId} — HEAVY OIL WELL` : selection.label}
            </div>
            <div className="text-[11px] text-slate-400">{OBJECT_META[selection.kind].hint}</div>
            <div className="text-[11px] text-slate-500 font-mono mt-0.5">
              Depth {COMPONENTS[selection.kind].depthPct[0]}–{COMPONENTS[selection.kind].depthPct[1]}% (prototype-relative)
            </div>
            <div className="flex gap-2 mt-2">
              {isIsolatable(selection.kind) ? (
                isolated === selection.kind ? (
                  <button
                    onClick={onShowAll}
                    className="text-[10px] font-mono font-bold px-2.5 py-1.5 rounded-lg bg-teal-400/15 text-teal-200 border border-teal-300/40"
                  >
                    ◉ SHOW ALL
                  </button>
                ) : (
                  <button
                    onClick={() => onIsolate(selection.kind as IsolatableKind)}
                    className="text-[10px] font-mono font-bold px-2.5 py-1.5 rounded-lg bg-slate-700/70 text-slate-200 border border-slate-600/60 hover:border-teal-300/50"
                  >
                    ◎ ISOLATE {COMPONENTS[selection.kind].displayName.toUpperCase()}
                  </button>
                )
              ) : (
                <span className="text-[10px] font-mono text-slate-500">Aggregate / surface entity — isolation N/A</span>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="border-b border-slate-700/40" role="tablist" aria-label="Inspector sections">
        <div className="flex gap-1 px-3 overflow-x-auto scroll-thin" role="group" aria-label="Primary state">
          {primaryTabs.map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`px-2.5 py-2 text-[10px] font-mono font-bold whitespace-nowrap border-b-2 transition-colors ${
                tab === t
                  ? "border-teal-300 text-teal-200"
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="flex gap-1 px-3 overflow-x-auto scroll-thin bg-slate-900/40" role="group" aria-label="Systems">
          {systemTabs.map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`px-2 py-1.5 text-[9px] font-mono font-bold whitespace-nowrap border-b-2 transition-colors ${
                tab === t
                  ? "border-amber-warm/70 text-amber-200"
                  : "border-transparent text-slate-600 hover:text-slate-300"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scroll-thin p-4 space-y-4 min-h-0">
        {publicDetail && !twin ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Pill level="MODERATE" />
              <span className="text-[11px] font-mono text-slate-300">PUBLIC FIELD RECORD</span>
            </div>
            <p className="text-[11px] text-slate-400">
              Verified historical record (BAGHEWALA_FIELD) — not live telemetry.
              No twin snapshot: insufficient public telemetry.
            </p>
            <Rows
              rows={[
                ["Status", `${publicDetail.status ?? "—"}${publicDetail.status_as_of ? ` (as of ${publicDetail.status_as_of})` : ""}`],
                ["Lift", publicDetail.lift_method ?? "—"],
                ["CSS status", publicDetail.css_status ?? "—"],
                ["CSS cycles", publicDetail.css_cycle_count != null ? String(publicDetail.css_cycle_count) : "—"],
                ["CSS events", String(publicDetail.css.length)],
                ["Production recs", String(publicDetail.production.length)],
                ["Confidence", publicDetail.confidence ?? "—"],
                ["Source", publicDetail.source_id ?? "—"],
              ]}
            />
            {(publicDetail as unknown as { status_as_of_kind?: string; temporal_note?: string }).status_as_of_kind && (
              <p className="text-[11px] font-mono text-amber-200/90">
                Date semantics: {(publicDetail as unknown as { status_as_of_kind: string }).status_as_of_kind} — not a live reading.
              </p>
            )}
            {(publicDetail as unknown as { temporal_note?: string }).temporal_note && (
              <p className="text-[11px] text-slate-500">
                {(publicDetail as unknown as { temporal_note: string }).temporal_note}
              </p>
            )}
            {publicDetail.production.map((p, i) => {
              const rec = p as unknown as Record<string, string | number | null>;
              const isDerived = rec["value_kind"] === "midpoint_of_reported_range";
              return (
                <div key={i} className="rounded-lg border border-slate-700/50 bg-slate-800/40 px-2.5 py-2 space-y-1">
                  <div className="text-[11px] font-mono text-slate-200">
                    {isDerived
                      ? `Reported: ${rec["reported_min_bopd"]}–${rec["reported_max_bopd"]} BOPD`
                      : `Value: ${rec["value"]} ${rec["unit"] ?? ""}`}
                  </div>
                  {isDerived && (
                    <div className="text-[11px] font-mono text-amber-200">
                      Derived midpoint: {rec["derived_midpoint_bopd"]} BOPD (DERIVED — not a raw measurement)
                    </div>
                  )}
                  {typeof rec["derivation"] === "string" && (
                    <div className="text-[10px] font-mono text-slate-500">{rec["derivation"]}</div>
                  )}
                  {typeof rec["event_period"] === "string" && (
                    <div className="text-[10px] font-mono text-slate-500">
                      Period: {rec["event_period"]} ({typeof rec["date_precision"] === "string" ? rec["date_precision"] : ""} precision; exact date {rec["exact_date_available"] ? "available" : "not established"})
                    </div>
                  )}
                </div>
              );
            })}
            {publicDetail.css.map((c, i) => {
              const rec = c as unknown as Record<string, string | number | null | boolean>;
              return (
                <div key={i} className="rounded-lg border border-slate-700/50 bg-slate-800/40 px-2.5 py-2 space-y-1">
                  <div className="text-[11px] font-mono text-slate-200">
                    {typeof rec["cycle_id"] === "string" ? rec["cycle_id"] : "CSS event"}
                    {typeof rec["event_period"] === "string" ? ` · ${rec["event_period"]}` : ""}
                  </div>
                  {typeof rec["source_publication_date"] === "string" && (
                    <div className="text-[10px] font-mono text-slate-500">
                      Source published {rec["source_publication_date"]} — publication date is not the event date.
                    </div>
                  )}
                  {typeof rec["injection_end_note"] === "string" && (
                    <div className="text-[10px] font-mono text-slate-500">{rec["injection_end_note"]}</div>
                  )}
                  {typeof rec["reported_injection_days"] === "number" && (
                    <div className="text-[10px] font-mono text-slate-500">
                      Reported ~{rec["reported_injection_days"]} days of injection; exact start/end not established — not continuous telemetry.
                    </div>
                  )}
                </div>
              );
            })}
            {publicDetail.notes && (
              <p className="text-[11px] text-slate-400">{publicDetail.notes}</p>
            )}
          </div>
        ) : !twin || !telemetry ? (
          <p className="text-xs text-slate-500 font-mono">
            {wellId ? "Loading twin state…" : "No well selected."}
          </p>
        ) : (
          <>
            {tab === "OVERVIEW" && (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400 font-mono">STATUS</span>
                  <Pill level={twin.overall_engineering_status} />
                  <span className="text-xs text-slate-400 font-mono ml-2">CSS</span>
                  <span className="text-xs font-mono text-amber-200">
                    {twin.css_phase}
                    {twin.css_phase === "PRODUCTION" && twin.days_in_phase > 0 && ` · day ${fmt(twin.days_in_phase, 1)}`}
                  </span>
                </div>
                {(twin.css_phase === "INJECTION" || twin.css_phase === "SOAK") && (
                  <p className="text-[10px] text-amber-200/80 font-mono">
                    Well shut in for {twin.css_phase.toLowerCase()}: figures below are the twin&apos;s production capability.
                  </p>
                )}
                {selection && selection.kind !== "well" && (
                  <section>
                    <h4 className="text-[11px] font-bold text-teal-200 mb-1">
                      {OBJECT_SECTIONS[selection.kind](twin, telemetry).heading.toUpperCase()}
                    </h4>
                    <Rows rows={OBJECT_SECTIONS[selection.kind](twin, telemetry).rows} />
                  </section>
                )}
                <section>
                  <h4 className="text-[11px] font-bold text-slate-300 mb-1">OPERATING STATE</h4>
                  <Rows
                    rows={[
                      ["Steam", `${fmt(telemetry.steam_volume_t, 0)} t`],
                      ["Injection pressure", `${fmt(telemetry.steam_injection_pressure_bar, 0)} bar`],
                      ["Soak", `${fmt(telemetry.soak_time_h, 0)} h`],
                      ["SPM", fmt(telemetry.spm)],
                      ["Stroke", `${fmt(telemetry.stroke_in, 0)} in`],
                      ["VFD", `${fmt(telemetry.vfd_percent)} % (twin setpoint ${fmt(twin.vfd_setpoint_percent, 0)} %)`],
                    ]}
                  />
                </section>
                <section>
                  <h4 className="text-[11px] font-bold text-slate-300 mb-1">TWIN SNAPSHOT</h4>
                  <Rows
                    rows={[
                      ["Measured oil", `${fmt(telemetry.oil_rate_bopd)} BOPD`],
                      ["Twin oil (uncalibrated)", `${fmt(twin.estimated_oil_production_bopd)} BOPD`],
                      ["Liquid / water cut", `${fmt(twin.estimated_liquid_production_bpd)} bpd · ${fmt(twin.water_cut_percent, 0)} %`],
                      ["Pump fillage", fmt(twin.estimated_pump_fillage, 2)],
                      ["SOR (prototype t/bbl)", fmt(twin.steam_oil_ratio_t_per_bbl, 4)],
                      ["Energy", `${fmt(twin.total_energy_kwh, 0)} kWh`],
                    ]}
                  />
                </section>
                <section>
                  <h4 className="text-[11px] font-bold text-slate-300 mb-1">RISK</h4>
                  <div className="space-y-1.5 text-xs">
                    {(
                      [
                        ["Rod Floating", twin.rod_float_risk],
                        ["Impact Loading", twin.impact_risk],
                        ["Pump Unsetting", twin.pump_unsetting_risk],
                      ] as const
                    ).map(([name, r]) => (
                      <div key={name} className="flex items-center justify-between gap-2">
                        <span className="text-slate-400 font-mono">{name}</span>
                        <Pill level={r.risk_level} />
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {tab === "TELEMETRY" && (
              <Rows
                rows={[
                  ["Oil rate", `${fmt(telemetry.oil_rate_bopd)} BOPD`],
                  ["Reservoir temperature", `${fmt(telemetry.reservoir_temperature_c)} °C`],
                  ["Viscosity (twin)", `${fmt(twin.estimated_viscosity_cp)} cP`],
                  ["Reservoir pressure", `${fmt(telemetry.reservoir_pressure_bar)} bar`],
                  ["Wellhead pressure", `${fmt(telemetry.wellhead_pressure_bar)} bar`],
                  ["Steam volume", `${fmt(telemetry.steam_volume_t, 0)} t`],
                  ["Steam inj. pressure", `${fmt(telemetry.steam_injection_pressure_bar, 0)} bar`],
                  ["Soak time", `${fmt(telemetry.soak_time_h, 0)} h`],
                  ["SPM", fmt(telemetry.spm)],
                  ["Stroke", `${fmt(telemetry.stroke_in, 0)} in`],
                  ["VFD", `${fmt(telemetry.vfd_percent)} %`],
                  ["Water cut", `${fmt(telemetry.water_cut_percent)} %`],
                  ["API gravity", `${fmt(telemetry.api_gravity)}°`],
                  ["Days in phase", fmt(telemetry.days_in_phase, 1)],
                  ["Timestamp", telemetry.timestamp ?? "—"],
                ]}
              />
            )}

            {tab === "PHYSICS" && (
              <div className="space-y-3">
                <Rows
                  rows={[
                    ["Temperature", `${fmt(twin.estimated_temperature_c)} °C (base ${fmt(twin.baseline_reservoir_temperature_c)})`],
                    ["Viscosity", `${fmt(twin.estimated_viscosity_cp)} cP`],
                    ["Mobility", fmt(twin.mobility_factor, 3)],
                    ["Inflow", `${fmt(twin.estimated_reservoir_inflow_bopd)} BOPD`],
                    ["Pump capacity", `${fmt(twin.pump_capacity_bopd)} BPD`],
                    ["Liquid rate", `${fmt(twin.estimated_liquid_production_bpd)} BPD`],
                    ["Oil (after water cut)", `${fmt(twin.estimated_oil_production_bopd)} BOPD`],
                    ["Pump fillage (est.)", fmt(twin.estimated_pump_fillage, 2)],
                    ["Limiting", twin.production_limiting_factor],
                    ["SOR", `${fmt(twin.steam_oil_ratio_t_per_bbl, 4)} t/bbl (${twin.sor_status})`],
                    ["Energy", `${fmt(twin.total_energy_kwh, 0)} kWh`],
                  ]}
                />
                <p className="text-[11px] text-slate-400">{twin.recommendation}</p>
                <div className="text-[11px] text-slate-500 space-y-1">
                  {Object.entries(twin.explanations).map(([k, v]) => (
                    <p key={k}>
                      <strong className="text-slate-300">{k}:</strong> {v}
                    </p>
                  ))}
                </div>
              </div>
            )}

            {tab === "WHAT-IF" && wellId && <WhatIfPanel wellId={wellId} twin={twin} />}
            {tab === "CYCLE" && wellId && <CyclePanel wellId={wellId} refreshKey={refreshKey} />}
            {tab === "SRP" && wellId && <SrpPanel wellId={wellId} refreshKey={refreshKey} />}
            {tab === "ANALYTICS" && wellId && <AnalyticsPanel wellId={wellId} refreshKey={refreshKey} />}
            {tab === "ML-RISK" && wellId && <MlPanel wellId={wellId} refreshKey={refreshKey} />}
            {tab === "HISTORY" && (
              <div className="space-y-3">
                {historyLoading ? (
                  <p className="text-xs text-slate-500 font-mono">Loading historical data…</p>
                ) : coverageData ? (
                  <>
                    <div className="flex items-center gap-2">
                      <Pill level={coverageData.time_series_ready ? "LOW" : "MODERATE"} />
                      <span className="text-[11px] font-mono text-slate-300">
                        {coverageData.time_series_ready ? "TIME-SERIES READY" : "INSUFFICIENT COVERAGE"}
                      </span>
                    </div>
                    <section>
                      <h4 className="text-[11px] font-bold text-slate-300 mb-1">COVERAGE SUMMARY</h4>
                      <Rows
                        rows={[
                          ["Observations", String(coverageData.coverage.observation_count)],
                          ["Temporal coverage", coverageData.coverage.temporal_coverage],
                          ["Has gaps", coverageData.coverage.has_gaps ? "Yes" : "No"],
                          ["Measured", String(coverageData.coverage.measured_count)],
                          ["Derived", String(coverageData.coverage.derived_count)],
                          ["Synthetic", String(coverageData.coverage.synthetic_count)],
                          ["Time-series safe", String(coverageData.coverage.time_series_safe_count)],
                          ["ML-safe", String(coverageData.coverage.ml_safe_count)],
                        ]}
                      />
                    </section>
                    {coverageData.coverage.provenance_classes.length > 0 && (
                      <section>
                        <h4 className="text-[11px] font-bold text-slate-300 mb-1">PROVENANCE</h4>
                        <div className="flex flex-wrap gap-1">
                          {coverageData.coverage.provenance_classes.map((prov) => (
                            <span
                              key={prov}
                              className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                                prov === "BAGHEWALA_FIELD"
                                  ? "bg-leaf/15 text-leaf border-leaf/40"
                                  : prov === "DERIVED"
                                    ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                                    : prov === "SYNTHETIC_BAGHEWALA"
                                      ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                                      : prov === "LIVE_TELEMETRY"
                                        ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                        : "bg-slate-700/60 text-slate-300 border-slate-600/50"
                              }`}
                            >
                              {prov.replace("_BAGHEWALA", "")}
                            </span>
                          ))}
                        </div>
                      </section>
                    )}
                    {Object.keys(coverageData.variables).length > 0 && (
                      <section>
                        <h4 className="text-[11px] font-bold text-slate-300 mb-1">VARIABLES</h4>
                        <div className="text-[10px] font-mono text-slate-400 space-y-0.5">
                          {Object.entries(coverageData.variables).map(([varName, count]) => (
                            <div key={varName}>
                              {varName}: {count} observation{count !== 1 ? "s" : ""}
                            </div>
                          ))}
                        </div>
                      </section>
                    )}
                    {historyData && historyData.observations.length > 0 && (
                      <section>
                        <h4 className="text-[11px] font-bold text-slate-300 mb-1">RECENT OBSERVATIONS</h4>
                        <div className="space-y-2 max-h-48 overflow-y-auto scroll-thin">
                          {historyData.observations.slice(0, 10).map((obs) => (
                            <div key={obs.record_id} className="rounded-lg border border-slate-700/50 bg-slate-800/40 px-2.5 py-2 space-y-1">
                              <div className="flex justify-between items-start gap-2">
                                <div className="text-[11px] font-mono text-slate-200">
                                  {obs.variable}: {obs.value !== null ? `${obs.value} ${obs.unit}` : obs.value_str || "—"}
                                </div>
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[9px] font-mono border ${
                                    obs.provenance === "BAGHEWALA_FIELD"
                                      ? "bg-leaf/15 text-leaf border-leaf/40"
                                      : obs.provenance === "DERIVED"
                                        ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                                        : obs.provenance === "SYNTHETIC_BAGHEWALA"
                                          ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                                          : obs.data_status === "LIVE_TELEMETRY"
                                            ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                            : "bg-slate-700/60 text-slate-300 border-slate-600/50"
                                  }`}
                                >
                                  {obs.provenance.replace("_BAGHEWALA", "")}
                                </span>
                              </div>
                              <div className="text-[10px] font-mono text-slate-500">
                                {obs.timestamp_start} ({obs.timestamp_precision})
                              </div>
                              {obs.value_kind === "reported_range" && obs.reported_min !== null && obs.reported_max !== null && (
                                <div className="text-[10px] font-mono text-amber-200">
                                  Reported range: {obs.reported_min}–{obs.reported_max} {obs.unit}
                                </div>
                              )}
                              {obs.value_kind === "derived_midpoint" && (
                                <div className="text-[10px] font-mono text-amber-200">
                                  Derived midpoint — not a raw measurement
                                </div>
                              )}
                              {obs.notes && (
                                <div className="text-[10px] font-mono text-slate-500">{obs.notes}</div>
                              )}
                            </div>
                          ))}
                        </div>
                        {historyData.observations.length > 10 && (
                          <p className="text-[10px] font-mono text-slate-500">
                            Showing 10 of {historyData.count} observations
                          </p>
                        )}
                      </section>
                    )}
                    {!coverageData.time_series_ready && (
                      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                        <p className="text-[11px] font-mono text-amber-200">
                          Insufficient time-series coverage for trend analysis or charting.
                          {coverageData.coverage.observation_count < 2
                            ? ` Only ${coverageData.coverage.observation_count} observation${coverageData.coverage.observation_count !== 1 ? "s" : ""} available.`
                            : " Temporal precision or observation count insufficient."}
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-xs text-slate-500 font-mono">
                    No historical data available for this well.
                  </p>
                )}
              </div>
            )}

            {tab === "ML-FIELD" && (
              <div className="space-y-3">
                {mlLoading ? (
                  <p className="text-xs text-slate-500 font-mono">Loading ML intelligence…</p>
                ) : mlStatus ? (
                  <>
                    <div className="flex items-center gap-2">
                      <Pill level={mlStatus.status === "OPERATIONAL" ? "LOW" : "MODERATE"} />
                      <span className="text-[11px] font-mono text-slate-300">
                        {mlStatus.status} — {mlStatus.datasets} datasets
                      </span>
                    </div>
                    
                    <section>
                      <h4 className="text-[11px] font-bold text-slate-300 mb-1">PRODUCTION FORECAST</h4>
                      {mlForecast ? (
                        <div className="space-y-2">
                          {mlForecast.insufficient_data ? (
                            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                              <p className="text-[11px] font-mono text-amber-200">
                                Insufficient training data
                              </p>
                              <p className="text-[10px] font-mono text-slate-500 mt-1">
                                {mlForecast.insufficient_reason}
                              </p>
                            </div>
                          ) : (
                            <>
                              <Rows
                                rows={[
                                  ["Model", `${mlForecast.model_id} v${mlForecast.model_version}`],
                                  ["Data quality", mlForecast.data_quality],
                                  ["Horizon", `${mlForecast.forecast_horizon_days} days`],
                                ]}
                              />
                              {mlForecast.limitations.length > 0 && (
                                <div className="text-[10px] font-mono text-slate-500 space-y-1">
                                  {mlForecast.limitations.map((lim, i) => (
                                    <p key={i}>• {lim}</p>
                                  ))}
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500 font-mono">No forecast data available</p>
                      )}
                    </section>

                    <section>
                      <h4 className="text-[11px] font-bold text-slate-300 mb-1">ANOMALY DETECTION</h4>
                      {mlAnomaly ? (
                        <div className="space-y-2">
                          {mlAnomaly.insufficient_data ? (
                            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                              <p className="text-[11px] font-mono text-amber-200">
                                Insufficient historical context
                              </p>
                              <p className="text-[10px] font-mono text-slate-500 mt-1">
                                {mlAnomaly.insufficient_reason}
                              </p>
                            </div>
                          ) : (
                            <>
                              <div className="flex items-center gap-2">
                                <Pill level={mlAnomaly.status === "NORMAL" ? "LOW" : mlAnomaly.status === "WARNING" ? "MODERATE" : "HIGH"} />
                                <span className="text-[11px] font-mono text-slate-300">
                                  {mlAnomaly.status}
                                </span>
                              </div>
                              <Rows
                                rows={[
                                  ["Variable", mlAnomaly.variable],
                                  ["Value", fmt(mlAnomaly.observed_value)],
                                  ["Score", fmt(mlAnomaly.anomaly_score, 2)],
                                  ["Method", mlAnomaly.method],
                                ]}
                              />
                              <p className="text-[10px] font-mono text-slate-400">{mlAnomaly.explanation}</p>
                            </>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500 font-mono">No anomaly data available</p>
                      )}
                    </section>

                    <section>
                      <h4 className="text-[11px] font-bold text-slate-300 mb-1">SRP/PUMP HEALTH</h4>
                      {mlHealth ? (
                        <div className="space-y-2">
                          {mlHealth.insufficient_data ? (
                            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                              <p className="text-[11px] font-mono text-amber-200">
                                Insufficient SRP operational data
                              </p>
                              <p className="text-[10px] font-mono text-slate-500 mt-1">
                                {mlHealth.insufficient_reason}
                              </p>
                            </div>
                          ) : (
                            <>
                              <div className="flex items-center gap-2">
                                <Pill level={mlHealth.health_status === "HEALTHY" ? "LOW" : mlHealth.health_status === "DEGRADED" ? "MODERATE" : "HIGH"} />
                                <span className="text-[11px] font-mono text-slate-300">
                                  {mlHealth.health_status} ({fmt(mlHealth.health_score, 2)})
                                </span>
                              </div>
                              <Rows
                                rows={[
                                  ["Model", `${mlHealth.model_id} v${mlHealth.model_version}`],
                                  ["Data quality", mlHealth.data_quality],
                                  ["SPM status", mlHealth.spm_status || "—"],
                                  ["Stroke status", mlHealth.stroke_status || "—"],
                                ]}
                              />
                              {mlHealth.limitations.length > 0 && (
                                <div className="text-[10px] font-mono text-slate-500 space-y-1">
                                  {mlHealth.limitations.map((lim, i) => (
                                    <p key={i}>• {lim}</p>
                                  ))}
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500 font-mono">No health data available</p>
                      )}
                    </section>

                    <section>
                      <h4 className="text-[11px] font-bold text-slate-300 mb-1">FAILURE RISK</h4>
                      {mlFailure ? (
                        <div className="space-y-2">
                          {mlFailure.insufficient_data ? (
                            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                              <p className="text-[11px] font-mono text-amber-200">
                                Insufficient labeled failure data
                              </p>
                              <p className="text-[10px] font-mono text-slate-500 mt-1">
                                {mlFailure.insufficient_reason}
                              </p>
                            </div>
                          ) : (
                            <>
                              <Rows
                                rows={[
                                  ["Model", `${mlFailure.model_id} v${mlFailure.model_version}`],
                                  ["Data quality", mlFailure.data_quality],
                                  ["Risk level", mlFailure.risk_level || "—"],
                                  ["Probability", mlFailure.failure_probability !== null ? fmt(mlFailure.failure_probability * 100, 1) + "%" : "—"],
                                ]}
                              />
                              {mlFailure.limitations.length > 0 && (
                                <div className="text-[10px] font-mono text-slate-500 space-y-1">
                                  {mlFailure.limitations.map((lim, i) => (
                                    <p key={i}>• {lim}</p>
                                  ))}
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500 font-mono">No failure risk data available</p>
                      )}
                    </section>

                    <div className="text-[10px] font-mono text-slate-500 space-y-1">
                      <p>ML intelligence uses only ML-safe historical observations.</p>
                      <p>See HISTORY tab for data readiness and provenance.</p>
                      <p>Models unavailable due to insufficient training data return explicit unavailable states.</p>
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-slate-500 font-mono">ML system unavailable</p>
                )}
              </div>
            )}

            {tab === "OPTIMIZATION" && (
              <div className="space-y-3">
                <button
                  onClick={onRunOptimize}
                  disabled={optLoading}
                  className="px-3 py-2 rounded-lg bg-gradient-to-r from-forest-700 to-leaf text-white text-xs font-bold disabled:opacity-40"
                >
                  {optLoading ? "Evaluating 243 scenarios…" : "RUN OPTIMIZATION"}
                </button>
                {!opt && !optLoading && (
                  <p className="text-xs text-slate-500 font-mono">
                    Runs the real backend optimizer (243-scenario grid). Prototype weights.
                  </p>
                )}
                {opt && (
                  <div className="space-y-2 text-xs">
                    <Rows
                      rows={[
                        ["Recommended production", `${fmt(opt.recommended.estimated_oil_production_bopd)} BOPD`],
                        ["Change vs current", `${opt.delta.production_delta_bopd >= 0 ? "+" : ""}${fmt(opt.delta.production_delta_bopd)} BOPD`],
                        [
                          "Settings",
                          `${fmt(opt.recommended.inputs.steam_volume_t, 0)} t · ${fmt(opt.recommended.inputs.soak_time_h, 0)} h · ${fmt(opt.recommended.inputs.spm)} SPM`,
                        ],
                        ["VFD setpoint", `${fmt(opt.recommended.inputs.vfd_setpoint_percent, 0)} %`],
                        ["Objective score", fmt(opt.objective_score, 4)],
                        ["Scenarios", `${opt.scenarios_evaluated}`],
                        ["Status", opt.recommended.overall_engineering_status],
                      ]}
                    />
                    <div>
                      <div className="text-[11px] font-bold text-slate-300 mb-1">TOP SCENARIOS</div>
                      {opt.top_scenarios.map((s) => (
                        <div key={s.rank} className="font-mono text-[11px] flex justify-between text-slate-300">
                          <span>#{s.rank} {fmt(s.inputs.steam_volume_t, 0)}t/{fmt(s.inputs.soak_time_h, 0)}h/{fmt(s.inputs.spm)}spm/{fmt(s.inputs.vfd_setpoint_percent, 0)}%VFD</span>
                          <span>{fmt(s.estimated_oil_production_bopd)} bopd · {fmt(s.score, 3)}</span>
                        </div>
                      ))}
                    </div>
                    {opt.pareto_frontier && opt.pareto_frontier.length > 0 && (
                      <ParetoSection
                        frontier={opt.pareto_frontier}
                        paretoCount={opt.pareto_count ?? opt.pareto_frontier.length}
                        policy={opt.recommendation_policy}
                        uncertainty={opt.uncertainty_note}
                        constraints={opt.constraints}
                        selected={paretoSel}
                        onSelect={setParetoSel}
                      />
                    )}
                    <div>
                      <div className="text-[11px] font-bold text-slate-300 mb-1">WHY (backend reasons)</div>
                      <ul className="list-disc pl-4 space-y-1 text-slate-400">
                        {opt.why_recommended.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
      <div className="px-4 py-2 border-t border-slate-700/40 text-[10px] font-mono text-slate-500">
        Prototype visualization — relative units, not field dimensions.
      </div>
    </aside>
  );
}
