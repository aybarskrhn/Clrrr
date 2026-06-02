import { Link } from "react-router-dom";
import AppLayout from "@/components/AppLayout";
import { ArrowLeft } from "lucide-react";

export default function BillingCancel() {
  return (
    <AppLayout>
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-8">
          <div className="cv-tag">// CHECKOUT CANCELED</div>
          <h1 className="mt-3 font-heading text-3xl font-bold tracking-tight">
            No charge, no plan change.
          </h1>
          <p className="mt-3 font-body text-sm text-[var(--cv-muted)]">
            You're still on the trial. Come back whenever you're ready to lock in the Desk tier.
          </p>
          <Link
            to="/settings"
            data-testid="billing-cancel-back"
            className="mt-6 inline-flex items-center gap-2 border border-[var(--cv-border)] px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> back to billing
          </Link>
        </div>
      </div>
    </AppLayout>
  );
}
