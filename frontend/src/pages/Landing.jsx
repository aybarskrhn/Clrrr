import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  ShieldCheck,
  FileSearch,
  Zap,
  Lock,
  CheckCircle2,
  TerminalSquare,
} from "lucide-react";
import { LANDING, NAV } from "@/constants/testIds";
import TickerBar from "@/components/TickerBar";

const FEATURES = [
  {
    key: "ingest",
    icon: FileSearch,
    title: "Drag. Drop. Decoded.",
    body: "Drop any financial PDF — 10-Ks, LOIs, cap tables, audit reports — and ClearVault returns structured line items in under 90 seconds.",
  },
  {
    key: "redflags",
    icon: ShieldCheck,
    title: "Red-Flag Engine",
    body: "Surfaces customer concentration, off-balance liabilities, weak covenants, going-concern flags. Severity-ranked and source-cited.",
  },
  {
    key: "local",
    icon: Lock,
    title: "Zero-Onboarding. Secure.",
    body: "No SSO contracts. No InfoSec reviews. No developer integration. Your deal room never leaves your perimeter.",
  },
  {
    key: "speed",
    icon: Zap,
    title: "Built For Junior Analysts",
    body: "What used to take you a sleepless weekend now takes a coffee. Output is auditable, exportable, and citation-locked.",
  },
];

const PRICING = [
  {
    key: "analyst",
    name: "Analyst",
    price: "$0",
    period: "/14-day trial",
    blurb: "For a single analyst evaluating their next deal.",
    perks: ["100 pages / month", "5 active deals", "Email support"],
    cta: "Start free",
    accent: false,
  },
  {
    key: "desk",
    name: "Desk",
    price: "$890",
    period: "/seat/month",
    blurb: "For a boutique deal team running multiple processes.",
    perks: [
      "Unlimited pages",
      "Unlimited deals",
      "Red-flag audit trail",
      "Comparable export to Excel",
      "Slack notifications",
    ],
    cta: "Talk to founder",
    accent: true,
  },
  {
    key: "firm",
    name: "Firm",
    price: "Custom",
    period: "",
    blurb: "Up to 25 seats. On-prem deployment option.",
    perks: ["On-prem inference", "SAML SSO", "Custom red-flag rules", "Dedicated solutions engineer"],
    cta: "Request demo",
    accent: false,
  },
];

const LOGOS = ["LAZARD", "EVERCORE", "CENTERVIEW", "QATALYST", "MOELIS", "GUGGENHEIM"];

const STATS = [
  { v: "47 hrs", k: "Saved per deal" },
  { v: "1,284", k: "Red flags surfaced" },
  { v: "98.4%", k: "Extraction accuracy" },
  { v: "<90s", k: "Per document" },
];

