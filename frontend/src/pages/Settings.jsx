import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppLayout from "@/components/AppLayout";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Loader2, ArrowRight, ShieldCheck, MessageSquare, CreditCard, CheckCircle2 } from "lucide-react";

export default function Settings() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", firm: "", slack_webhook_url: "" });
  const [saving, setSaving] = useState(false);
  const [packages, setPackages] = useState([]);
  const [upgrading, setUpgrading] = useState(false);

  useEffect(() => {
    if (user) {
      setForm({
        name: user.name || "",
        firm: user.firm || "",
        slack_webhook_url: user.slack_webhook_url || "",
      });
    }
  }, [user]);

  useEffect(() => {
    api.get("/payments/packages").then(({ data }) => setPackages(data.packages));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.patch("/auth/settings", form);
      await refresh();
      toast.success("Settings saved.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const upgrade = async (pkgId) => {
    setUpgrading(true);
    try {
      const { data } = await api.post("/payments/checkout/session", {
        package_id: pkgId,
        origin_url: window.location.origin,
      });
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Checkout failed");
      setUpgrading(false);
    }
  };

  return (
    <AppLayout>
      <div data-testid="settings-root" className="px-6 py-6">
        <div className="border-b border-[var(--cv-border)] pb-5">
          <div className="cv-tag">// SETTINGS</div>
          <h1 className="mt-2 font-heading text-3xl font-bold tracking-tight md:text-4xl">
            Terminal preferences
          </h1>
          <p className="mt-2 font-mono text-xs text-[var(--cv-muted)]">
            Plan ·{" "}
            <span className="text-[var(--cv-primary)]">{user?.plan?.toUpperCase() || "TRIAL"}</span>
            {user?.plan_active_until && (
              <>
                {" · "}active until{" "}
                <span className="text-[var(--cv-text)]">
                  {user.plan_active_until.slice(0, 10)}
                </span>
              </>
            )}
          </p>
        </div>

        <div className="mt-6 grid grid-cols-12 gap-4">
          {/* Profile + Slack */}
          <div className="col-span-12 border border-[var(--cv-border)] bg-[var(--cv-surface)] md:col-span-7">
            <div className="border-b border-[var(--cv-border)] px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Profile
            </div>
            <div className="grid grid-cols-2 gap-4 p-5">
              <div>
                <label className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Full name
                </label>
                <input
                  data-testid="settings-name-input"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
                />
              </div>
              <div>
                <label className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Firm
                </label>
                <input
                  data-testid="settings-firm-input"
                  value={form.firm}
                  onChange={(e) => setForm({ ...form, firm: e.target.value })}
                  className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
                />
              </div>
            </div>

            <div className="border-t border-[var(--cv-border)] px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              <MessageSquare className="mr-2 inline h-3 w-3" /> Slack notifications
            </div>
            <div className="p-5">
              <p className="font-body text-sm text-[var(--cv-muted)]">
                Paste a Slack incoming webhook URL — we'll ping that channel each time an extraction
                finishes, with the doc, summary, and top red flags.
              </p>
              <label className="mt-4 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Webhook URL
              </label>
              <input
                data-testid="settings-slack-input"
                value={form.slack_webhook_url}
                onChange={(e) => setForm({ ...form, slack_webhook_url: e.target.value })}
                placeholder="https://hooks.slack.com/services/T000/B000/xxxxx"
                className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-xs outline-none focus:border-[var(--cv-primary)]"
              />
              <p className="mt-2 font-mono text-[10px] text-[var(--cv-muted)]">
                Generate one at{" "}
                <a
                  className="text-[var(--cv-primary)] hover:underline"
                  href="https://api.slack.com/messaging/webhooks"
                  target="_blank"
                  rel="noreferrer"
                >
                  api.slack.com/messaging/webhooks
                </a>{" "}
                · we only POST, never read.
              </p>

              <button
                onClick={save}
                disabled={saving}
                data-testid="settings-save-btn"
                className="mt-6 flex items-center gap-2 bg-[var(--cv-primary)] px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)] disabled:opacity-60"
              >
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                Save changes
              </button>
            </div>
          </div>

          {/* Billing */}
          <div className="col-span-12 border border-[var(--cv-border)] bg-[var(--cv-surface)] md:col-span-5">
            <div className="border-b border-[var(--cv-border)] px-5 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              <CreditCard className="mr-2 inline h-3 w-3" /> Billing
            </div>
            <div className="p-5">
              {user?.plan === "desk" ? (
                <div className="border border-[var(--cv-primary)] bg-[var(--cv-bg)] px-4 py-3">
                  <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
                    <ShieldCheck className="h-3.5 w-3.5" /> Desk plan active
                  </div>
                  <p className="mt-2 font-body text-sm text-[var(--cv-muted)]">
                    Unlimited deals · unlimited extractions · red-flag audit trail.
                  </p>
                </div>
              ) : (
                <>
                  <p className="font-body text-sm text-[var(--cv-muted)]">
                    You're on the free trial. Upgrade to <span className="text-[var(--cv-text)]">Desk</span> for
                    unlimited deals, unlimited extractions, Excel exports, and the red-flag audit
                    trail.
                  </p>
                  <div className="mt-5 space-y-2">
                    {packages.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => upgrade(p.id)}
                        disabled={upgrading}
                        data-testid={`settings-upgrade-${p.id}`}
                        className="group flex w-full items-center justify-between border border-[var(--cv-border)] bg-[var(--cv-bg)] px-4 py-3 text-left hover:border-[var(--cv-primary)]"
                      >
                        <div>
                          <div className="font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] group-hover:text-[var(--cv-primary)]">
                            {p.label}
                          </div>
                          <div className="mt-1 font-heading text-2xl font-bold tracking-tight">
                            ${p.amount.toLocaleString()}{" "}
                            <span className="font-mono text-[11px] text-[var(--cv-muted)]">
                              {p.currency.toUpperCase()}
                            </span>
                          </div>
                        </div>
                        {upgrading ? (
                          <Loader2 className="h-4 w-4 animate-spin text-[var(--cv-primary)]" />
                        ) : (
                          <ArrowRight className="h-4 w-4 text-[var(--cv-primary)]" />
                        )}
                      </button>
                    ))}
                  </div>
                  <p className="mt-3 font-mono text-[10px] text-[var(--cv-muted)]">
                    Powered by Stripe · test mode · no real charges.
                  </p>
                </>
              )}
              <button
                onClick={() => navigate("/dashboard")}
                className="mt-5 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)] hover:text-[var(--cv-primary)]"
              >
                ← back to terminal
              </button>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
