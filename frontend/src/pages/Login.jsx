import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { AUTH, NAV } from "@/constants/testIds";
import { toast } from "sonner";
import { ArrowRight, Loader2 } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Terminal access granted.");
      navigate("/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--cv-bg)] text-[var(--cv-text)] cv-grid-bg">
      <div className="cv-scanlines absolute inset-0 pointer-events-none" />
      <div className="relative mx-auto flex max-w-[1100px] flex-col px-8 py-10">
        <Link to="/" data-testid={NAV.brand} className="flex w-fit items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center border border-[var(--cv-primary)] bg-[var(--cv-primary)] text-black">
            <span className="font-mono text-sm font-bold">CV</span>
          </div>
          <span className="font-heading text-base font-bold tracking-tight">
            CLEAR<span className="text-[var(--cv-primary)]">VAULT</span>
          </span>
        </Link>

        <div className="mt-16 grid grid-cols-12 gap-8">
          <div className="col-span-12 md:col-span-6">
            <span className="cv-tag">// AUTH · TERMINAL ACCESS</span>
            <h1 className="mt-4 font-heading text-4xl font-bold tracking-tight md:text-5xl">
              Sign back into the desk.<span className="cv-cursor" />
            </h1>
            <p className="mt-6 max-w-md font-body text-[var(--cv-muted)]">
              Pick up where you left off — every deal, document, and red flag are exactly where you
              parked them.
            </p>
            <div className="mt-12 border border-[var(--cv-border)] bg-[var(--cv-surface)] p-4">
              <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                $ session-log
              </div>
              <pre className="mt-2 font-mono text-[11px] leading-relaxed text-[var(--cv-muted)]">{`> last login          14m ago
> active deals        3
> pending extractions 1
> red flags surfaced  17`}</pre>
            </div>
          </div>

          <div className="col-span-12 md:col-span-6">
            <form
              onSubmit={submit}
              data-testid={AUTH.loginForm}
              className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-8"
            >
              <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
                Sign in
              </div>
              <h2 className="mt-2 font-heading text-2xl font-bold tracking-tight">Welcome back.</h2>

              <label className="mt-8 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Email
              </label>
              <input
                type="email"
                required
                value={email}
                data-testid={AUTH.loginEmail}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="analyst@boutiquebank.com"
                className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm text-[var(--cv-text)] outline-none focus:border-[var(--cv-primary)]"
              />

              <label className="mt-5 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                data-testid={AUTH.loginPassword}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm text-[var(--cv-text)] outline-none focus:border-[var(--cv-primary)]"
              />

              <button
                type="submit"
                disabled={loading}
                data-testid={AUTH.loginSubmit}
                className="mt-8 flex w-full items-center justify-center gap-2 bg-[var(--cv-primary)] px-4 py-3 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)] disabled:opacity-60"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                Authenticate
              </button>

              <p className="mt-6 font-mono text-[11px] text-[var(--cv-muted)]">
                No terminal yet?{" "}
                <Link to="/signup" className="text-[var(--cv-primary)] hover:underline">
                  Request access →
                </Link>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
