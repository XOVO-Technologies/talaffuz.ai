import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { BackendMissing } from "./components/BackendMissing";
import { ClipTable } from "./components/ClipTable";
import { useDialog } from "./components/Dialog";
import { ExportPanel } from "./components/ExportPanel";
import { GithubStars } from "./components/GithubStars";
import { Logo } from "./components/icons";
import { JobProgress } from "./components/JobProgress";
import { RomanPanel } from "./components/RomanPanel";
import { SettingsPanel, validateSettings } from "./components/SettingsPanel";
import { Stepper, type StepInfo } from "./components/Stepper";
import { Uploader } from "./components/Uploader";
import { REPO_URL } from "./config";
import { capacityOf, fileName, formatDuration, isGood, lacksRoman, needsLook } from "./format";
import type { Clip, Health, JobEvent, KeyStatus, Project, ProjectSummary, Settings } from "./types";

const LAST_KEY = "urdu-dataset:last-project";
const SECONDS_PER_CLIP = 35; // measured on a laptop CPU with large-v3-turbo

const remember = (id: string) => {
  try {
    localStorage.setItem(LAST_KEY, id);
  } catch {
    /* storage can be blocked; the app works without it */
  }
};

interface CardProps {
  id: string;
  n: number;
  title: string;
  hint?: string;
  children: ReactNode;
  /** Makes the card collapsible. While collapsed, `summary` replaces the hint and the body is hidden. */
  collapse?: { collapsed: boolean; summary: string; showLabel: string; onToggle: () => void };
}

