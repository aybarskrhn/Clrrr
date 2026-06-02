import { Link, NavLink, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { NAV } from "@/constants/testIds";
import { LogOut, LayoutDashboard, FolderKanban, UploadCloud, Search, Settings as Cog } from "lucide-react";
import TickerBar from "@/components/TickerBar";
import CommandPalette from "@/components/CommandPalette";

export default function AppLayout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [cmdOpen, setCmdOpen] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const navItem = ({ isActive }) =>
    `flex items-center gap-2 px-3 py-2 text-xs font-mono uppercase tracking-wider border-l-2 ${
      isActive
        ? "border-[var(--cv-primary)] bg-[var(--cv-surface)] text-[var(--cv-text)]"
        : "border-transparent text-[var(--cv-muted)] hover:text-[var(--cv-text)] hover:bg-[var(--cv-surface)]"
    }`;

  return (
    <div className="min-h-screen bg-[var(--cv-bg)] text-[var(--cv-text)]">
      <header className="border-b border-[var(--cv-border)] bg-[var(--cv-bg)]">
        <div className="flex items-center justify-between px-6 py-3">
          <Link to="/dashboard" data-testid={NAV.brand} className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center border border-[var(--cv-primary)] bg-[var(--cv-primary)] text-black">
              <span className="font-mono text-sm font-bold">CV</span>
            </div>
            <div className="font-heading text-base font-bold tracking-tight">
              CLEAR<span className="text-[var(--cv-primary)]">VAULT</span>
            </div>
            <span className="cv-chip cv-chip-amber ml-2">M&A · LIVE</span>
          </Link>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setCmdOpen(true)}
              data-testid="nav-search-btn"
              className="hidden items-center gap-2 border border-[var(--cv-border)] px-3 py-1.5 font-mono text-xs text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)] md:flex"
            >
              <Search className="h-3.5 w-3.5" />
              search…
              <span className="ml-2 border border-[var(--cv-border)] px-1.5 py-0.5 text-[10px]">⌘K</span>
            </button>
            <span className="hidden font-mono text-xs text-[var(--cv-muted)] lg:block">
              {user?.firm ? `${user.firm} · ` : ""}
              {user?.email}
            </span>
            <button
              onClick={() => {
                logout();
                navigate("/");
              }}
              data-testid={NAV.logoutBtn}
              className="flex items-center gap-2 border border-[var(--cv-border)] px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
            >
              <LogOut className="h-3.5 w-3.5" />
              Logout
            </button>
          </div>
        </div>
        <TickerBar />
      </header>

      <div className="flex">
        <aside className="hidden w-56 shrink-0 border-r border-[var(--cv-border)] md:block">
          <div className="px-4 pt-6 pb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--cv-muted)]">
            Workspace
          </div>
          <nav className="flex flex-col">
            <NavLink to="/dashboard" className={navItem} data-testid={NAV.dashboardLink}>
              <LayoutDashboard className="h-3.5 w-3.5" /> Overview
            </NavLink>
            <NavLink to="/deals" className={navItem} data-testid={NAV.dealsLink}>
              <FolderKanban className="h-3.5 w-3.5" /> Deals
            </NavLink>
            <NavLink to="/upload" className={navItem} data-testid={NAV.uploadLink}>
              <UploadCloud className="h-3.5 w-3.5" /> Ingest PDF
            </NavLink>
            <NavLink to="/settings" className={navItem} data-testid="nav-settings-link">
              <Cog className="h-3.5 w-3.5" /> Settings
            </NavLink>
          </nav>
          <div className="px-4 pt-8 pb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--cv-muted)]">
            Reference
          </div>
          <div className="px-4 font-mono text-[11px] leading-relaxed text-[var(--cv-muted)]">
            <p className="mb-2">Local processing · No public AI exposure.</p>
            <p className="mb-2">Models: Gemini 3 · Plex Mono · Bloomberg-grade rigor.</p>
            <p className="mt-3 text-[var(--cv-muted)]">
              ⌘K — global search
            </p>
          </div>
        </aside>

        <main className="flex-1 min-w-0">{children}</main>
      </div>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </div>
  );
}