export default function Landing() {
  const [clock, setClock] = useState("");
  useEffect(() => {
    const tick = () => {
      const d = new Date();
      const hh = String(d.getUTCHours()).padStart(2, "0");
      const mm = String(d.getUTCMinutes()).padStart(2, "0");
      const ss = String(d.getUTCSeconds()).padStart(2, "0");
      setClock(`${hh}:${mm}:${ss} UTC`);
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="min-h-screen bg-[var(--cv-bg)] text-[var(--cv-text)]">
      {/* Nav */}
      <header className="border-b border-[var(--cv-border)] bg-[var(--cv-bg)]">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-8 py-4">
          <Link to="/" data-testid={NAV.brand} className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center border border-[var(--cv-primary)] bg-[var(--cv-primary)] text-black">
              <span className="font-mono text-sm font-bold">CV</span>
            </div>
            <span className="font-heading text-base font-bold tracking-tight">
              CLEAR<span className="text-[var(--cv-primary)]">VAULT</span>
            </span>
          </Link>
          <nav className="hidden items-center gap-8 md:flex">
            <a href="#product" className="font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:text-[var(--cv-text)]">
              Product
            </a>
            <a href="#pricing" className="font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:text-[var(--cv-text)]">
              Pricing
            </a>
            <a href="#security" className="font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:text-[var(--cv-text)]">
              Security
            </a>
            <span className="font-mono text-xs text-[var(--cv-muted)]">{clock}</span>
          </nav>
          <div className="flex items-center gap-2">
            <Link
              to="/login"
              data-testid={NAV.loginBtn}
              className="border border-[var(--cv-border)] px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
            >
              Sign in
            </Link>
            <Link
              to="/signup"
              data-testid={NAV.signupBtn}
              className="bg-[var(--cv-primary)] px-3 py-1.5 font-mono text-xs font-semibold uppercase tracking-wider text-black hover:bg-[var(--cv-primary-hover)]"
            >
              Open Terminal
            </Link>
          </div>
        </div>
        <TickerBar />
      </header>

      {/* Hero */}
      <section
        data-testid={LANDING.hero}
        className="relative overflow-hidden border-b border-[var(--cv-border)]"
      >
        <div
          aria-hidden
          className="absolute inset-0 opacity-70"
          style={{
            backgroundImage:
              "url(https://static.prod-images.emergentagent.com/jobs/dca0f65a-6270-4c83-83bc-e84806831efa/images/2616361f985978f68ce524526491f0758c9b4d0250d763bdb10ace05bd1f860d.png)",
            backgroundPosition: "center right",
            backgroundSize: "cover",
          }}
        />
        <div aria-hidden className="absolute inset-0 bg-black/70" />
        <div aria-hidden className="absolute inset-0 cv-grid-bg opacity-40" />
        <div aria-hidden className="absolute inset-0 cv-scanlines" />

        <div className="relative mx-auto grid max-w-[1400px] grid-cols-12 gap-6 px-8 py-24 md:py-32">
          <div className="col-span-12 md:col-span-8">
            <div className="cv-tag mb-6 flex items-center gap-3">
              <span className="inline-block h-1.5 w-1.5 bg-[var(--cv-primary)]" />
              MID-MARKET DUE DILIGENCE · v0.94 BETA
            </div>
            <h1 className="font-heading text-4xl font-black leading-[0.95] tracking-tight sm:text-5xl lg:text-7xl">
              The no-code <span className="text-[var(--cv-primary)]">M&A auditor</span>
              <br />
              for boutique deal teams<span className="cv-cursor" />
            </h1>
            <p className="mt-8 max-w-2xl font-body text-base leading-relaxed text-[var(--cv-muted)] md:text-lg">
              Drag a 400-page data-room PDF in. Get a structured balance sheet, red-flag log,
              and contract abstract back. No API keys. No developer onboarding. No public LLMs
              touching your deal.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-3">
              <Link
                to="/signup"
                data-testid={LANDING.heroCta}
                className="flex items-center gap-2 bg-[var(--cv-primary)] px-5 py-3 font-mono text-xs font-semibold uppercase tracking-wider text-black hover:bg-[var(--cv-primary-hover)]"
              >
                Open the terminal <ArrowRight className="h-4 w-4" />
              </Link>
              <a
                href="#product"
                data-testid={LANDING.heroSecondary}
                className="flex items-center gap-2 border border-[var(--cv-border)] px-5 py-3 font-mono text-xs uppercase tracking-wider text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
              >
                <TerminalSquare className="h-4 w-4" /> Watch ingest
              </a>
            </div>

            <div className="mt-14 grid grid-cols-2 gap-px border border-[var(--cv-border)] bg-[var(--cv-border)] md:grid-cols-4">
              {STATS.map((s) => (
                <div key={s.k} className="bg-[var(--cv-bg)] p-5">
                  <div className="font-mono text-2xl text-[var(--cv-primary)]">{s.v}</div>
                  <div className="mt-1 font-mono text-[10px] uppercase tracking-widest text-[var(--cv-muted)]">
                    {s.k}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="col-span-12 md:col-span-4">
            <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]/90 backdrop-blur">
              <div className="flex items-center justify-between border-b border-[var(--cv-border)] px-3 py-2">
                <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  ~/clearvault/extract.json
                </span>
                <span className="cv-chip cv-chip-green">LIVE</span>
              </div>
              <pre className="overflow-hidden p-4 font-mono text-[11px] leading-relaxed text-[var(--cv-muted)]">{`{
  "document_type": "balance_sheet",
  "summary": "Acme Industrial FY24 — 12% revenue
    growth, EBITDA compression driven by two
    customer concentration risks.",
  "financial_metrics": [
    { "label": "Revenue", "value": "$42.3M" },
    { "label": "EBITDA",  "value": "$7.1M"  },
    { "label": "Net Debt","value": "$11.8M" },
    { "label": "AR Days", "value": "73"     }
  ],
  "red_flags": [
    { "severity": "high",
      "title": "Top 2 customers = 61% revenue" },
    { "severity": "medium",
      "title": "Off-balance lease obligations" }
  ],
  "confidence": 0.91
}`}</pre>
            </div>
            <div className="mt-3 font-mono text-[11px] text-[var(--cv-muted)]">
              <span className="text-[var(--cv-primary)]">$</span> clearvault extract acme-fy24.pdf
              <span className="cv-cursor" />
            </div>
          </div>
        </div>

        {/* Logos band */}
        <div className="relative border-t border-[var(--cv-border)] bg-[var(--cv-bg)]">
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-6 px-8 py-6">
            <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-[var(--cv-muted)]">
              Built for desks at
            </span>
            <div className="flex flex-wrap items-center gap-x-10 gap-y-2">
              {LOGOS.map((l) => (
                <span key={l} className="font-mono text-sm tracking-[0.25em] text-[var(--cv-muted)]">
                  {l}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Product features */}
      <section id="product" className="border-b border-[var(--cv-border)]">
        <div className="mx-auto max-w-[1400px] px-8 py-24">
          <div className="grid grid-cols-12 gap-8">
            <div className="col-span-12 md:col-span-5">
              <span className="cv-tag">// 01 PRODUCT</span>
              <h2 className="mt-4 font-heading text-3xl font-bold tracking-tight md:text-5xl">
                A Bloomberg Terminal
                <br />
                for due diligence.
              </h2>
              <p className="mt-6 max-w-md font-body text-[var(--cv-muted)]">
                ClearVault sits between your data room and your model. Every line in your IC memo
                is now sourced, auditable, and one keystroke away.
              </p>
            </div>
            <div className="col-span-12 md:col-span-7">
              <div className="grid grid-cols-1 gap-px border border-[var(--cv-border)] bg-[var(--cv-border)] sm:grid-cols-2">
                {FEATURES.map(({ key, icon: Icon, title, body }) => (
                  <div
                    key={key}
                    data-testid={LANDING.featureCard(key)}
                    className="group bg-[var(--cv-bg)] p-6 transition-colors hover:bg-[var(--cv-surface)]"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center border border-[var(--cv-border)] group-hover:border-[var(--cv-primary)]">
                        <Icon className="h-4 w-4 text-[var(--cv-primary)]" />
                      </div>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--cv-muted)]">
                        {key}
                      </span>
                    </div>
                    <h3 className="mt-5 font-heading text-lg font-bold tracking-tight">{title}</h3>
                    <p className="mt-2 font-body text-sm text-[var(--cv-muted)]">{body}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-20 grid grid-cols-12 gap-6">
            <div className="col-span-12 md:col-span-7">
              <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
                <div className="flex items-center justify-between border-b border-[var(--cv-border)] px-4 py-2">
                  <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                    acme-fy24-audit.pdf — extract
                  </span>
                  <span className="cv-chip cv-chip-amber">DUE DILIGENCE</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full font-mono text-xs">
                    <thead>
                      <tr className="border-b border-[var(--cv-border)] text-[var(--cv-muted)]">
                        <th className="px-4 py-2 text-left">Line item</th>
                        <th className="px-4 py-2 text-right">FY23</th>
                        <th className="px-4 py-2 text-right">FY24</th>
                        <th className="px-4 py-2 text-right">Δ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ["Revenue", "37.7M", "42.3M", "+12.2%", "green"],
                        ["Gross Profit", "14.1M", "15.0M", "+6.4%", "muted"],
                        ["EBITDA", "8.4M", "7.1M", "−15.4%", "red"],
                        ["Operating Cash Flow", "6.9M", "5.2M", "−24.6%", "red"],
                        ["Net Debt", "9.8M", "11.8M", "+20.4%", "red"],
                        ["AR Days", "58", "73", "+25.8%", "amber"],
                      ].map(([k, a, b, d, color]) => (
                        <tr key={k} className="border-b border-[var(--cv-border)]/60">
                          <td className="px-4 py-2 text-[var(--cv-text)]">{k}</td>
                          <td className="px-4 py-2 text-right text-[var(--cv-muted)]">{a}</td>
                          <td className="px-4 py-2 text-right text-[var(--cv-text)]">{b}</td>
                          <td
                            className={`px-4 py-2 text-right ${
                              color === "green"
                                ? "text-[var(--cv-success)]"
                                : color === "red"
                                ? "text-[var(--cv-danger)]"
                                : color === "amber"
                                ? "text-[var(--cv-primary)]"
                                : "text-[var(--cv-muted)]"
                            }`}
                          >
                            {d}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div className="col-span-12 md:col-span-5">
              <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
                <div className="border-b border-[var(--cv-border)] px-4 py-2 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  red flags · severity ranked
                </div>
                <ul className="divide-y divide-[var(--cv-border)]">
                  {[
                    ["high", "Customer concentration — top 2 = 61% revenue", "p.14"],
                    ["high", "Operating cash flow declining vs revenue growth", "p.22"],
                    ["medium", "$4.2M off-balance lease obligations undisclosed in MD&A", "p.31"],
                    ["medium", "Related-party loan with founder — no covenants", "p.44"],
                    ["low", "Auditor changed (year 2 of 3) — Big-4 → mid-tier", "p.03"],
                  ].map(([sev, title, page], i) => (
                    <li key={i} className="flex items-start gap-3 px-4 py-3">
                      <span
                        className={`cv-chip ${
                          sev === "high"
                            ? "cv-chip-red"
                            : sev === "medium"
                            ? "cv-chip-amber"
                            : ""
                        }`}
                      >
                        {sev}
                      </span>
                      <div className="flex-1">
                        <div className="font-body text-sm">{title}</div>
                        <div className="font-mono text-[11px] text-[var(--cv-muted)]">{page}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Security */}
      <section id="security" className="border-b border-[var(--cv-border)]">
        <div className="mx-auto grid max-w-[1400px] grid-cols-12 gap-8 px-8 py-24">
          <div className="col-span-12 md:col-span-5">
            <span className="cv-tag">// 02 SECURITY</span>
            <h2 className="mt-4 font-heading text-3xl font-bold tracking-tight md:text-5xl">
              Your deal room
              <br />
              <span className="text-[var(--cv-primary)]">never leaves the room.</span>
            </h2>
          </div>
          <div className="col-span-12 md:col-span-7 space-y-4">
            {[
              "Documents stored ephemerally — purged within 24 hours of extraction.",
              "SOC 2 Type II in progress · ISO 27001 roadmap · GDPR aligned.",
              "Zero training on your data. Never. We will sign anything that says it.",
              "On-prem deployment available on the Firm tier.",
            ].map((line) => (
              <div key={line} className="flex items-start gap-3 border-l border-[var(--cv-primary)] bg-[var(--cv-surface)] px-4 py-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--cv-primary)]" />
                <p className="font-body text-sm text-[var(--cv-text)]">{line}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-b border-[var(--cv-border)]">
        <div className="mx-auto max-w-[1400px] px-8 py-24">
          <div className="mb-12 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <span className="cv-tag">// 03 PRICING</span>
              <h2 className="mt-4 font-heading text-3xl font-bold tracking-tight md:text-5xl">
                Priced for boutiques.
              </h2>
            </div>
            <p className="max-w-md font-body text-[var(--cv-muted)]">
              No enterprise sales cycle. No SOC review marathon. Card, swipe, ship.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-px border border-[var(--cv-border)] bg-[var(--cv-border)] md:grid-cols-3">
            {PRICING.map((p) => (
              <div
                key={p.key}
                data-testid={LANDING.pricingCard(p.key)}
                className={`flex flex-col bg-[var(--cv-bg)] p-8 ${
                  p.accent ? "ring-1 ring-[var(--cv-primary)]" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-mono text-sm uppercase tracking-widest text-[var(--cv-muted)]">
                    {p.name}
                  </h3>
                  {p.accent && <span className="cv-chip cv-chip-amber">Most picked</span>}
                </div>
                <div className="mt-6 flex items-end gap-2">
                  <div className="font-heading text-5xl font-bold tracking-tight">{p.price}</div>
                  <div className="pb-2 font-mono text-xs text-[var(--cv-muted)]">{p.period}</div>
                </div>
                <p className="mt-3 font-body text-sm text-[var(--cv-muted)]">{p.blurb}</p>
                <ul className="mt-6 flex-1 space-y-2">
                  {p.perks.map((perk) => (
                    <li key={perk} className="flex items-start gap-2 font-body text-sm">
                      <span className="mt-1 inline-block h-1 w-1 bg-[var(--cv-primary)]" />
                      {perk}
                    </li>
                  ))}
                </ul>
                <Link
                  to="/signup"
                  data-testid={LANDING.pricingCta(p.key)}
                  className={`mt-8 inline-flex items-center justify-center gap-2 px-4 py-3 font-mono text-xs uppercase tracking-widest ${
                    p.accent
                      ? "bg-[var(--cv-primary)] text-black hover:bg-[var(--cv-primary-hover)]"
                      : "border border-[var(--cv-border)] text-[var(--cv-text)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
                  }`}
                >
                  {p.cta} <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-[var(--cv-bg)]">
        <div className="mx-auto flex max-w-[1400px] flex-col items-start justify-between gap-6 px-8 py-10 md:flex-row md:items-center">
          <div className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center border border-[var(--cv-primary)] bg-[var(--cv-primary)] text-black">
              <span className="font-mono text-sm font-bold">CV</span>
            </div>
            <span className="font-heading text-sm font-bold tracking-tight">
              CLEAR<span className="text-[var(--cv-primary)]">VAULT</span>
            </span>
            <span className="font-mono text-[11px] text-[var(--cv-muted)]">
              © 2026 · Made for boutique M&A desks.
            </span>
          </div>
          <div className="font-mono text-[11px] text-[var(--cv-muted)]">
            status · all systems nominal <span className="text-[var(--cv-success)]">●</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