function Card({ id, n, title, hint, children, collapse }: CardProps) {
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

function Stat({ label, value, unit, note, attn }: { label: string; value: ReactNode; unit?: string; note?: string; attn?: boolean }) {
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

const goTo = (id: string) => document.getElementById(`step-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

function Hero() {
  return (
    <section className="hero" aria-label="About this tool">
      <div className="hero-main">
        <span className="tag">Urdu speech dataset</span>
        <h2>Turn long Urdu recordings into a training dataset</h2>
        <p>
          Add your recordings and the app cuts them into sentence-length clips, removes noise and music, and transcribes
          each clip in Urdu. You correct what it got wrong, add Roman Urdu, then export the wavs and metadata in one
          fixed format. Everything runs on this computer, and no audio leaves it.
        </p>
        <button className="primary lg" onClick={() => goTo("recordings")}>
          Add recordings
        </button>
      </div>
      <div className="hero-side">
        <h3>How it works</h3>
        <ol className="hero-steps">
          <li>
            <span className="n">1</span>
            <div>
              <strong>Add recordings</strong>
              <span>Drop in long audio files. Files of several GB are fine.</span>
            </div>
          </li>
          <li>
            <span className="n">2</span>
            <div>
              <strong>Process</strong>
              <span>Speech is cut at pauses, cleaned and transcribed. Plan on about 35 seconds per clip on a laptop CPU.</span>
            </div>
          </li>
          <li>
            <span className="n">3</span>
            <div>
              <strong>Review</strong>
              <span>Play each clip, fix the Urdu and drop the bad ones. Claude Code or Codex writes the Roman Urdu.</span>
            </div>
          </li>
          <li>
            <span className="n">4</span>
            <div>
              <strong>Export</strong>
              <span>Download dataset.zip with the wavs, metadata.csv and metadata.xlsx.</span>
            </div>
          </li>
        </ol>
      </div>
    </section>
  );
}

export default function App() {
  const dialog = useDialog();
  const [health, setHealth] = useState<Health | null>(null);
  const [keyStatus, setKeyStatus] = useState<KeyStatus | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [event, setEvent] = useState<JobEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState<string | null>(null); // set when the first request to the backend fails
  // Settings and Recordings fold away once there are clips; the user can still open them by hand.
  const [openOverride, setOpenOverride] = useState<Record<string, boolean>>({});
  const pid = project?.id;
  const running = project?.running ?? null;
  useEffect(() => setOpenOverride({}), [pid]);

  const refresh = useCallback(async (id: string) => {
    const p = await api.getProject(id);
    setProject(p);
    return p;
  }, []);

  const open = useCallback(
    async (id: string) => {
      const p = await refresh(id);
      setDraft(p.settings);
      setEvent(null);
      remember(id);
    },
    [refresh],
  );

  // First load: health, project list, reopen the last project or create one.
  useEffect(() => {
    (async () => {
      try {
        setHealth(await api.health());
        api.keyStatus().then(setKeyStatus).catch(() => {});
        let list = await api.listProjects();
        if (list.length === 0) {
          await api.createProject("Urdu dataset");
          list = await api.listProjects();
        }
        setProjects(list);
        let last: string | null = null;
        try {
          last = localStorage.getItem(LAST_KEY);
        } catch {
          /* ignore */
        }
        await open(list.find((p) => p.id === last)?.id ?? list[0].id);
      } catch (e) {
        setOffline((e as Error).message || "no answer from the backend");
      }
    })();
  }, [open]);

  // Live progress from the server while a job runs.
  const openRef = useRef(refresh);
  openRef.current = refresh;
  useEffect(() => {
    if (!pid) return;
    const source = new EventSource(`/api/projects/${pid}/events`);
    source.onmessage = (m) => {
      const ev: JobEvent = JSON.parse(m.data);
      setEvent(ev);
      if (["done", "error", "cancelled", "started"].includes(ev.stage)) void openRef.current(pid);
      if (ev.stage === "error") setError(ev.message);
    };
    return () => source.close();
  }, [pid]);

  // While a job runs, refetch so new clips show up in the table.
  useEffect(() => {
    if (!pid || !running) return;
    const t = setInterval(() => void refresh(pid), 3000);
    return () => clearInterval(t);
  }, [pid, running, refresh]);

  // Roman Urdu is usually written by Claude Code (/romanize) outside this page, so pick its changes up.
  const missingRoman = useMemo(() => (project ? project.clips.filter(lacksRoman).length : 0), [project]);
  useEffect(() => {
    if (!pid || running || missingRoman === 0) return;
    const t = setInterval(() => !document.hidden && void refresh(pid), 8000);
    return () => clearInterval(t);
  }, [pid, running, missingRoman, refresh]);

  const guard = (fn: () => Promise<unknown>) => async () => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const settingsProblem = draft ? validateSettings(draft) : null;

  const start = guard(async () => {
    if (!project || !draft) return;
    await api.putSettings(project.id, draft);
    await api.process(project.id);
    await refresh(project.id);
  });

  const processMore = guard(async () => {
    if (!project) return;
    await api.putSettings(project.id, draft ?? project.settings);
    await api.process(project.id, 50);
    await refresh(project.id);
  });

  // Roman Urdu through the Anthropic API. These return rather than throw so the panel can decide what to do next.
  const saveKey = async (key: string, remember: boolean) => {
    setError(null);
    try {
      setKeyStatus(await api.saveKey(key, remember));
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };
  const removeKey = guard(async () => setKeyStatus(await api.removeKey()));
  const chooseModel = async (model: string, remember: boolean) => {
    try {
      setKeyStatus(await api.setModel(model, remember));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const generateRoman = guard(async () => {
    if (!project) return;
    await api.romanize(project.id, true);
    await refresh(project.id);
  });

  const onPatched = useCallback((clip: Clip) => {
    setProject((p) => (p ? { ...p, clips: p.clips.map((c) => (c.id === clip.id ? clip : c)) } : p));
  }, []);

  const newProject = guard(async () => {
    const name = await dialog.prompt({ title: "New project", label: "Project name", defaultValue: "Urdu dataset" });
    if (!name) return;
    const p = await api.createProject(name);
    setProjects(await api.listProjects());
    await open(p.id);
  });

  const deleteProject = guard(async () => {
    if (!project) return;
    const ok = await dialog.confirm({
      title: "Delete this project?",
      message: `"${project.name}" and all its recordings, clips and exported files will be removed from this computer. This cannot be undone.`,
      confirmLabel: "Delete project",
      danger: true,
    });
    if (!ok) return;
    await api.deleteProject(project.id);
    let list = await api.listProjects();
    if (list.length === 0) {
      await api.createProject("Urdu dataset");
      list = await api.listProjects();
    }
    setProjects(list);
    await open(list[0].id);
  });

  const resegment = guard(async () => {
    if (!project) return;
    const ok = await dialog.confirm({
      title: "Cut the recordings again?",
      message: "All current clips, including your edits to them, are discarded. The recordings are analysed again with the current settings.",
      confirmLabel: "Re-segment",
      danger: true,
    });
    if (!ok) return;
    await api.resegment(project.id);
    await refresh(project.id);
  });

  const header = (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="brand">
          <span className="logo">
            <Logo />
          </span>
          <div>
            <h1>Talaffuz.ai</h1>
            <p>Runs on this computer</p>
          </div>
        </div>
        <div className="topbar-actions">
          {project && (
            <>
              <select aria-label="Project" value={project.id} onChange={(e) => void open(e.target.value)} disabled={running !== null}>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.id === project.id ? project.clips.length : p.clips} clips)
                  </option>
                ))}
              </select>
              <button className="sm" onClick={newProject} disabled={running !== null}>
                New project
              </button>
              <button className="ghost sm quiet-danger" onClick={deleteProject} disabled={running !== null} title="Delete this project">
                Delete
              </button>
            </>
          )}
          <GithubStars />
        </div>
      </div>
    </header>
  );

  if (!project || !draft) {
    if (offline !== null) {
      return (
        <>
          {header}
          <BackendMissing detail={offline} />
        </>
      );
    }
    return (
      <>
        {header}
        <main className="page-center">
          {error ? (
            <>
              <p className="notice bad" role="alert">
                {error}
              </p>
              <p>Start the app with ./start.ps1, then reload this page.</p>
              <button className="primary" onClick={() => location.reload()}>
                Reload
              </button>
            </>
          ) : (
            <p role="status">Loading…</p>
          )}
        </main>
      </>
    );
  }

  // ---- numbers for the dashboard ----
  const cap = capacityOf(project.settings);
  const good = project.clips.filter(isGood).length;
  const pending = project.clips.filter((c) => c.status === "pending").length;
  const rejected = project.clips.filter((c) => !c.keep && c.status !== "pending").length;
  const flagged = project.clips.filter((c) => isGood(c) && needsLook(c)).length;
  const hasSources = project.sources.length > 0;
  const recordedSeconds = project.sources.reduce((sum, s) => sum + (s.duration_s ?? 0), 0);
  const romanizeViaApi = keyStatus?.configured ?? health?.romanize_available ?? false;

  const stage = running ? 2 : project.exported ? 5 : good > 0 ? (missingRoman > 0 ? 3 : 4) : hasSources ? 2 : 1;
  const state = (i: number): StepInfo["state"] => (i < stage ? "done" : i === stage ? "current" : "todo");
  const steps: StepInfo[] = [
    { id: "settings", label: "Settings", note: `${cap === null ? "All clips" : `${cap} clips`} · ${(project.settings.sample_rate / 1000).toFixed(2).replace(/\.?0+$/, "")} kHz`, state: state(0) },
    { id: "recordings", label: "Recordings", note: hasSources ? `${project.sources.length} file${project.sources.length === 1 ? "" : "s"}` : "None yet", state: state(1) },
    { id: "process", label: "Process", note: running ? "Running" : good > 0 ? `${good} clips` : "Not started", state: state(2) },
    { id: "review", label: "Review", note: missingRoman > 0 ? `${missingRoman} need Roman Urdu` : flagged > 0 ? `${flagged} to check` : good > 0 ? "Nothing flagged" : "Waiting", state: state(3) },
    { id: "export", label: "Export", note: project.exported ? "Built" : "Not built", state: state(4) },
  ];

  const foldAway = project.clips.length > 0; // by default, hide the setup cards once the work has started
  const isOpen = (id: string) => openOverride[id] ?? !foldAway;
  const toggle = (id: string) => () => setOpenOverride((o) => ({ ...o, [id]: !isOpen(id) }));
  const musicLabel = { auto: "music removed only if present", on: "music always removed", off: "music never removed" }[draft.remove_music];
  const settingsSummary = [
    draft.end_index === null
      ? `Files from ${fileName(draft.start_index)}, every good clip`
      : `${fileName(draft.start_index)} to ${fileName(draft.end_index)} (${capacityOf(draft)} clips)`,
    `${(draft.sample_rate / 1000).toFixed(2).replace(/\.?0+$/, "")} kHz`,
    draft.whisper_model,
    musicLabel,
  ].join(" · ");
  const failedSources = project.sources.filter((s) => s.status === "error").length;
  const recordingsSummary = hasSources
    ? `${project.sources.length} recording${project.sources.length === 1 ? "" : "s"}${recordedSeconds ? `, ${formatDuration(recordedSeconds)} of audio` : ""}${failedSources ? `, ${failedSources} failed` : ""}`
    : "No recordings yet";

  const draftCap = capacityOf(draft);
  const goal = draftCap === null ? null : Math.ceil(draftCap * (1 + draft.buffer_pct / 100));
  // With no last file number every candidate is processed, which is unknown until the recordings have been cut.
  const clipsToDo = goal === null ? pending : Math.max(0, Math.min(goal - good, project.clips.length === 0 ? goal : pending));
  const showEstimate =
    running === null && hasSources && !settingsProblem && clipsToDo > 0 && health?.device !== "cuda" && draft.whisper_model === "large-v3-turbo";

  return (
    <>
      {header}
      <div className="shell">
      <aside className="side">
        <Stepper
          steps={steps}
          onSelect={(id) => (id === "settings" || id === "recordings") && setOpenOverride((o) => ({ ...o, [id]: true }))}
        />
        <div className="side-card">
          <h3>Help</h3>
          <ul>
            <li>
              <a href={`${REPO_URL}#using-the-app`} target="_blank" rel="noopener noreferrer">
                User guide
              </a>
            </li>
            <li>
              <a href={`${REPO_URL}/issues`} target="_blank" rel="noopener noreferrer">
                Report a problem
              </a>
            </li>
          </ul>
        </div>
      </aside>
      <main className="main">
        {health && !health.ffmpeg && (
          <p className="notice bad" role="alert">
            ffmpeg could not be found, so audio cannot be decoded. Run ./setup.ps1 again.
          </p>
        )}

        {!hasSources && project.clips.length === 0 ? (
          <Hero />
        ) : (
          <div className="stats" role="group" aria-label="Project summary">
            <Stat label="Recordings" value={project.sources.length} note={recordedSeconds ? `${formatDuration(recordedSeconds)} of audio` : "Not analysed yet"} />
            <Stat label="Clips ready" value={good} unit={cap === null ? undefined : `of ${cap}`} note={pending > 0 ? `${pending} more candidates waiting` : undefined} />
            <Stat label="Need Roman Urdu" value={missingRoman} attn={missingRoman > 0} note={missingRoman > 0 ? "Run /romanize or $romanize" : "All filled in"} />
            <Stat label="Need a look" value={flagged} attn={flagged > 0} note={flagged > 0 ? "Flagged by the checks" : "Nothing flagged"} />
          </div>
        )}

        <Card
          id="settings"
          n={1}
          title="Settings"
          hint="The defaults suit most recordings. Files are numbered from 1 and every good clip is kept. Set a last file number to stop at a fixed count."
          collapse={{ collapsed: !isOpen("settings"), summary: settingsSummary, showLabel: "Edit", onToggle: toggle("settings") }}
        >
          <SettingsPanel value={draft} onChange={setDraft} disabled={running !== null} />
        </Card>

        <Card
          id="recordings"
          n={2}
          title="Recordings"
          hint="Add one or more long recordings. They are copied into this project on your disk and go nowhere else."
          collapse={{ collapsed: !isOpen("recordings"), summary: recordingsSummary, showLabel: "Show", onToggle: toggle("recordings") }}
        >
          <Uploader project={project} onUploaded={() => void refresh(project.id)} onError={setError} />
        </Card>

        <Card id="process" n={3} title="Cut and transcribe" hint="Finds the speech, cuts clips at pauses, removes noise and music, then writes the Urdu text for each clip.">
          <div className="row">
            {running === null ? (
              <>
                <button className="primary" onClick={start} disabled={!hasSources || settingsProblem !== null} title={settingsProblem ?? undefined}>
                  {project.clips.length === 0 ? "Start" : "Continue"}
                </button>
                {pending > 0 && good > 0 && <button onClick={processMore}>Process 50 more clips</button>}
                {project.clips.length > 0 && (
                  <button className="ghost" onClick={resegment}>
                    Re-segment
                  </button>
                )}
              </>
            ) : (
              <button className="danger" onClick={guard(async () => void (await api.cancel(project.id)))}>
                Stop
              </button>
            )}
            {health && <span className="small">Runs on {health.device === "cuda" ? health.name : "the CPU"}</span>}
          </div>
          {!hasSources && <p className="hint" style={{ marginTop: 12 }}>Add a recording first.</p>}
          {settingsProblem && hasSources && (
            <p className="inline-alert bad" role="alert" style={{ marginTop: 12 }}>
              Fix the settings first: {settingsProblem}
            </p>
          )}
          {showEstimate && (
            <p className="hint" style={{ marginTop: 12, maxWidth: "70ch" }}>
              {goal === null ? `This run covers all ${clipsToDo} clips found so far.` : `This run covers up to about ${clipsToDo} clips.`}{" "}
              On a laptop CPU that takes roughly{" "}
              <strong>{formatDuration(clipsToDo * SECONDS_PER_CLIP)}</strong>, at about {SECONDS_PER_CLIP} seconds per clip and more when
              music has to be removed. Progress is saved after every clip, so you can stop and continue later.
            </p>
          )}
          {running !== null && <JobProgress running={running} event={event} />}
          {running === null && event?.stage === "done" && (
            <p className="notice good" role="status" style={{ marginTop: 20 }}>
              {event.message}
            </p>
          )}
          {running === null && project.clips.length > 0 && (
            <div className="stats compact" style={{ marginTop: 20 }}>
              <Stat label="Good clips" value={good} />
              <Stat label="Rejected" value={rejected} note="Empty, repeated or not speech" />
              <Stat label="Not processed yet" value={pending} />
            </div>
          )}
        </Card>

        <Card id="review" n={4} title="Review" hint="Play each clip and fix the Urdu and Roman Urdu. Untick Keep on clips that are bad. Edits save when you leave a field.">
          {(missingRoman > 0 || romanizeViaApi) && (
            <RomanPanel
              projectId={project.id}
              missing={missingRoman}
              running={running !== null}
              autoOn={draft.auto_romanize}
              status={keyStatus}
              onSaveKey={saveKey}
              onRemoveKey={removeKey}
              onSetModel={chooseModel}
              onGenerate={generateRoman}
            />
          )}
          <div style={{ marginTop: missingRoman > 0 || romanizeViaApi ? 20 : 0 }}>
            <ClipTable project={project} onPatched={onPatched} />
          </div>
        </Card>

        <Card id="export" n={5} title="Export" hint="Builds the files in the fixed format and checks them before you download.">
          <ExportPanel project={project} onDone={() => void refresh(project.id)} onError={setError} />
        </Card>
      </main>
      </div>

      {error && (
        <div className="toast" role="alert">
          <span className="toast-msg">{error}</span>
          <button className="ghost sm" onClick={() => setError(null)} aria-label="Dismiss message">
            Dismiss
          </button>
        </div>
      )}
    </>
  );
}
