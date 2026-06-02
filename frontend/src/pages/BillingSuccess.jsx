import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import AppLayout from "@/components/AppLayout";
import { useAuth } from "@/context/AuthContext";
import { CheckCircle2, Loader2, AlertOctagon } from "lucide-react";

const MAX_POLLS = 12;
const INTERVAL_MS = 2000;

export default function BillingSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState({ state: "pending", payment_status: null, plan: null });
  const [attempts, setAttempts] = useState(0);
  const { refresh } = useAuth();

  useEffect(() => {
    if (!sessionId) {
      setStatus({ state: "error", payment_status: null });
      return;
    }
    let cancelled = false;

    const poll = async (n) => {
      if (cancelled) return;
      if (n >= MAX_POLLS) {
        setStatus((s) => ({ ...s, state: "timeout" }));
        return;
      }
      try {
        const { data } = await api.get(`/payments/checkout/status/${sessionId}`);
        setAttempts(n + 1);
        if (data.payment_status === "paid") {
          setStatus({ state: "paid", payment_status: "paid", plan: data.plan });
          await refresh();
          return;
        }
        if (data.status === "expired") {
          setStatus({ state: "expired", payment_status: data.payment_status });
          return;
        }
        setTimeout(() => poll(n + 1), INTERVAL_MS);
      } catch (e) {
        setTimeout(() => poll(n + 1), INTERVAL_MS);
      }
    };

    poll(0);
    return () => {
      cancelled = true;
    };
  }, [sessionId, refresh]);

  return (
    <AppLayout>
      <div data-testid="billing-success-root" className="mx-auto max-w-2xl px-6 py-16">
        <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-8">
          {status.state === "pending" && (
            <>
              <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
                <Loader2 className="h-4 w-4 animate-spin" /> Verifying payment…
              </div>
              <h1 className="mt-3 font-heading text-3xl font-bold tracking-tight">
                One moment.
              </h1>
              <p className="mt-3 font-body text-sm text-[var(--cv-muted)]">
                Polling Stripe for confirmation. We won't credit your account until payment is
                cleared. Attempt {attempts}/{MAX_POLLS}.
              </p>
            </>
          )}

          {status.state === "paid" && (
            <>
              <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-success)]">
                <CheckCircle2 className="h-4 w-4" /> Payment confirmed
              </div>
              <h1 className="mt-3 font-heading text-3xl font-bold tracking-tight">
                Welcome to the <span className="text-[var(--cv-primary)]">Desk</span> tier.
              </h1>
              <p className="mt-3 font-body text-sm text-[var(--cv-muted)]">
                Unlimited deals, unlimited extractions, IC roll-ups, exports, Slack notifications,
                red-flag audit trail.
              </p>
              <Link
                to="/dashboard"
                data-testid="billing-success-back"
                className="mt-8 inline-flex items-center gap-2 bg-[var(--cv-primary)] px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)]"
              >
                Return to terminal →
              </Link>
            </>
          )}

          {(status.state === "expired" || status.state === "error") && (
            <>
              <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-danger)]">
                <AlertOctagon className="h-4 w-4" /> Payment not completed
              </div>
              <h1 className="mt-3 font-heading text-2xl font-bold tracking-tight">
                Session {status.state === "expired" ? "expired" : "missing"}.
              </h1>
              <Link
                to="/settings"
                className="mt-6 inline-flex items-center gap-2 border border-[var(--cv-border)] px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
              >
                ← Try again
              </Link>
            </>
          )}

          {status.state === "timeout" && (
            <>
              <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                <Loader2 className="h-4 w-4" /> Taking longer than expected
              </div>
              <h1 className="mt-3 font-heading text-2xl font-bold tracking-tight">
                Still pending.
              </h1>
              <p className="mt-3 font-body text-sm text-[var(--cv-muted)]">
                Stripe hasn't confirmed within our polling window. Refresh in a minute — your plan
                will switch over automatically once payment clears.
              </p>
              <Link
                to="/dashboard"
                className="mt-6 inline-flex items-center gap-2 border border-[var(--cv-border)] px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
              >
                ← Back to terminal
              </Link>
            </>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
