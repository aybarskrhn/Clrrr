import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import AppLayout from "@/components/AppLayout";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  Users,
  UserPlus,
  Copy,
  Loader2,
  Crown,
  Shield,
  Trash2,
  X,
  ArrowRightLeft,
  Mail,
} from "lucide-react";

export default function Team() {
  const { user, refresh } = useAuth();
  const [org, setOrg] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [invitingEmail, setInvitingEmail] = useState("");
  const [invitingRole, setInvitingRole] = useState("member");
  const [issuing, setIssuing] = useState(false);
  const [lastInvite, setLastInvite] = useState(null);
  const [editingName, setEditingName] = useState(false);
  const [orgName, setOrgName] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, all] = await Promise.all([
        api.get("/orgs/current"),
        api.get("/orgs/me/orgs"),
      ]);
      setOrg(c.data);
      setOrgName(c.data?.name || "");
      setOrgs(all.data?.orgs || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const isOwner = org?.my_role === "owner";
  const isAdmin = org?.my_role === "owner" || org?.my_role === "admin";

  const invite = async (e) => {
    e?.preventDefault();
    if (!invitingEmail) return;
    setIssuing(true);
    try {
      const { data } = await api.post("/orgs/current/invites", {
        email: invitingEmail.trim(),
        role: invitingRole,
      });
      const link = `${window.location.origin}/invite/${data.token}`;
      setLastInvite({ ...data, link });
      toast.success("Invite link minted — share it with the teammate.");
      setInvitingEmail("");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Invite failed");
    } finally {
      setIssuing(false);
    }
  };

  const revokeInvite = async (id) => {
    if (!window.confirm("Revoke this invite?")) return;
    try {
      await api.delete(`/orgs/current/invites/${id}`);
      toast.success("Invite revoked.");
      load();
    } catch {
      toast.error("Revoke failed");
    }
  };

  const removeMember = async (uid) => {
    if (!window.confirm("Remove this teammate from the workspace?")) return;
    try {
      await api.delete(`/orgs/current/members/${uid}`);
      toast.success("Member removed.");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Remove failed");
    }
  };

  const changeRole = async (uid, role) => {
    try {
      await api.patch(`/orgs/current/members/${uid}`, { role });
      toast.success("Role updated.");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Update failed");
    }
  };

  const switchOrg = async (orgId) => {
    try {
      await api.post(`/orgs/switch/${orgId}`);
      await refresh();
      await load();
      toast.success("Switched workspace.");
    } catch (err) {
      toast.error("Switch failed");
    }
  };

  const saveName = async () => {
    if (!orgName.trim() || orgName === org?.name) {
      setEditingName(false);
      return;
    }
    try {
      const { data } = await api.patch("/orgs/current", { name: orgName.trim() });
      setOrg(data);
      setEditingName(false);
      toast.success("Workspace renamed.");
    } catch {
      toast.error("Rename failed");
    }
  };

  if (loading || !org) {
    return (
      <AppLayout>
        <div className="px-6 py-12 font-mono text-sm text-[var(--cv-muted)]">
          <Loader2 className="mr-2 inline h-4 w-4 animate-spin" /> loading team…
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div data-testid="team-root" className="px-6 py-6">
        <div className="border-b border-[var(--cv-border)] pb-5">
          <div className="cv-tag">// TEAM · {org.id.slice(0, 8).toUpperCase()}</div>
          <div className="mt-2 flex items-end gap-3">
            {editingName ? (
              <input
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                onBlur={saveName}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveName();
                  if (e.key === "Escape") {
                    setOrgName(org.name);
                    setEditingName(false);
                  }
                }}
                autoFocus
                data-testid="team-rename-input"
                className="border border-[var(--cv-primary)] bg-[var(--cv-bg)] px-3 py-1 font-heading text-3xl font-bold tracking-tight outline-none md:text-4xl"
              />
            ) : (
              <h1
                onClick={() => isAdmin && setEditingName(true)}
                title={isAdmin ? "Click to rename" : ""}
                className={`font-heading text-3xl font-bold tracking-tight md:text-4xl ${
                  isAdmin ? "cursor-pointer hover:text-[var(--cv-primary)]" : ""
                }`}
              >
                {org.name}
              </h1>
            )}
            <span className="cv-chip cv-chip-amber">{org.plan?.toUpperCase()}</span>
          </div>
          <p className="mt-2 font-mono text-xs text-[var(--cv-muted)]">
            You are <span className="text-[var(--cv-primary)]">{org.my_role}</span> · {org.members.length} member
            {org.members.length === 1 ? "" : "s"}
            {org.pending_invites.length > 0 && (
              <>
                {" · "}
                {org.pending_invites.length} pending invite{org.pending_invites.length === 1 ? "" : "s"}
              </>
            )}
          </p>
        </div>

        <div className="mt-6 grid grid-cols-12 gap-4">
          {/* Members */}
          <section className="col-span-12 border border-[var(--cv-border)] bg-[var(--cv-surface)] md:col-span-7">
            <div className="flex items-center justify-between border-b border-[var(--cv-border)] px-4 py-3">
              <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                <Users className="mr-2 inline h-3 w-3" /> Members
              </span>
              <span className="font-mono text-[10px] text-[var(--cv-muted)]">
                {org.members.length}
              </span>
            </div>
            <table className="w-full font-mono text-xs">
              <thead>
                <tr className="border-b border-[var(--cv-border)] text-left text-[var(--cv-muted)]">
                  <th className="px-4 py-2">Name</th>
                  <th className="px-4 py-2">Email</th>
                  <th className="px-4 py-2">Role</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {org.members.map((m) => {
                  const isMe = m.user_id === user?.id;
                  const isThisOwner = m.role === "owner";
                  return (
                    <tr key={m.user_id} data-testid={`team-member-${m.user_id}`} className="border-b border-[var(--cv-border)]/60">
                      <td className="px-4 py-3 text-[var(--cv-text)]">
                        {m.name}
                        {isMe && <span className="ml-2 cv-chip">you</span>}
                      </td>
                      <td className="px-4 py-3 text-[var(--cv-muted)]">{m.email}</td>
                      <td className="px-4 py-3">
                        <span className={`cv-chip ${isThisOwner ? "cv-chip-amber" : ""}`}>
                          {isThisOwner && <Crown className="h-3 w-3" />}
                          {m.role === "admin" && <Shield className="h-3 w-3" />}
                          {m.role}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {isOwner && !isThisOwner && !isMe && (
                          <div className="flex items-center justify-end gap-2">
                            <select
                              value={m.role}
                              onChange={(e) => changeRole(m.user_id, e.target.value)}
                              data-testid={`team-role-${m.user_id}`}
                              className="border border-[var(--cv-border)] bg-[var(--cv-bg)] px-2 py-1 text-[11px] outline-none focus:border-[var(--cv-primary)]"
                            >
                              <option value="member">member</option>
                              <option value="admin">admin</option>
                            </select>
                            <button
                              onClick={() => removeMember(m.user_id)}
                              data-testid={`team-remove-${m.user_id}`}
                              className="text-[var(--cv-muted)] hover:text-[var(--cv-danger)]"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {/* Invite + my orgs */}
          <aside className="col-span-12 space-y-4 md:col-span-5">
            {isAdmin && (
              <form
                onSubmit={invite}
                data-testid="team-invite-form"
                className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5"
              >
                <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  <UserPlus className="mr-2 inline h-3 w-3" /> Invite a teammate
                </div>
                <label className="mt-4 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Work email
                </label>
                <input
                  required
                  type="email"
                  value={invitingEmail}
                  onChange={(e) => setInvitingEmail(e.target.value)}
                  placeholder="jamie@boutiquecap.com"
                  data-testid="team-invite-email"
                  className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2 font-mono text-xs outline-none focus:border-[var(--cv-primary)]"
                />
                <label className="mt-3 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Role
                </label>
                <select
                  value={invitingRole}
                  onChange={(e) => setInvitingRole(e.target.value)}
                  data-testid="team-invite-role"
                  className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2 font-mono text-xs outline-none focus:border-[var(--cv-primary)]"
                >
                  <option value="member">member — can ingest & analyze</option>
                  <option value="admin">admin — also invites & removes</option>
                </select>
                <button
                  type="submit"
                  disabled={issuing}
                  data-testid="team-invite-submit"
                  className="mt-5 flex w-full items-center justify-center gap-2 bg-[var(--cv-primary)] px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)] disabled:opacity-60"
                >
                  {issuing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />}
                  Mint invite link
                </button>
                <p className="mt-3 font-mono text-[10px] text-[var(--cv-muted)]">
                  We don't email automatically — you copy the link and share it (Slack, email,
                  whatever). They sign up with that same email and join your workspace.
                </p>
              </form>
            )}

            {lastInvite && (
              <div
                data-testid="team-invite-result"
                className="border border-[var(--cv-primary)]/70 bg-[var(--cv-surface)] p-4"
              >
                <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
                  Invite link for {lastInvite.email}
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <input
                    readOnly
                    value={lastInvite.link}
                    data-testid="team-invite-link"
                    onFocus={(e) => e.target.select()}
                    className="flex-1 border border-[var(--cv-border)] bg-[var(--cv-bg)] px-2 py-1.5 font-mono text-[11px] text-[var(--cv-text)] outline-none"
                  />
                  <button
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(lastInvite.link);
                        toast.success("Copied.");
                      } catch {
                        toast.error("Couldn't copy.");
                      }
                    }}
                    data-testid="team-invite-copy"
                    className="border border-[var(--cv-border)] px-2 py-1.5 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
                  >
                    <Copy className="h-3 w-3" />
                  </button>
                </div>
              </div>
            )}

            {org.pending_invites.length > 0 && (
              <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
                <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Pending invites
                </div>
                <ul className="divide-y divide-[var(--cv-border)]/60">
                  {org.pending_invites.map((inv) => (
                    <li
                      key={inv.id}
                      data-testid={`team-pending-${inv.id}`}
                      className="flex items-center justify-between px-4 py-3"
                    >
                      <div>
                        <div className="font-body text-sm text-[var(--cv-text)]">{inv.email}</div>
                        <div className="font-mono text-[10px] text-[var(--cv-muted)]">
                          {inv.role} · {inv.created_at?.slice(0, 10)}
                        </div>
                      </div>
                      {isAdmin && (
                        <button
                          onClick={() => revokeInvite(inv.id)}
                          className="text-[var(--cv-muted)] hover:text-[var(--cv-danger)]"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {orgs.length > 1 && (
              <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
                <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  <ArrowRightLeft className="mr-2 inline h-3 w-3" /> Switch workspace
                </div>
                <ul className="divide-y divide-[var(--cv-border)]/60">
                  {orgs.map((o) => {
                    const active = o.id === org.id;
                    return (
                      <li key={o.id}>
                        <button
                          onClick={() => !active && switchOrg(o.id)}
                          disabled={active}
                          data-testid={`team-switch-${o.id}`}
                          className={`flex w-full items-center justify-between px-4 py-3 text-left ${
                            active
                              ? "bg-[var(--cv-surface-hover)]"
                              : "hover:bg-[var(--cv-surface-hover)]"
                          }`}
                        >
                          <div>
                            <div className="font-body text-sm">{o.name}</div>
                            <div className="font-mono text-[10px] text-[var(--cv-muted)]">{o.role}</div>
                          </div>
                          {active && <span className="cv-chip cv-chip-amber">active</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </aside>
        </div>
      </div>
    </AppLayout>
  );
}
