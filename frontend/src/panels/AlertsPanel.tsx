// Alerts panel (M7, PLAN §4.8). Renders the live signal feed from /api/alerts
// (fetched once in App for the header badge, passed down here). Negative prices,
// price spikes, congested borders, near-full NTC — severity-sorted by the backend.

import type { Alert, AlertsSnapshot } from "../types";

const SEV: Record<string, { color: string; label: string }> = {
  crit: { color: "#f87171", label: "critique" },
  warn: { color: "#fbbf24", label: "à surveiller" },
  info: { color: "#60a5fa", label: "info" },
};

const TYPE_LABEL: Record<Alert["type"], string> = {
  negative_price: "Prix négatif",
  price_spike: "Pic de prix",
  high_spread: "Congestion",
  near_full_capacity: "Capacité",
};

const tsFmt = new Intl.DateTimeFormat("fr-BE", {
  timeZone: "Europe/Brussels",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

interface Props {
  data: AlertsSnapshot | null;
  warming: boolean;
}

export default function AlertsPanel({ data, warming }: Props) {
  if (!data) {
    return (
      <p className="font-mono text-xs text-amber-300">
        {warming ? "◌ signaux en préparation…" : "chargement…"}
      </p>
    );
  }

  const { counts, alerts } = data;
  const dataTs = data.data_ts ? tsFmt.format(new Date(data.data_ts)) : "—";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        {(["crit", "warn", "info"] as const).map((sev) => (
          <div
            key={sev}
            className="rounded-lg border border-white/10 bg-surface-2/50 px-3 py-2"
          >
            <div className="flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: SEV[sev].color }}
              />
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                {SEV[sev].label}
              </span>
            </div>
            <div className="font-mono text-base font-semibold text-slate-100">
              {counts[sev] ?? 0}
            </div>
          </div>
        ))}
      </div>

      <p className="text-[10px] text-slate-500">
        instant {dataTs} · {alerts.length} signaux · niveau zone &amp; frontière
      </p>

      {alerts.length === 0 ? (
        <p className="rounded-lg border border-emerald-400/20 bg-surface-2/40 px-3 py-3 text-[11px] text-emerald-300">
          ✓ Aucun signal — marché calme à cet instant.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {alerts.map((a, i) => (
            <li
              key={`${a.type}-${a.key}-${i}`}
              className="flex items-start gap-2 rounded-lg border border-white/10 bg-surface-2/40 px-3 py-2"
            >
              <span
                className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                style={{ background: SEV[a.severity].color }}
                title={SEV[a.severity].label}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-xs text-slate-200">{a.key}</span>
                  <span className="shrink-0 text-[10px] uppercase tracking-wide text-slate-500">
                    {TYPE_LABEL[a.type]}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400">{a.detail}</div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="border-t border-white/10 pt-3 text-[10px] text-slate-600">
        Capacité (utilisation NTC) :{" "}
        <span className="text-slate-400">visible avec ENTSO-E</span> — aucune NTC fabriquée
        sur Energy-Charts.
      </p>
    </div>
  );
}
