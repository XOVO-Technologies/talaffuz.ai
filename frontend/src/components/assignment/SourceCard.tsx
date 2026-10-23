import { useState } from "react";
import type { AssignmentProfile, AssignmentState } from "../../types";
import { Stat } from "../Card";
import { TextFixPanel } from "./TextFixPanel";

interface Props {
  state: AssignmentState;
  draft: AssignmentProfile;
  scanning: boolean;
  version: number;
  disabled: boolean;
  onPath: (path: string) => void;
  onScan: () => void;
  onChanged: () => void;
  onError: (message: string) => void;
}

const OTHER = "__other__";

export function SourceCard({ state, draft, scanning, version, disabled, onPath, onScan, onChanged, onError }: Props) {
  const known = state.choices.find((c) => c.path === draft.source_path || (draft.source_path === "" && c === state.choices[0]));
  const [other, setOther] = useState(!known && draft.source_path !== "");
  const selected = other || !known ? OTHER : known.path;
  const info = state.source;
  const text = state.text;
  const needed = draft.total;

  return (
    <div>
      <div className="source-pick">
        <label className="field">
          <span>Folder with your wavs and metadata</span>
          <select
            value={selected}
            disabled={disabled}
            onChange={(e) => {
              if (e.target.value === OTHER) {
                setOther(true);
              } else {
                setOther(false);
                onPath(e.target.value);
              }
            }}
          >
            {state.choices.map((c) => (
              <option key={c.path} value={c.path}>
                {c.label}
              </option>
            ))}
            <option value={OTHER}>Another folder</option>
          </select>
        </label>
        {selected === OTHER && (
          <label className="field">
            <span>Folder path</span>
            <input
              type="text"
              className="mono"
              value={draft.source_path}
              disabled={disabled}
              placeholder="D:\Downloads\talaffuz.ai\dataset or /content/drive/MyDrive/..."
              onChange={(e) => onPath(e.target.value)}
            />
          </label>
        )}
        <button className="primary" disabled={scanning || disabled} onClick={onScan}>
          {scanning ? "Checking…" : info ? "Check again" : "Check this folder"}
        </button>
      </div>
      <p className="hint source-help">
        The folder holds <code>wavs/</code> and <code>metadata.csv</code> or <code>metadata.xlsx</code>, the files the dataset builder exports. On Colab, paste a path that starts with <code>/content/drive/MyDrive/</code> (a Google Drive web link will not work), after mounting Drive in step 3 of the notebook.
      </p>

      {state.source_error && (
        <p className="notice bad" role="alert" style={{ marginTop: 16 }}>
          {state.source_error}
        </p>
      )}

      {info && text && (
        <>
          <div className="stats compact" style={{ marginTop: 20 }}>
            <Stat label="Recordings found" value={info.found} note={info.used < info.found ? `${info.used} will be used` : info.metadata_file} />
            <Stat
              label="Length of each"
              value={info.min_seconds === info.max_seconds ? info.min_seconds.toFixed(1) : `${info.min_seconds.toFixed(1)} to ${info.max_seconds.toFixed(1)}`}
              unit="s"
              note={`${info.sample_rates.map((r) => `${(r / 1000).toFixed(2).replace(/\.?0+$/, "")} kHz`).join(", ")}, converted to 16 kHz`}
            />
            <Stat label="Sentences" value={text.sentences.ok + text.sentences.fixed + text.sentences.check + text.sentences.bad} note={`${text.words.toLocaleString()} words`} />
          </div>

          {info.short_by > 0 && (
            <p className="notice" role="status" style={{ marginTop: 16 }}>
              <span className="notice-body">
                <strong>
                  {info.found} recordings found, {needed} needed.
                </strong>
                <span>
                  You are {info.short_by} short. Process {info.short_by} more clips in the Dataset builder tab, export again, and check this folder again. You can build with fewer to test, but the checker expects {needed}.
                </span>
              </span>
            </p>
          )}
          {info.missing_audio > 0 && (
            <p className="notice bad" role="alert" style={{ marginTop: 16 }}>
              {info.missing_audio} rows in the metadata have no wav file and were skipped.
            </p>
          )}
          {info.empty_text > 0 && (
            <p className="notice bad" role="alert" style={{ marginTop: 16 }}>
              {info.empty_text} recordings have no Urdu or no Roman Urdu text.
            </p>
          )}

          <h3 className="subhead">Urdu and Roman Urdu word counts</h3>
          <p className="hint" style={{ maxWidth: "75ch" }}>
            Every sentence needs the same number of Urdu and Roman Urdu words, so each word has a pair. Where the Roman text joins or splits words differently, the app pairs them for you using the spellings already in your data.
          </p>
          <div className="stats compact" style={{ marginTop: 14 }}>
            <Stat label="Ready as they are" value={text.sentences.ok} note="Sentences" />
            <Stat label="Paired automatically" value={text.sentences.fixed + text.sentences.check} note={`${text.sentences.check} worth a look`} attn={text.sentences.check > 0} />
            <Stat label="Need your fix" value={text.sentences.bad} note={text.sentences.bad > 0 ? "Blocks the build" : "Nothing left"} attn={text.sentences.bad > 0} />
          </div>
          <div style={{ marginTop: 18 }}>
            <TextFixPanel bad={text.sentences.bad} check={text.sentences.check} version={version} onChanged={onChanged} onError={onError} />
          </div>
        </>
      )}
    </div>
  );
}
