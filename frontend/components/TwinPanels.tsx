"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { fmt } from "@/lib/scene";
import type {
  AnalyticsResponse,
  CyclePlanResponse,
  CycleResponse,
  DynacardResponse,
  HistoryPoint,
  PredictResponse,
  ScenarioOverrides,
  SimulateResponse,
  TwinSnapshot,
} from "@/lib/types";
import { DynaCardChart, LineChart, ProbabilityBar } from "./Charts";
import { Delta, ErrorLine, Kpi, Loading, Note, Pill, PrimaryButton, Rows, Section } from "./ui";

/* Fetch helper: refetches whenever wellId / refreshKey change; keeps last data while reloading. */
function useFetch<T>(fn: (() => Promise<T>) | null, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!fn) return;
    let alive = true;
    fn()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}

const daysSince = (ts: string, t0: number) => (Date.parse(ts) - t0) / 86_400_000;

/* ======================= WHAT-IF ======================= */

type SliderKey = "steam_volume_t" | "steam_injection_pressure_bar" | "soak_time_h" | "vfd_percent" | "stroke_in" | "water_cut_percent";

const SLIDERS: { key: SliderKey; label: string; min: number; max: number; step: number; unit: string }[] = [
  { key: "steam_volume_t", label: "Steam volume", min: 0, max: 1500, step: 50, unit: "t" },
  { key: "steam_injection_pressure_bar", label: "Injection pressure", min: 0, max: 100, step: 5, unit: "bar" },
  { key: "soak_time_h", label: "Soak time", min: 0, max: 168, step: 6, unit: "h" },
  { key: "vfd_percent", label: "VFD speed (→ SPM)", min: 10, max: 100, step: 1, unit: "%" },
  { key: "stroke_in", label: "Stroke length", min: 48, max: 168, step: 6, unit: "in" },
  { key: "water_cut_percent", label: "Water cut", min: 0, max: 90, step: 1, unit: "%" },
];

