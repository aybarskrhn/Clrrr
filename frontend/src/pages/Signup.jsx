import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { AUTH, NAV } from "@/constants/testIds";
import { toast } from "sonner";
import { ArrowRight, Loader2 } from "lucide-react";

export default function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next");
  const inviteToken = params.get("invite");
  const inviteEmail = params.get("email");
  const [form, setForm] = useState({
    name: "",
    firm: "",
    email: inviteEmail || "",
    password: "",
  });
  const [loading, setLoading] = useState(false);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await signup(form);
      toast.success("Terminal provisioned.");

      // If signing up via an invite link, accept it
      if (inviteToken) {
        try {
          await api.post(`/invites/${inviteToken}/accept`);
          toast.success("Joined workspace.");
        } catch (err) {
          // non-fatal — they can accept from /invite/:token later
        }
        navigate("/dashboard");
        return;
      }

      if (next === "upgrade") {
        try {
          const { data } = await api.post("/payments/checkout/session", {
            package_id: "desk_monthly",
            origin_url: window.location.origin,
          });
          window.location.href = data.url;
          return;
        } catch (err) {
          toast.error("Couldn't redirect to checkout — open Settings to try again.");
        }
      }
      navigate("/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Signup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--cv-bg)] text-[var(--cv-text)] cv-grid-bg">
      <div className="cv-scanlines absolute inset-0 pointer-events-none" />
      <div className="relative mx-auto max-w-[1100px] px-8 py-10">
        <Link to="/" data-testid={NAV.brand} className="flex w-fit items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center border border-[var(--cv-primary)] bg-[var(--cv-primary)] text-black">
            <span className="font-mono text-sm font-bold">CV</span>
          </div>
          <span className="font-heading text-base font-bold tracking-tight">
            CLEAR<span className="text-[var(--cv-primary)]">VAULT</span>
          </span>
        </Link>

        <div className="mt-14 grid grid-cols-12 gap-8">
          <div className="col-span-12 md:col-span-5">
            <span className="cv-tag">// AUTH · NEW DESK</span>
            <h1 className="mt-4 font-heading text-4xl font-bold tracking-tight md:text-5xl">
              Provision a terminal.<span className="cv-cursor" />
            </h1>
            <p className="mt-6 max-w-md font-body text-[var(--cv-muted)]">
              14-day trial. No credit card. No InfoSec review. Drop your first PDF in under 60
              seconds.
            </p>

            <ul className="mt-10 space-y-3 font-mono text-[12px] text-[var(--cv-muted)]">
              <li>→ Drag-drop ingestion</li>
              <li>→ Structured financials in &lt;90s</li>
              <li>→ Severity-ranked red flags</li>
              <li>→ Excel-ready exports</li>
            </ul>
          </div>

          <div className="col-span-12 md:col-span-7">
            <form
              onSubmit={submit}
              data-testid={AUTH.signupForm}
              className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-8"
            >
              <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
                Create account
              </div>
              <h2 className="mt-2 font-heading text-2xl font-bold tracking-tight">
                Open your ClearVault terminal.
              </h2>

              <div className="mt-8 grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                    Full name
                  </label>
                  <input
                    required
                    data-testid={AUTH.signupName}
                    value={form.name}
                    onChange={onChange("name")}
                    placeholder="Sarah Chen"
                    className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
                  />
                </div>
                <div>
                  <label className="block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                    Firm
                  </label>
                  <input
                    data-testid={AUTH.signupFirm}
                    value={form.firm}
                    onChange={onChange("firm")}
                    placeholder="Boutique Capital LLP"
                    className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
                  />
                </div>
              </div>

              <label className="mt-5 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Work email
              </label>
              <input
                required
                type="email"
                data-testid={AUTH.signupEmail}
                value={form.email}
                onChange={onChange("email")}
                placeholder="schen@boutiquecap.com"
                className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
              />

              <label className="mt-5 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Password
              </label>
              <input
                required
                type="password"
                minLength={6}
                data-testid={AUTH.signupPassword}
                value={form.password}
                onChange={onChange("password")}
                placeholder="at least 6 characters"
                className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
              />

              <button
                type="submit"
                disabled={loading}
                data-testid={AUTH.signupSubmit}
                className="mt-8 flex w-full items-center justify-center gap-2 bg-[var(--cv-primary)] px-4 py-3 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)] disabled:opacity-60"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                Provision terminal
              </button>

              <p className="mt-6 font-mono text-[11px] text-[var(--cv-muted)]">
                Existing user?{" "}
                <Link to="/login" className="text-[var(--cv-primary)] hover:underline">
                  Sign in →
                </Link>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
