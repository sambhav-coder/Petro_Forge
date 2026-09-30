"use client";

import type { Alert } from "@/lib/types";
import { Pill } from "./ui";

export default function AlertsDrawer({
  alerts,
  onAck,
  onPick,
  onClose,
}: {
  alerts: Alert[];
  onAck: (id: string) => void;
  onPick: (wellId: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="absolute right-0 top-full mt-2 w-[380px] max-h-[70vh] overflow-y-auto scroll-thin rounded-xl shadow-2xl z-30 p-3 space-y-2 bg-[#0b1220]/[0.97] border border-slate-600/50">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-bold font-mono text-slate-200">ALERTS · twin, dynacard, ML, anomaly</div>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xs font-mono">✕</button>
      </div>
      {alerts.length === 0 && <p className="text-xs text-slate-500 font-mono">No alerts raised.</p>}
      {alerts.map((a) => (
        <div
          key={a.alert_id}
          className={`rounded-lg border p-2 space-y-1 ${
            a.acknowledged ? "border-slate-700/50 opacity-60" : "border-slate-600/60 bg-slate-800/40"
          }`}
        >
          <div className="flex items-center gap-2">
            <Pill level={a.severity} />
            <button onClick={() => onPick(a.well_id)} className="text-[11px] font-mono text-teal-200 hover:underline">
              {a.well_id}
            </button>
            <span className="text-[10px] font-mono text-slate-500">{a.timestamp.slice(5, 16).replace("T", " ")}</span>
            {a.active && <span className="text-[9px] font-mono text-rose-300">ACTIVE</span>}
            {a.model_mode && (
              <span
                className="text-[9px] font-mono px-1 py-px rounded border border-amber-500/40 text-amber-300"
                title="Demonstration model output — not field-validated intelligence"
              >
                {a.model_mode}
              </span>
            )}
            <div className="flex-1" />
            {!a.acknowledged && (
              <button
                onClick={() => onAck(a.alert_id)}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-700 border border-slate-600 hover:border-teal-300/60"
              >
                ACK
              </button>
            )}
          </div>
          <div className="text-xs text-slate-200">{a.title}</div>
          <div className="text-[11px] text-slate-400 leading-snug">{a.detail}</div>
        </div>
      ))}
      <p className="text-[10px] text-slate-500">
        Decision support only: alerts recommend inspection or setpoint review and never command equipment.
      </p>
    </div>
  );
}
