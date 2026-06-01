import { useEffect, useState } from "react";
import { ArrowUp, ArrowDown } from "lucide-react";

// Static, illustrative ticker. Pure presentation — values jitter on a timer
// so the dashboard always feels "live" without needing a market feed.
const SYMBOLS = [
  { sym: "SPX", val: 5814.32, ch: 0.42 },
  { sym: "VIX", val: 14.21, ch: -2.31 },
  { sym: "DJI", val: 42118.6, ch: 0.18 },
  { sym: "NDX", val: 20453.9, ch: 0.66 },
  { sym: "LBO/EV", val: 11.8, ch: 0.05 },
  { sym: "MID-MKT M&A", val: 213, ch: -1.4 },
  { sym: "USD/EUR", val: 1.082, ch: 0.11 },
  { sym: "10Y UST", val: 4.21, ch: 0.03 },
  { sym: "WTI", val: 71.4, ch: -0.92 },
  { sym: "BTC", val: 67124, ch: 1.42 },
];

export default function TickerBar() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 4200);
    return () => clearInterval(t);
  }, []);

  const items = SYMBOLS.map((s) => {
    const jitter = (Math.sin(tick + s.sym.length) * 0.3).toFixed(2);
    const ch = s.ch + parseFloat(jitter) * 0.1;
    const up = ch >= 0;
    return { ...s, ch, up };
  });

  const renderGroup = (k) => (
    <div className="flex shrink-0 items-center gap-8 pr-8" key={k}>
      {items.map((s) => (
        <div key={k + s.sym} className="flex items-center gap-2 font-mono text-[11px]">
          <span className="text-[var(--cv-muted)]">{s.sym}</span>
          <span className="text-[var(--cv-text)]">{s.val.toLocaleString()}</span>
          <span className={s.up ? "text-[var(--cv-success)]" : "text-[var(--cv-danger)]"}>
            {s.up ? <ArrowUp className="inline h-3 w-3" /> : <ArrowDown className="inline h-3 w-3" />}
            {Math.abs(s.ch).toFixed(2)}%
          </span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="border-y border-[var(--cv-border)] bg-[var(--cv-surface)] overflow-hidden">
      <div className="flex cv-ticker whitespace-nowrap py-1.5">
        {renderGroup("a")}
        {renderGroup("b")}
      </div>
    </div>
  );
}
