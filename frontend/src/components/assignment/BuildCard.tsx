import { useState, type ReactNode } from "react";
import { api } from "../../api";
import { formatDuration } from "../../format";
import type { AssignmentState, JobEvent } from "../../types";
import { Stat } from "../Card";
import { JobProgress } from "../JobProgress";

interface Props {
  state: AssignmentState;
  event: JobEvent | null;
  onBuild: () => void;
  onCheck: () => void;
  onStop: () => void;
}

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

const SPLITS = ["train", "test"] as const;

export function BuildCard({ state, event, onBuild, onCheck, onStop }: Props) {
  const [showOfficial, setShowOfficial] = useState(false);
  const idle = state.running === null;
  const text = state.text;
  const source = state.source;
  const detailsDone = state.missing.length === 0;
  const textDone = !!text && text.sentences.bad === 0 && text.recordings.bad === 0;
  const countDone = !!source && source.short_by === 0;
  const check = state.check;
  const build = state.build;
  const ready = detailsDone && textDone && !!source;

  return (
    <div>
      <ul className="checklist">
        <Item tone={detailsDone ? "ok" : "todo"}>
          {detailsDone ? "Your details and experience form are complete." : <>Still missing: {state.missing.join(", ")}.</>}
        </Item>
        <Item tone={source ? (textDone ? "ok" : "todo") : "wait"}>
          {!source ? "Check the folder with your recordings first." : textDone ? "Every sentence has matching Urdu and Roman Urdu word counts." : "Some sentences still need a fix in step 2."}
        </Item>
        <Item tone={source ? (countDone ? "ok" : "wait") : "wait"}>
          {!source ? "The recording count is checked with the folder." : countDone ? `${state.profile.total} recordings are available.` : `${source.short_by} recordings short of ${state.profile.total}. You can still build to test the files.`}
        </Item>
        <Item tone={state.timing.total > 0 && state.timing.done === state.timing.total ? "ok" : "wait"}>
          {state.timing.done === state.timing.total && state.timing.total > 0 ? "Word timings are ready." : "Word timings that are missing are found at the start of the build."}
        </Item>
      </ul>

      <div className="row">
        {state.running === "assignment_build" ? (
          <button className="danger" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button className="primary" disabled={!idle || !ready} onClick={onBuild} title={ready ? undefined : "Finish the steps above first"}>
            {state.zip ? "Rebuild the dataset" : "Build the dataset"}
          </button>
        )}
        {state.zip && idle && (
          <button onClick={onCheck} title="Run the checks again on the finished dataset">
            Check again
          </button>
        )}
        {!detailsDone && <span className="hint">Complete step 1 and step 4 first.</span>}
      </div>

      {(state.running === "assignment_build" || state.running === "assignment_check") && <JobProgress running={state.running} event={event} />}

      {build && (
        <div className="report">
          <div className="stats compact">
            {(["recordings", "sentences", "words"] as const).map((level) => (
              <Stat
                key={level}
                label={level[0].toUpperCase() + level.slice(1)}
                value={SPLITS.reduce((sum, s) => sum + (build.counts[level]?.[s] ?? 0), 0).toLocaleString()}
                note={`train ${build.counts[level]?.train ?? 0}, test ${build.counts[level]?.test ?? 0}, ${formatDuration(build.seconds[level] ?? 0)}`}
              />
            ))}
          </div>
          {build.weak.length > 0 && (
            <p className="warn">
              Weaker word timing in {build.weak.length} recordings (for example R{String(build.weak[0]).padStart(3, "0")}). Listen to a few of their word files.
            </p>
          )}
        </div>
      )}

      {check && (
        <div className="report">
          {check.ok ? (
            <p className="notice good" role="status">
              The built-in check found no mistakes. The folder follows the file names, audio settings, split rule, word counts, README and experience form rules.
            </p>
          ) : (
            <>
              <p className="notice bad" role="alert">
                The built-in check found {check.errors.length} problems.
              </p>
              <ul className="errors">
                {check.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </>
          )}
          {check.warnings.length > 0 && (
            <ul className="warnings">
              {check.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          {check.official ? (
            <div className={`notice ${check.official.ok ? "good" : "bad"}`}>
              <div className="notice-body">
                <strong>{check.official.ok ? "The official check_dataset.py found no mistakes." : "The official check_dataset.py reported problems."}</strong>
                <button className="ghost sm" style={{ width: "max-content" }} onClick={() => setShowOfficial((v) => !v)}>
                  {showOfficial ? "Hide output" : "Show output"}
                </button>
                {showOfficial && <pre className="official">{check.official.output}</pre>}
              </div>
            </div>
          ) : (
            <p className="hint">
              To also run the teacher&apos;s <code>check_dataset.py</code> after every build, put that file in the <code>assignment</code> folder inside the app&apos;s data folder, or next to the app&apos;s README.
            </p>
          )}
        </div>
      )}

      {state.zip && (
        <div className="downloads">
          <div className="row">
            <a className="button primary" href={api.assignmentDownload}>
              Download {state.zip.name}
            </a>
            <span className="small">{state.zip.size_mb.toLocaleString()} MB</span>
          </div>
          <p className="hint" style={{ marginTop: 10 }}>
            Upload the zip to your section&apos;s folder on the teacher&apos;s Drive link. On Colab the file is also in your Drive, in the same data folder as your projects.
          </p>
        </div>
      )}
    </div>
  );
}
