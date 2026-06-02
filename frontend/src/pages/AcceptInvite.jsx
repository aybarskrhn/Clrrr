import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { ArrowRight, Loader2, AlertOctagon, UserPlus, CheckCircle2 } from "lucide-react";

export default function AcceptInvite() {
  const { token } = useParams();
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [err, setErr] = useState(null);
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    api
      .get(`/invites/${token}`)
      .then(({ data }) => setInvite(data))
      .catch((e) => setErr(e?.response?.data?.detail || "Invite not found"));
  }, [token]);

  const accept = async () => {
    if (!user) {
      navigate(`/signup?invite=${token}&email=${encodeURIComponent(invite?.email || "")}`);
      return;
    }
    setAccepting(true);
    try {
      const { data } = await api.post(`/invites/${token}/accept`);
      await refresh();
      toast.success(`Joined ${data.joined_org_name}.`);
      navigate("/dashboard");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Accept failed");
    } finally {
      setAccepting(false);
    }
  };

  if (err) {
    return (
      <Shell>
        <div className="flex items-center gap-2 text-[var(--cv-danger)]">
          <AlertOctagon className="h-5 w-5" />
          <span className="font-mono text-[11px] uppercase tracking-widest">Invite unavailable</span>
        </div>
        <h1 className="mt-3 font-heading text-3xl font-bold tracking-tight">{err}</h1>
        <p className="mt-3 font-body text-sm text-[var(--cv-muted)]">
          The link may have been revoked, already accepted, or never existed.
        </p>
        <Link
          to="/"
          className="mt-6 inline-flex items-center gap-2 border border-[var(--cv-border)] px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
        >
          ← back to clearvault
        </Link>
      </Shell>
    );
  }

  if (!invite) {
    return (
      <Shell>
        <div className="flex items-center gap-2 font-mono text-sm text-[var(--cv-muted)]">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading invite…
        </div>
      </Shell>
    );
  }

  const emailMismatch = user && user.email !== invite.email;

  return (
    <Shell>
      <div className="cv-tag">// INVITE</div>
      <h1 className="mt-3 font-heading text-3xl font-bold tracking-tight md:text-5xl">
        Join <span className="text-[var(--cv-primary)]">{invite.org_name}</span>
      </h1>
      <p className="mt-4 font-body text-base text-[var(--cv-muted)]">
        <span className="text-[var(--cv-text)]">{invite.invited_by}</span> invited you to the
        workspace as a{" "}
        <span className="text-[var(--cv-text)]">{invite.role}</span>. You'll get access to every
        deal, document and red-flag in the workspace.
      </p>

      <div className="mt-8 border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5">
        <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
          Invite details
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-3 font-mono text-xs">
          <dt className="text-[var(--cv-muted)]">Workspace</dt>
          <dd className="text-[var(--cv-text)]">{invite.org_name}</dd>
          <dt className="text-[var(--cv-muted)]">Invited email</dt>
          <dd className="text-[var(--cv-text)]">{invite.email}</dd>
          <dt className="text-[var(--cv-muted)]">Role</dt>
          <dd className="text-[var(--cv-text)]">{invite.role}</dd>
        </dl>
      </div>

      {emailMismatch && (
        <div className="mt-4 border border-[var(--cv-danger)]/60 bg-[var(--cv-surface)] p-4 font-mono text-xs text-[var(--cv-danger)]">
          You're signed in as {user.email}, but this invite is for {invite.email}. Log out and sign
          up with the invited address.
        </div>
      )}

      <button
        onClick={accept}
        disabled={accepting || emailMismatch}
        data-testid="invite-accept-btn"
        className="mt-8 inline-flex items-center gap-2 bg-[var(--cv-primary)] px-5 py-3 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)] disabled:opacity-50"
      >
        {accepting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
        {user ? "Accept invite" : "Create account & accept"} <ArrowRight className="h-4 w-4" />
      </button>

      <p className="mt-4 font-mono text-[11px] text-[var(--cv-muted)]">
        <CheckCircle2 className="mr-1 inline h-3 w-3 text-[var(--cv-primary)]" />
        You can switch back to your personal workspace anytime from the Team page.
      </p>
    </Shell>
  );
}

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-[var(--cv-bg)] text-[var(--cv-text)] cv-grid-bg">
      <div className="cv-scanlines absolute inset-0 pointer-events-none" />
      <div className="relative mx-auto max-w-2xl px-6 py-16">
        <Link to="/" className="flex w-fit items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center border border-[var(--cv-primary)] bg-[var(--cv-primary)] text-black">
            <span className="font-mono text-sm font-bold">CV</span>
          </div>
          <span className="font-heading text-base font-bold tracking-tight">
            CLEAR<span className="text-[var(--cv-primary)]">VAULT</span>
          </span>
        </Link>
        <div className="mt-10 border border-[var(--cv-border)] bg-[var(--cv-surface)] p-8">{children}</div>
      </div>
    </div>
  );
}
