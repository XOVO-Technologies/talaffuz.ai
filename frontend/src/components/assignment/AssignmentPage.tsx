import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { AssignmentProfile, AssignmentState, JobEvent } from "../../types";
import { Card, goTo } from "../Card";
import { Stepper, type StepInfo } from "../Stepper";
import { BuildCard } from "./BuildCard";
import { DetailsCard } from "./DetailsCard";
import { ExperienceCard } from "./ExperienceCard";
import { SourceCard } from "./SourceCard";
import { TimingCard } from "./TimingCard";

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

const detailsGaps = (p: AssignmentProfile) =>
  [p.roll_no === null, !p.name, !p.phone_model, !p.location, !(p.date_from || p.date_to)].filter(Boolean).length;

const experienceGaps = (p: AssignmentProfile) => {
  const e = p.experience;
  return [e.hours_recording, e.hours_cutting, e.hours_text, e.difficulty, e.hardest, e.helpful, e.issues, e.redo, e.learned].filter(
    (v) => v === "" || v === null,
  ).length;
};

export function AssignmentPage() {
  const [state, setState] = useState<AssignmentState | null>(null);
  const [draft, setDraft] = useState<AssignmentProfile | null>(null);
  const [event, setEvent] = useState<JobEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [version, setVersion] = useState(0);
  const scanned = useRef(false);
  const saved = useRef<AssignmentProfile | null>(null);

  const refresh = useCallback(async () => {
    const next = await api.assignmentState();
    setState(next);
    return next;
  }, []);

  useEffect(() => {
    api
      .assignmentState()
      .then((s) => {
        setState(s);
        setDraft(s.profile);
        saved.current = s.profile;
      })
      .catch((e: Error) => setOffline(e.message || "no answer from the backend"));
  }, []);

  const scan = useCallback(async () => {
    setScanning(true);
    setError(null);
    try {
      if (draft && !same(draft, saved.current)) {
        saved.current = draft;
        await api.assignmentSaveProfile(draft);
      }
      setState(await api.assignmentScan());
      setVersion((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setScanning(false);
    }
  }, [draft]);

  useEffect(() => {
    if (!state || scanned.current || state.source || state.source_error || state.running) return;
    scanned.current = true;
    void scan();
  }, [state, scan]);

  useEffect(() => {
    if (!draft || same(draft, saved.current)) return;
    const timer = setTimeout(() => {
      saved.current = draft;
      api
        .assignmentSaveProfile(draft)
        .then(setState)
        .catch((e: Error) => setError(e.message));
    }, 800);
    return () => clearTimeout(timer);
  }, [draft]);

  useEffect(() => {
    const source = new EventSource("/api/assignment/events");
    source.onmessage = (m) => {
      const ev: JobEvent = JSON.parse(m.data);
      setEvent(ev);
      if (["done", "error", "cancelled", "started"].includes(ev.stage)) void refresh();
      if (ev.stage === "error") setError(ev.message);
    };
    return () => source.close();
  }, [refresh]);

  const running = state?.running ?? null;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [running, refresh]);

  const guard = (fn: () => Promise<unknown>) => async () => {
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const flush = async () => {
    if (draft && !same(draft, saved.current)) {
      saved.current = draft;
      await api.assignmentSaveProfile(draft);
    }
  };

  const startTiming = (redo: boolean) =>
    guard(async () => {
      await flush();
      await api.assignmentTiming(redo);
    })();
  const startBuild = guard(async () => {
    await flush();
    await api.assignmentBuild();
  });
  const startCheck = guard(() => api.assignmentCheck());
  const stop = guard(() => api.assignmentCancel());

  if (offline !== null) {
    return (
      <main className="page-center">
        <p className="notice bad" role="alert">
          {offline}
        </p>
        <p>Start the app with ./start.ps1, then reload this page.</p>
        <button className="primary" onClick={() => location.reload()}>
          Reload
        </button>
      </main>
    );
  }
  if (!state || !draft) {
    return (
      <main className="page-center">
        <p role="status">Loading…</p>
      </main>
    );
  }

  const busy = state.running !== null;
  const detailsMissing = detailsGaps(draft);
  const experienceMissing = experienceGaps(draft);
  const text = state.text;
  const textBlocked = !state.source ? "Check the folder with your recordings first." : text && text.sentences.bad > 0 ? "Fix the sentences marked Needs a fix first." : null;
  const timingBlocked = state.id === null ? "Enter your roll number first." : textBlocked;
  const timingDone = state.timing.total > 0 && state.timing.done === state.timing.total;
  const built = !!state.zip;

  const order = [
    detailsMissing === 0,
    !!state.source && !!text && text.sentences.bad === 0,
    timingDone,
    experienceMissing === 0,
    built && !!state.check?.ok,
  ];
  const current = order.findIndex((d) => !d);
  const stateOf = (i: number): StepInfo["state"] => (order[i] ? "done" : i === current || current === -1 ? "current" : "todo");
  const steps: StepInfo[] = [
    { id: "details", label: "Your details", note: state.id ?? (detailsMissing ? `${detailsMissing} missing` : "Complete"), state: stateOf(0) },
    { id: "source", label: "Recordings and text", note: state.source ? `${state.source.found} recordings` : "Not checked", state: stateOf(1) },
    { id: "timing", label: "Word timing", note: `${state.timing.done} of ${state.timing.total}`, state: stateOf(2) },
    { id: "experience", label: "Experience form", note: experienceMissing ? `${experienceMissing} missing` : "Complete", state: stateOf(3) },
    { id: "build", label: "Build and check", note: built ? (state.check?.ok ? "Passed" : "Built") : "Not built", state: stateOf(4) },
  ];

  return (
    <>
      <div className="shell">
        <aside className="side">
          <Stepper steps={steps} />
          <div className="side-card">
            <h3>Your dataset</h3>
            <p>{state.id ? <code>{state.id}</code> : "Enter your roll number to see your ID."}</p>
            <h3>Help</h3>
            <ul>
              <li>
                <button className="link" onClick={() => goTo("build")}>
                  Jump to build
                </button>
              </li>
            </ul>
          </div>
        </aside>
        <main className="main">
          <section className="hero" aria-label="About this page">
            <div className="hero-main">
              <span className="tag">Assignment 2</span>
              <h2>Turn your recordings into the assignment dataset</h2>
              <p>
                Enter your details and the app builds the whole folder: 16 kHz mono recordings, sentence files, word files, the six metadata.csv files, README.md, EXPERIENCE.md and the zip named with your ID. Then it checks the result against the assignment rules.
              </p>
            </div>
            <div className="hero-side">
              <h3>What happens</h3>
              <ol className="hero-steps">
                <li>
                  <span className="n">1</span>
                  <div>
                    <strong>Details</strong>
                    <span>Your name, section, roll number and the recording facts.</span>
                  </div>
                </li>
                <li>
                  <span className="n">2</span>
                  <div>
                    <strong>Pair the words</strong>
                    <span>Urdu and Roman Urdu get the same number of words in every sentence.</span>
                  </div>
                </li>
                <li>
                  <span className="n">3</span>
                  <div>
                    <strong>Time the words</strong>
                    <span>The app finds where each word starts and ends.</span>
                  </div>
                </li>
                <li>
                  <span className="n">4</span>
                  <div>
                    <strong>Build and check</strong>
                    <span>Download the zip when the checks pass.</span>
                  </div>
                </li>
              </ol>
            </div>
          </section>

          <Card id="details" n={1} title="Your details" hint="These go into every file name, the metadata and the README. The ID is built from your section, roll number and gender.">
            <DetailsCard draft={draft} id={state.id} disabled={busy} onChange={setDraft} />
          </Card>

          <Card id="source" n={2} title="Recordings and text" hint="Uses the dataset you already built in the Dataset builder tab. Each of your clips becomes one recording.">
            <SourceCard
              state={state}
              draft={draft}
              scanning={scanning}
              version={version}
              disabled={busy}
              onPath={(path) => setDraft({ ...draft, source_path: path })}
              onScan={() => void scan()}
              onChanged={() => void refresh()}
              onError={setError}
            />
          </Card>

          <Card id="timing" n={3} title="Word timing" hint="Finds the start and end of every word so the audio can be cut into sentences and words.">
            <TimingCard state={state} event={event} blocked={timingBlocked} onStart={startTiming} onStop={() => void stop()} />
          </Card>

          <Card id="experience" n={4} title="Experience form" hint="Seven short questions about how the work went. They are written into EXPERIENCE.md in your own words.">
            <ExperienceCard value={draft.experience} disabled={busy} onChange={(experience) => setDraft({ ...draft, experience })} />
          </Card>

          <Card id="build" n={5} title="Build and check" hint="Writes the folder, checks it against the assignment rules and makes the zip.">
            <BuildCard state={state} event={event} onBuild={() => void startBuild()} onCheck={() => void startCheck()} onStop={() => void stop()} />
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
