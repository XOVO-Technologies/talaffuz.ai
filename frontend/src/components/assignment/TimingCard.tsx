import { formatDuration } from "../../format";
import type { AssignmentState, JobEvent } from "../../types";
import { JobProgress } from "../JobProgress";
import { ProgressBar } from "../ProgressBar";

interface Props {
  state: AssignmentState;
  event: JobEvent | null;
  blocked: string | null;
  onStart: (redo: boolean) => void;
  onStop: () => void;
}

const SECONDS_GPU = 2;
const SECONDS_CPU = 25;

export function TimingCard({ state, event, blocked, onStart, onStop }: Props) {
  const { done, total, weak } = state.timing;
  const left = Math.max(0, total - done);
  const gpu = state.device === "cuda";
  const running = state.running === "assignment_timing";
  const idle = state.running === null;
  const estimate = left * (gpu ? SECONDS_GPU : SECONDS_CPU);

  return (
    <div>
      <p className="hint" style={{ maxWidth: "75ch", marginBottom: 14 }}>
        The app listens to each recording and finds where every word starts and ends. These times become the sentence and word files and the start and end columns of the metadata. The results are saved after every recording, so you can stop and continue.
      </p>
      <ProgressBar value={total ? done / total : 0} label="Recordings with word timings" thick />
      <ul className="checklist" style={{ marginTop: 14 }}>
        <li>
          <span className={`tick ${total > 0 && done === total ? "ok" : "todo"}`} aria-hidden>
            {total > 0 && done === total ? "✓" : "!"}
          </span>
          <span>
            <strong>
              {done} of {total}
            </strong>{" "}
            recordings have word timings.
            {weak > 0 && ` ${weak} of them have weaker timing and are worth a listen after the build.`}
          </span>
        </li>
      </ul>
      {idle && left > 0 && (
        <p className="hint" style={{ marginBottom: 14, maxWidth: "75ch" }}>
          {gpu
            ? `This machine has a GPU (${state.device_name}), so the remaining ${left} recordings take about ${formatDuration(estimate)}.`
            : `This runs on the CPU (${state.device_name}) at roughly ${SECONDS_CPU} seconds per recording, so the remaining ${left} take about ${formatDuration(estimate)}. A GPU, such as the free one in Google Colab, is much faster.`}
        </p>
      )}
      <div className="row">
        {running ? (
          <button className="danger" onClick={onStop}>
            Stop
          </button>
        ) : (
          <>
            <button className="primary" disabled={!idle || left === 0 || blocked !== null} title={blocked ?? undefined} onClick={() => onStart(false)}>
              {done === 0 ? "Find word timings" : "Continue"}
            </button>
            {done > 0 && (
              <button className="ghost" disabled={!idle || blocked !== null} onClick={() => onStart(true)}>
                Redo all
              </button>
            )}
          </>
        )}
        {left === 0 && total > 0 && idle && <span className="good small">All timings are ready.</span>}
      </div>
      {blocked && !running && (
        <p className="hint" style={{ marginTop: 12 }}>
          {blocked}
        </p>
      )}
      {running && <JobProgress running="assignment_timing" event={event} />}
    </div>
  );
}