export function WhatIfPanel({ wellId, twin }: { wellId: string; twin: TwinSnapshot }) {
  const [vals, setVals] = useState<Record<SliderKey, number> | null>(null);
  const [res, setRes] = useState<SimulateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const twinRef = useRef(twin);
  twinRef.current = twin;

  // Initialise once per well (and on reset) from the stored operating state, so live
  // updates do not yank the sliders out from under the user.
  useEffect(() => {
    let alive = true;
    setVals(null);
    setRes(null);
    api
      .well(wellId)
      .then((w) => {
        if (!alive) return;
        setVals({
          steam_volume_t: w.steam_volume_t,
          steam_injection_pressure_bar: w.steam_injection_pressure_bar,
          soak_time_h: w.soak_time_h,
          vfd_percent: twinRef.current.vfd_setpoint_percent,
          stroke_in: w.stroke_in,
          water_cut_percent: w.water_cut_percent,
        });
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [wellId, resetKey]);

  useEffect(() => {
    if (!vals) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const o: ScenarioOverrides = { ...vals };
      api
        .simulate(wellId, o)
        .then((r) => (setRes(r), setError(null)))
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }, 250);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [vals, wellId]);

  if (!vals) return <Loading what="operating state" />;
  const c = res?.current;
  const s = res?.scenario;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2">
        <Note>
          Drag any control: the backend twin re-simulates instantly. Simulation only — nothing is sent
          to equipment. VFD maps to SPM through the prototype drive ratio.
        </Note>
        <button
          onClick={() => setResetKey((k) => k + 1)}
          className="shrink-0 text-[10px] font-mono px-2 py-1 rounded bg-slate-700/70 border border-slate-600/60 hover:border-teal-300/50"
        >
          RESET
        </button>
      </div>
      <div className="space-y-2.5">
        {SLIDERS.map((sl) => (
          <label key={sl.key} className="block">
            <div className="flex justify-between text-[11px] font-mono">
              <span className="text-slate-400">{sl.label}</span>
              <span className="text-teal-200">
                {fmt(vals[sl.key], sl.step < 1 ? 1 : 0)} {sl.unit}
                {sl.key === "vfd_percent" && s && <span className="text-slate-500"> · {fmt(s.spm)} SPM</span>}
              </span>
            </div>
            <input
              type="range"
              min={sl.min}
              max={sl.max}
              step={sl.step}
              value={vals[sl.key]}
              onChange={(e) => setVals((v) => (v ? { ...v, [sl.key]: Number(e.target.value) } : v))}
              className="w-full accent-teal-400"
            />
          </label>
        ))}
      </div>
      {error && <ErrorLine error={error} />}
      {c && s && res && (
        <Section title="CURRENT → SCENARIO">
          <div className="text-xs font-mono space-y-1">
            {(
              [
                ["Oil", c.estimated_oil_production_bopd, s.estimated_oil_production_bopd, "bopd", "up", 1],
                ["Liquid", c.estimated_liquid_production_bpd, s.estimated_liquid_production_bpd, "bpd", "up", 1],
                ["Temperature", c.estimated_temperature_c, s.estimated_temperature_c, "°C", "up", 1],
                ["Viscosity", c.estimated_viscosity_cp, s.estimated_viscosity_cp, "cP", "down", 1],
                ["Pump fillage", c.estimated_pump_fillage, s.estimated_pump_fillage, "", "up", 2],
                ["SOR", c.steam_oil_ratio_t_per_bbl, s.steam_oil_ratio_t_per_bbl, "t/bbl", "down", 3],
                ["Energy", c.total_energy_kwh, s.total_energy_kwh, "kWh", "down", 0],
              ] as const
            ).map(([k, a, b, unit, good, d]) => (
              <div key={k} className="grid grid-cols-[1fr_auto_auto_auto] gap-2 items-baseline">
                <span className="text-slate-400">{k}</span>
                <span className="text-slate-500 text-right">{fmt(a, d)}</span>
                <span className="text-slate-100 text-right">{fmt(b, d)} <span className="text-[10px] text-slate-500">{unit}</span></span>
                <span className="text-right w-16">
                  <Delta v={a !== null && b !== null ? b - a : null} digits={d} goodWhen={good} />
                </span>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 text-[11px] font-mono pt-1">
            <Pill level={c.overall_engineering_status} />→<Pill level={s.overall_engineering_status} />
            <span className="text-slate-500">{s.production_limiting_factor.replace("_", " ").toLowerCase()}</span>
          </div>
        </Section>
      )}
    </div>
  );
}

/* ======================= CSS CYCLE ======================= */

export function CyclePanel({ wellId, refreshKey }: { wellId: string; refreshKey: number }) {
  const { data: cyc, error } = useFetch<CycleResponse>(() => api.cycle(wellId), [wellId, refreshKey]);
  const [plan, setPlan] = useState<CyclePlanResponse | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planErr, setPlanErr] = useState<string | null>(null);
  useEffect(() => setPlan(null), [wellId]);

  if (error) return <ErrorLine error={error} />;
  if (!cyc) return <Loading what="CSS cycle" />;

  const down = cyc.injection_days + cyc.soak_days;
  const prod = cyc.series.filter((p) => p.phase === "PRODUCTION");
  const cutoffX = down + cyc.optimal_cutoff_production_day;
  const horizon = cutoffX + Math.max(20, cyc.optimal_cutoff_production_day);
  const shown = cyc.series.filter((p) => p.day <= horizon);

  const runPlan = async () => {
    setPlanning(true);
    setPlanErr(null);
    try {
      setPlan(await api.cyclePlan(wellId));
    } catch (e) {
      setPlanErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPlanning(false);
    }
  };

  const steams = plan ? Array.from(new Set(plan.candidates.map((c) => c.steam_volume_t))).sort((a, b) => a - b) : [];
  const soaks = plan ? Array.from(new Set(plan.candidates.map((c) => c.soak_time_h))).sort((a, b) => a - b) : [];
  const maxAvg = plan ? Math.max(...plan.candidates.map((c) => c.average_cycle_rate_bopd)) : 1;

  return (
    <div className="space-y-4">
      <Section title="ONE CSS CYCLE AT CURRENT SETTINGS">
        <LineChart
          height={160}
          xLabel="cycle day"
          yLabel="oil bopd"
          bands={[
            { x0: 0, x1: cyc.injection_days, color: "rgba(251,113,133,0.10)", label: "INJ" },
            { x0: cyc.injection_days, x1: down, color: "rgba(251,191,36,0.10)", label: "SOAK" },
          ]}
          markers={[{ x: cutoffX, label: `cut-off d${cyc.optimal_cutoff_production_day}`, color: "#2dd4bf" }]}
          series={[
            { name: "twin oil rate", color: "#f5a524", points: shown.map((p) => [p.day, p.oil_rate_bopd]) },
            {
              name: "cold (no steam) rate",
              color: "#64748b",
              dashed: true,
              points: [
                [0, cyc.cold_oil_rate_bopd],
                [horizon, cyc.cold_oil_rate_bopd],
              ],
            },
          ]}
        />
        <div className="grid grid-cols-3 gap-1.5">
          <Kpi label="Cycle-avg rate" value={fmt(cyc.average_cycle_rate_bopd)} unit="bopd" tone="good" />
          <Kpi label="Cycle length" value={fmt(cyc.cycle_length_days, 0)} unit="d" />
          <Kpi label="SOR" value={fmt(cyc.cycle_sor_cwe, 2)} unit="CWE" tone={(cyc.cycle_sor_cwe ?? 99) > 6 ? "warn" : undefined} />
          <Kpi label="Cycle oil" value={fmt(cyc.cycle_oil_bbl, 0)} unit="bbl" />
          <Kpi label="Incremental" value={fmt(cyc.incremental_oil_bbl, 0)} unit="bbl" tone={cyc.incremental_oil_bbl > 0 ? "good" : "bad"} />
          <Kpi label="Peak rate" value={fmt(cyc.peak_oil_rate_bopd)} unit="bopd" />
        </div>
        <Note>{cyc.explanation}</Note>
      </Section>

      {prod.length > 0 && (
        <Section title="HEATED-ZONE COOLING">
          <LineChart
            height={110}
            xLabel="production day"
            yLabel="°C"
            yMin={Math.min(...prod.map((p) => p.temperature_c ?? 0)) - 5}
            markers={[{ x: cyc.optimal_cutoff_production_day, label: "cut-off", color: "#2dd4bf" }]}
            series={[
              {
                name: "temperature",
                color: "#ff6b35",
                points: prod.filter((p) => p.day <= horizon).map((p) => [p.day - down, p.temperature_c ?? 0]),
              },
            ]}
          />
        </Section>
      )}

      <Section title="CYCLE PLANNER (steam × soak)">
        <PrimaryButton onClick={runPlan} disabled={planning}>
          {planning ? "Simulating 25 cycles…" : "PLAN NEXT CYCLE"}
        </PrimaryButton>
        {planErr && <ErrorLine error={planErr} />}
        {plan && (
          <div className="space-y-2">
            <div className="rounded-lg border border-leaf/40 bg-leaf/10 p-2 text-xs font-mono space-y-0.5">
              <div className="text-leaf font-bold">RECOMMENDED</div>
              <div>
                {fmt(plan.recommended.steam_volume_t, 0)} t steam · {fmt(plan.recommended.soak_time_h, 0)} h soak · cut off after{" "}
                {plan.recommended.optimal_cutoff_production_day} d
              </div>
              <div className="text-slate-300">
                {fmt(plan.recommended.average_cycle_rate_bopd)} bopd cycle-avg (
                <Delta v={plan.average_rate_gain_bopd} /> vs now) · SOR {fmt(plan.recommended.cycle_sor_cwe, 2)} CWE
              </div>
            </div>
            <div className="text-[10px] font-mono text-slate-500">Cycle-average oil rate (bopd); ✕ = SOR above {plan.sor_limit_cwe}</div>
            <table className="w-full text-[10px] font-mono border-separate border-spacing-0.5">
              <thead>
                <tr>
                  <th className="text-slate-500 font-normal text-left">t \ h</th>
                  {soaks.map((s) => (
                    <th key={s} className="text-slate-500 font-normal">{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {steams.map((st) => (
                  <tr key={st}>
                    <td className="text-slate-500">{st}</td>
                    {soaks.map((sk) => {
                      const c = plan.candidates.find((x) => x.steam_volume_t === st && x.soak_time_h === sk)!;
                      const best = c === plan.recommended || (c.steam_volume_t === plan.recommended.steam_volume_t && c.soak_time_h === plan.recommended.soak_time_h);
                      const a = c.average_cycle_rate_bopd / maxAvg;
                      return (
                        <td
                          key={sk}
                          title={`${st} t, ${sk} h: ${c.average_cycle_rate_bopd} bopd, SOR ${c.cycle_sor_cwe}, cut-off d${c.optimal_cutoff_production_day}`}
                          className={`text-center rounded py-0.5 ${best ? "ring-1 ring-leaf text-white font-bold" : "text-slate-200"}`}
                          style={{ background: c.feasible ? `rgba(245,165,36,${0.12 + 0.6 * a})` : "rgba(51,65,85,0.5)" }}
                        >
                          {c.feasible ? fmt(c.average_cycle_rate_bopd, 0) : "✕"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <Note>{plan.explanation}</Note>
          </div>
        )}
      </Section>
    </div>
  );
}

/* ======================= SRP DYNACARD ======================= */

export function SrpPanel({ wellId, refreshKey }: { wellId: string; refreshKey: number }) {
  const { data: card, error } = useFetch<DynacardResponse>(() => api.dynacard(wellId), [wellId, refreshKey]);
  if (error) return <ErrorLine error={error} />;
  if (!card) return <Loading what="dynamometer card" />;
  const worst = card.diagnosis.reduce((a, d) => (d.severity === "HIGH" ? d : a), card.diagnosis[0]);
  return (
    <div className="space-y-4">
      <Section title="PREDICTED SURFACE DYNACARD" right={<Pill level={worst.severity === "LOW" ? "NORMAL" : worst.severity} />}>
        <DynaCardChart
          points={card.points}
          refLines={[
            { y: card.buoyant_rod_weight_lb, label: "buoyant rods", color: "#94a3b8" },
            { y: card.buoyant_rod_weight_lb + card.fluid_load_lb, label: "rods + fluid", color: "#f5a524" },
          ]}
        />
        <div className="grid grid-cols-3 gap-1.5">
          <Kpi label="PPRL" value={fmt(card.pprl_lb, 0)} unit="lb" />
          <Kpi label="MPRL" value={fmt(card.mprl_lb, 0)} unit="lb" tone={card.mprl_lb <= 0 ? "bad" : card.mprl_lb < 0.25 * card.buoyant_rod_weight_lb ? "warn" : undefined} />
          <Kpi label="Goodman" value={fmt(card.goodman_loading_percent, 0)} unit="%" tone={card.goodman_loading_percent >= 100 ? "bad" : card.goodman_loading_percent >= 90 ? "warn" : "good"} />
          <Kpi label="Fillage" value={fmt(card.estimated_pump_fillage, 2)} tone={card.estimated_pump_fillage < 0.75 ? "bad" : "good"} />
          <Kpi label="Tubing visc." value={fmt(card.tubing_viscosity_cp, 0)} unit="cP" />
          <Kpi label="PR power" value={fmt(card.polished_rod_hp, 1)} unit="hp" />
        </div>
      </Section>
      <Section title="DIAGNOSIS">
        <div className="space-y-2">
          {card.diagnosis.map((d) => (
            <div key={d.code} className="text-xs space-y-0.5">
              <div className="flex items-center gap-2">
                <Pill level={d.severity === "LOW" ? "NORMAL" : d.severity} />
                <span className="font-mono text-slate-200">{d.code.replace(/_/g, " ")}</span>
              </div>
              <p className="text-[11px] text-slate-400">{d.detail}</p>
            </div>
          ))}
        </div>
      </Section>
      <Note>
        Card from standard SRP relations (API 11L rod weights, Mills acceleration, 0.340·SG·D²·H fluid
        load, modified Goodman) plus prototype viscous drag at mean tubing temperature{" "}
        {fmt(card.tubing_mean_temperature_c)} °C. Pump depth {fmt(card.pump_depth_m, 0)} m (prototype).
      </Note>
    </div>
  );
}

/* ======================= ANALYTICS ======================= */

export function AnalyticsPanel({ wellId, refreshKey }: { wellId: string; refreshKey: number }) {
  const { data: hist, error: hErr } = useFetch(() => api.wellHistory(wellId, 240), [wellId, refreshKey]);
  const { data: an, error: aErr } = useFetch<AnalyticsResponse>(() => api.analytics(wellId), [wellId, refreshKey]);
  if (hErr || aErr) return <ErrorLine error={(hErr || aErr)!} />;
  if (!hist || !an) return <Loading what="history + analytics" />;
  const pts: HistoryPoint[] = hist.points;
  if (pts.length < 2) {
    return (
      <div className="space-y-2 text-xs text-slate-400">
        <p className="font-mono">Only {pts.length} reading(s) stored for {wellId}.</p>
        <Note>Load the synthetic field or start LIVE in the top bar to build history; analytics need a time series.</Note>
      </div>
    );
  }
  const t0 = Date.parse(pts[0].timestamp);
  const k = an.calibration.k;
  // Calibrated twin is drawn per production run so it never bridges a shut-in gap.
  const runs: HistoryPoint[][] = [];
  pts.forEach((p, i) => {
    if (p.css_phase !== "PRODUCTION") return;
    if (i === 0 || pts[i - 1].css_phase !== "PRODUCTION") runs.push([]);
    runs[runs.length - 1].push(p);
  });
  const tLast = daysSince(pts[pts.length - 1].timestamp, t0);
  const anomalyXs = an.anomalies.slice(-6).map((a) => ({
    x: daysSince(a.timestamp, t0),
    label: a.type === "TWIN_DIVERGENCE" ? "divergence" : a.metric.replace(/_bar|_bopd/g, ""),
    color: "#fb7185",
  }));

  // Shade shut-in (injection/soak) periods.
  const bands = [];
  let start: number | null = null;
  for (const p of pts) {
    const x = daysSince(p.timestamp, t0);
    if (p.css_phase !== "PRODUCTION" && start === null) start = x;
    if (p.css_phase === "PRODUCTION" && start !== null) {
      bands.push({ x0: start, x1: x, color: "rgba(251,191,36,0.08)", label: "shut-in" });
      start = null;
    }
  }
  if (start !== null) bands.push({ x0: start, x1: tLast, color: "rgba(251,191,36,0.08)", label: "shut-in" });

  return (
    <div className="space-y-4">
      <Section title="MEASURED vs DIGITAL TWIN">
        <LineChart
          height={160}
          xLabel="days"
          yLabel="oil bopd"
          bands={bands}
          markers={anomalyXs.slice(-3)}
          series={[
            { name: "measured", color: "#e2e8f0", points: pts.map((p) => [daysSince(p.timestamp, t0), p.oil_rate_bopd]) },
            ...runs.map((run, i) => ({
              name: `calibrated twin (k=${fmt(k, 3)})`,
              color: "#2dd4bf",
              hideLegend: i > 0,
              points: run.map((p): [number, number] => [daysSince(p.timestamp, t0), k * p.twin_oil_bopd]),
            })),
          ]}
        />
      </Section>
      <Section title="TWIN AUTO-CALIBRATION" right={<Pill level={an.calibration.status === "CALIBRATED" ? "NOMINAL" : "MODERATE"} />}>
        <div className="grid grid-cols-3 gap-1.5">
          <Kpi label="Scale k" value={fmt(k, 3)} />
          <Kpi label="MAPE raw" value={fmt(an.calibration.uncalibrated_mape_percent, 0)} unit="%" tone="bad" />
          <Kpi label="MAPE calib." value={fmt(an.calibration.mape_percent, 1)} unit="%" tone="good" />
        </div>
        <Note>{an.calibration.explanation}</Note>
      </Section>
      <Section title="DECLINE FORECAST (ARPS EXPONENTIAL)">
        {an.decline.status === "FITTED" ? (
          <>
            <LineChart
              height={110}
              xLabel="days ahead"
              yLabel="bopd"
              series={[{ name: "forecast", color: "#a78bfa", dashed: true, points: an.decline.forecast.map((f) => [f.day_ahead, f.oil_rate_bopd]) }]}
            />
            <div className="grid grid-cols-3 gap-1.5">
              <Kpi label="Decline" value={fmt(an.decline.decline_percent_per_month, 0)} unit="%/mo" />
              <Kpi label="30-d oil" value={fmt(an.decline.forecast_cum_oil_bbl, 0)} unit="bbl" />
              <Kpi label="Fit R²" value={fmt(an.decline.r2, 2)} />
            </div>
          </>
        ) : (
          <Note>{an.decline.explanation}</Note>
        )}
      </Section>
      <Section title={`ANOMALIES (${an.anomalies.length})`}>
        {an.anomalies.length === 0 ? (
          <Note>No anomalies in the stored history.</Note>
        ) : (
          <div className="space-y-1.5 max-h-44 overflow-y-auto scroll-thin pr-1">
            {an.anomalies
              .slice()
              .reverse()
              .slice(0, 12)
              .map((a, i) => (
                <div key={i} className="text-[11px]">
                  <span className="font-mono text-rose-300">{a.type === "TWIN_DIVERGENCE" ? "DIVERGENCE" : "OUTLIER"}</span>{" "}
                  <span className="font-mono text-slate-500">{a.timestamp.slice(5, 16).replace("T", " ")}</span>
                  <div className="text-slate-400">{a.detail}</div>
                </div>
              ))}
          </div>
        )}
        <Note>
          Robust modified z-score (median/MAD) with engineering deadbands, plus divergence from the
          calibrated twin, which separates real faults from normal CSS decline.
        </Note>
      </Section>
    </div>
  );
}

/* ======================= ML ======================= */

export function MlPanel({ wellId, refreshKey }: { wellId: string; refreshKey: number }) {
  const { data: pred, error } = useFetch<PredictResponse>(() => api.predict(wellId), [wellId, refreshKey]);
  const { data: hist } = useFetch(() => api.wellHistory(wellId, 240), [wellId, refreshKey]);
  if (error) return <ErrorLine error={error} />;
  if (!pred) return <Loading what="failure models" />;
  const pts = (hist?.points ?? []).filter((p) => p.css_phase === "PRODUCTION");
  const t0 = pts.length ? Date.parse(pts[0].timestamp) : 0;
  const maxAbs = Math.max(
    ...Object.values(pred.predictions).flatMap((p) => p.top_drivers.map((d) => Math.abs(d.contribution_log_odds))),
    0.01
  );

  return (
    <div className="space-y-4">
      {pred.mode && (
        <div
          className="text-[10px] font-mono px-2 py-1.5 rounded-lg border border-amber-500/40 text-amber-300 bg-amber-500/10"
          title="Demonstration model output trained on synthetic hazard labels — not field-validated intelligence"
        >
          {pred.mode} DEMO MODEL · not field-validated · not production-safe
        </div>
      )}
      {(["rod_failure", "pump_unsetting"] as const).map((name) => {
        const p = pred.predictions[name];
        const card = pred.model_info.models.find((m) => m.name === name);
        return (
          <Section
            key={name}
            title={`${name.replace("_", " ").toUpperCase()} · NEXT ${p.horizon_days} DAYS`}
            right={<Pill level={p.risk_band} />}
          >
            <div className="flex items-center gap-2">
              <span className="text-lg font-mono font-bold text-slate-100 w-16">{fmt(p.probability * 100, 1)}%</span>
              <ProbabilityBar p={p.probability} band={p.risk_band} />
            </div>
            <div className="space-y-1">
              {p.top_drivers.map((d) => (
                <div key={d.feature} className="grid grid-cols-[1fr_90px] gap-2 items-center text-[10px] font-mono">
                  <span className="text-slate-400 truncate" title={d.label}>
                    {d.label} <span className="text-slate-600">({fmt(d.value, 2)})</span>
                  </span>
                  <div className="relative h-2 bg-slate-800 rounded">
                    <div
                      className="absolute top-0 h-2 rounded"
                      style={{
                        left: d.contribution_log_odds >= 0 ? "50%" : `${50 - (Math.abs(d.contribution_log_odds) / maxAbs) * 50}%`,
                        width: `${(Math.abs(d.contribution_log_odds) / maxAbs) * 50}%`,
                        background: d.contribution_log_odds >= 0 ? "#fb7185" : "#34d399",
                      }}
                    />
                    <div className="absolute left-1/2 top-[-2px] h-3 w-px bg-slate-500" />
                  </div>
                </div>
              ))}
            </div>
            {card && (
              <div className="text-[10px] font-mono text-slate-500">
                holdout AUC {fmt(card.metrics.auc, 3)} (ceiling {fmt(card.metrics.oracle_auc, 3)}) · accuracy{" "}
                {fmt(card.metrics.accuracy_at_0_5 * 100, 0)}% · Brier {fmt(card.metrics.brier_score, 3)}
              </div>
            )}
          </Section>
        );
      })}
      {pts.length > 1 && (
        <Section title="RISK TREND (PRODUCTION READINGS)">
          <LineChart
            height={110}
            xLabel="days"
            yLabel="prob."
            yMin={0}
            series={[
              { name: "rod failure", color: "#fb7185", points: pts.map((p) => [daysSince(p.timestamp, t0), p.rod_failure_prob]) },
              { name: "pump unsetting", color: "#fbbf24", points: pts.map((p) => [daysSince(p.timestamp, t0), p.pump_unsetting_prob]) },
            ]}
          />
        </Section>
      )}
      <Section title="MODEL CARD">
        <Rows
          rows={[
            ["Model", "Logistic regression (L2)"],
            ["Features", "9 physics-informed (twin + dynacard)"],
            ["Training / holdout", `${pred.model_info.training_samples} / ${pred.model_info.holdout_samples}`],
            ["Labels", pred.model_info.label_source],
          ]}
        />
        <Note>
          {pred.model_info.data_statement} &quot;Ceiling&quot; is the AUC of the true synthetic hazard on the
          same noisy labels — the best any model could score.
        </Note>
      </Section>
    </div>
  );
}
