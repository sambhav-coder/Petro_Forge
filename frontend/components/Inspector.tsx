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
  SceneSelection,
  TwinSnapshot,
  WellTelemetry,
  HistoryResponse,
  WellCoverageSummary,
} from "@/lib/types";

type Tab = "OVERVIEW" | "TELEMETRY" | "PHYSICS" | "HISTORY" | "ANALYTICS" | "ML" | "OPTIMIZATION";

function Pill({ level }: { level: string }) {
  const cls =
    level === "LOW" || level === "NOMINAL"
      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
      : level === "MODERATE" || level === "ELEVATED"
        ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
        : "bg-rose-500/15 text-rose-300 border-rose-500/30";
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border font-mono ${cls}`}>
      {level}
    </span>
  );
}

function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <div className="text-xs font-mono space-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2">
          <span className="text-slate-400">{k}</span>
          <span className="text-slate-100 text-right">{v}</span>
        </div>
      ))}
    </div>
  );
}

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
}) {
  const [tab, setTab] = useState<Tab>("OVERVIEW");
  const [historyData, setHistoryData] = useState<HistoryResponse | null>(null);
  const [coverageData, setCoverageData] = useState<WellCoverageSummary | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const tabs: Tab[] = ["OVERVIEW", "TELEMETRY", "PHYSICS", "HISTORY", "ANALYTICS", "ML", "OPTIMIZATION"];

  // Load historical data when HISTORY tab is selected
  useEffect(() => {
    if (tab === "HISTORY" && wellId) {
      setHistoryLoading(true);
      Promise.all([
        api.history({ well_id, include_derived: false, include_synthetic: false, include_live: true, limit: 100 }),
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

  return (
    <aside className="glass rounded-none border-l border-slate-700/40 w-[380px] shrink-0 flex flex-col min-h-0">
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

      <div className="flex gap-1 px-3 overflow-x-auto scroll-thin border-b border-slate-700/40">
        {tabs.map((t) => (
          <button
            key={t}
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
                  <span className="text-xs font-mono text-amber-200">{twin.css_phase}</span>
                </div>
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
                      ["VFD", `${fmt(telemetry.vfd_percent)} %`],
                    ]}
                  />
                </section>
                <section>
                  <h4 className="text-[11px] font-bold text-slate-300 mb-1">TWIN SNAPSHOT</h4>
                  <Rows
                    rows={[
                      ["Production", `${fmt(twin.estimated_oil_production_bopd)} BOPD`],
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
                    ["Pump capacity", `${fmt(twin.pump_capacity_bopd)} BOPD`],
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

            {tab === "ANALYTICS" && (
              <div className="text-xs text-slate-400 space-y-2">
                <Pill level="MODERATE" />
                <p className="font-mono">Coming in Phase 3 — Advanced Analytics.</p>
                <p>Advanced trend analysis and anomaly detection will be available with ML integration.</p>
              </div>
            )}

            {tab === "ML" && (
              <div className="text-xs text-slate-400 space-y-2">
                <Pill level="MODERATE" />
                <p className="font-mono">Coming in Phase 3 — ML Intelligence.</p>
                <p>ML models will consume only ML-safe historical observations. See HISTORY tab for data readiness.</p>
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
                        ["Objective score", fmt(opt.objective_score, 4)],
                        ["Scenarios", `${opt.scenarios_evaluated}`],
                        ["Status", opt.recommended.overall_engineering_status],
                      ]}
                    />
                    <div>
                      <div className="text-[11px] font-bold text-slate-300 mb-1">TOP SCENARIOS</div>
                      {opt.top_scenarios.map((s) => (
                        <div key={s.rank} className="font-mono text-[11px] flex justify-between text-slate-300">
                          <span>#{s.rank} {fmt(s.inputs.steam_volume_t, 0)}t/{fmt(s.inputs.soak_time_h, 0)}h/{fmt(s.inputs.spm)}spm</span>
                          <span>{fmt(s.estimated_oil_production_bopd)} bopd · {fmt(s.score, 3)}</span>
                        </div>
                      ))}
                    </div>
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
