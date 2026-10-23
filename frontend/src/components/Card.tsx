import type { ReactNode } from "react";

interface CardProps {
  id: string;
  n: number;
  title: string;
  hint?: string;
  children: ReactNode;
  collapse?: { collapsed: boolean; summary: string; showLabel: string; onToggle: () => void };
}

export function Card({ id, n, title, hint, children, collapse }: CardProps) {
  const collapsed = collapse?.collapsed ?? false;
  return (
    <section className={`card${collapsed ? " collapsed" : ""}`} id={`step-${id}`} aria-labelledby={`h-${id}`}>
      <div className="card-head">
        <span className="badge" aria-hidden>
          {n}
        </span>
        <div className="grow">
          <h2 id={`h-${id}`}>{title}</h2>
          {(collapsed ? collapse?.summary : hint) && <p>{collapsed ? collapse?.summary : hint}</p>}
        </div>
        {collapse && (
          <button className={`${collapsed ? "" : "ghost "}sm head-action`} onClick={collapse.onToggle} aria-expanded={!collapsed} aria-controls={`body-${id}`}>
            {collapsed ? collapse.showLabel : "Hide"}
          </button>
        )}
      </div>
      {!collapsed && <div id={`body-${id}`}>{children}</div>}
    </section>
  );
}

export function Stat({ label, value, unit, note, attn }: { label: string; value: ReactNode; unit?: string; note?: string; attn?: boolean }) {
  return (
    <div className={`stat${attn ? " attn" : ""}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">
        {value}
        {unit && <small> {unit}</small>}
      </span>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

export const goTo = (id: string) => document.getElementById(`step-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
