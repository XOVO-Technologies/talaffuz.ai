import type { AssignmentProfile } from "../../types";

interface Props {
  draft: AssignmentProfile;
  id: string | null;
  disabled: boolean;
  onChange: (next: AssignmentProfile) => void;
}

const SECTIONS = ["7C", "7D", "7F", "7G", "7J"] as const;

export function DetailsCard({ draft, id, disabled, onChange }: Props) {
  const set = <K extends keyof AssignmentProfile>(key: K, value: AssignmentProfile[K]) => onChange({ ...draft, [key]: value });
  return (
    <fieldset className="settings" disabled={disabled}>
      <div className="grid">
        <label className="field">
          <span>Your name</span>
          <input type="text" value={draft.name} maxLength={120} autoComplete="name" onChange={(e) => set("name", e.target.value)} />
        </label>
        <label className="field">
          <span>Section</span>
          <select value={draft.section} onChange={(e) => set("section", e.target.value as AssignmentProfile["section"])}>
            {SECTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Roll number</span>
          <input
            type="number"
            min={1}
            max={999}
            value={draft.roll_no ?? ""}
            placeholder="For example 42"
            onChange={(e) => set("roll_no", e.target.value === "" ? null : Math.max(1, Math.min(999, Number(e.target.value))))}
          />
          <span className="help">Written with three digits, so 42 becomes 042.</span>
        </label>
        <fieldset className="field choice">
          <legend>Gender of the voice</legend>
          <div className="seg">
            {(["M", "F"] as const).map((g) => (
              <label key={g} className={`seg-item${draft.gender === g ? " on" : ""}`}>
                <input type="radio" name="gender" checked={draft.gender === g} onChange={() => set("gender", g)} />
                <span>{g === "M" ? "Male (M)" : "Female (F)"}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="field">
          <span>Phone model</span>
          <input type="text" value={draft.phone_model} maxLength={120} placeholder="The device used to record" onChange={(e) => set("phone_model", e.target.value)} />
        </label>
        <label className="field">
          <span>Place of recording</span>
          <input type="text" value={draft.location} maxLength={120} placeholder="City or room" onChange={(e) => set("location", e.target.value)} />
        </label>
        <label className="field">
          <span>Recorded from</span>
          <input type="date" value={draft.date_from} onChange={(e) => set("date_from", e.target.value)} />
        </label>
        <label className="field">
          <span>Recorded until</span>
          <input type="date" value={draft.date_to} min={draft.date_from || undefined} onChange={(e) => set("date_to", e.target.value)} />
        </label>
      </div>

      <p className="naming">
        <span>Speaker ID</span>
        <code>{id ?? "enter the roll number"}</code>
        {id && (
          <>
            <span>Zip</span>
            <code>{id}.zip</code>
            <span>First file</span>
            <code>{id}_R001.wav</code>
          </>
        )}
      </p>
      <p className="hint">The README and the experience form go to your teacher, so describe the recordings as they really are.</p>

      <details className="advanced">
        <summary>Counts and spelling</summary>
        <div className="grid">
          <label className="field">
            <span>Recordings in the dataset</span>
            <input type="number" min={1} max={999} value={draft.total} onChange={(e) => set("total", Math.max(1, Number(e.target.value)))} />
            <span className="help">The assignment asks for 500.</span>
          </label>
          <label className="field">
            <span>Recordings in train</span>
            <input type="number" min={1} max={998} value={draft.train} onChange={(e) => set("train", Math.max(1, Number(e.target.value)))} />
            <span className="help">The assignment asks for 400. The rest go to test.</span>
          </label>
          <label className="check wide">
            <input type="checkbox" checked={draft.lowercase_roman} onChange={(e) => set("lowercase_roman", e.target.checked)} />
            <span>
              Write Roman Urdu in lowercase
              <span className="help block">One spelling for each word is easier to keep when capital letters do not split it.</span>
            </span>
          </label>
        </div>
      </details>
    </fieldset>
  );
}
