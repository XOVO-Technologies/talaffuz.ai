import { useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { capacityOf, formatDuration, isGood, needsLook } from "../format";
import type { ExportReport, Project } from "../types";
import { ProgressBar } from "./ProgressBar";

type Tone = "ok" | "todo" | "wait";

function Item({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <li>
      <span className={`tick ${tone}`} aria-hidden>
        {tone === "ok" ? "✓" : tone === "todo" ? "!" : "i"}
      </span>
      <span>{children}</span>
    </li>
  );
}

export function ExportPanel({ project, onDone, onError }: { project: Project; onDone: () => void; onError: (m: string) => void }) {
  const [busy, setBusy] = useState(false);
  const report: ExportReport | null = project.last_export;
  const cap = capacityOf(project.settings);

  // Only the first `cap` good clips (in recording order) end up in the dataset. With no cap, all of them do.
  const included = useMemo(
    () =>
      project.clips
        .filter(isGood)
        .sort((a, b) => a.order - b.order)
        .slice(0, cap ?? undefined),
    [project.clips, cap],
  );
  const total = project.clips.filter(isGood).length;
  const missingRoman = included.filter((c) => !c.roman.trim()).length;
  const flagged = included.filter(needsLook).length;

  async function run(force: boolean) {
    setBusy(true);
    try {
      await api.exportDataset(project.id, force);
      onDone();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {cap !== null && <ProgressBar value={cap > 0 ? included.length / cap : 0} label="Clips ready for export" thick />}
      <ul className="checklist" style={{ marginTop: cap === null ? 0 : 14 }}>
        {cap === null ? (
          <Item tone={included.length > 0 ? "ok" : "todo"}>
            <strong>{included.length}</strong> clips ready. Every kept clip is exported, numbered from your first file number.
          </Item>
        ) : (
          <Item tone={included.length >= cap ? "ok" : "todo"}>
            <strong>
              {included.length} of {cap}
            </strong>{" "}
            clips ready
            {total > cap && ` (${total - cap} extra will be left out)`}
            {included.length < cap && ". Process more clips, or lower the last file number in Settings."}
          </Item>
        )}
        <Item tone={missingRoman === 0 && included.length > 0 ? "ok" : "todo"}>
          {missingRoman === 0 ? (
            "Every clip has Roman Urdu."
          ) : (
            <>
              <strong>{missingRoman}</strong> clips still need Roman Urdu. Type <code>/romanize</code> in Claude Code or <code>$romanize</code> in Codex.
            </>
          )}
        </Item>
        <Item tone={flagged === 0 ? "ok" : "wait"}>
          {flagged === 0 ? (
            "No clips are flagged for a second look."
          ) : (
            <>
              <strong>{flagged}</strong> clips are flagged. Check them under “Needs a look” (not required to export).
            </>
          )}
        </Item>
      </ul>

      <div className="row">
        <button className="primary" disabled={busy || project.running !== null || included.length === 0} onClick={() => void run(false)}>
          {busy ? "Building…" : report?.written ? "Rebuild dataset" : "Build dataset"}
        </button>
        {report && !report.ok && report.errors.length > 0 && (
          <button disabled={busy} onClick={() => void run(true)} title="Write the files even though the format check found problems">
            Export anyway
          </button>
        )}
        {project.running !== null && <span className="hint">Wait for the running job to finish.</span>}
      </div>

      {report && (
        <div className="report">
          {report.written && (
            <div className="stats compact">
              <div className="stat">
                <span className="stat-label">Clips written</span>
                <span className="stat-value">{report.count}</span>
                <span className="stat-note">
                  {report.first} to {report.last}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">Audio</span>
                <span className="stat-value">{formatDuration(report.total_seconds)}</span>
                <span className="stat-note">total length</span>
              </div>
            </div>
          )}
          {report.errors.length > 0 && (
            <ul className="errors">
              {report.errors.slice(0, 8).map((e) => (
                <li key={e}>{e}</li>
              ))}
              {report.errors.length > 8 && <li>… and {report.errors.length - 8} more</li>}
            </ul>
          )}
          {report.warnings.map((w) => (
            <p key={w} className="warn">
              {w}
            </p>
          ))}
          {report.written && report.errors.length === 0 && <p className="good">✓ All format checks passed.</p>}
        </div>
      )}

      {project.exported && (
        <div className="downloads">
          <div className="row">
            <a className="button primary" href={api.download(project.id, "zip")}>
              Download dataset.zip
            </a>
            <a className="button" href={api.download(project.id, "xlsx")}>
              metadata.xlsx
            </a>
            <a className="button" href={api.download(project.id, "csv")}>
              metadata.csv
            </a>
          </div>
          {report?.output_dir && (
            <p className="hint" style={{ marginTop: 10 }}>
              Also saved on this computer in <span className="path">{report.output_dir}</span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
