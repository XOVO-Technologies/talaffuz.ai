import type { ChangeEvent } from "react";
import { capacityOf, fileName } from "../format";
import type { Settings } from "../types";

interface Props {
  value: Settings;
  onChange: (s: Settings) => void;
  disabled: boolean;
}

const MODELS = [
  ["large-v3-turbo", "large-v3-turbo (recommended)"],
  ["large-v3", "large-v3 (most accurate, slowest)"],
  ["medium", "medium (about 2x faster, less accurate)"],
  ["small", "small (fast, poor Urdu accuracy)"],
];

/** Returns a message when the settings cannot be saved, otherwise null. Mirrors the server's checks. */
export function validateSettings(s: Settings): string | null {
  if (!(s.start_index >= 1) || (s.end_index !== null && !(s.end_index >= 1))) return "File numbers must be 1 or higher.";
  if (s.end_index !== null && s.end_index < s.start_index) return "The last file number must not be smaller than the first.";
  if (s.min_clip_s > s.max_clip_s) return "The shortest clip cannot be longer than the longest clip.";
  return null;
}

export function SettingsPanel({ value: s, onChange, disabled }: Props) {
  const num = (key: keyof Settings) => (e: ChangeEvent<HTMLInputElement>) => onChange({ ...s, [key]: Number(e.target.value) });
  const slots = capacityOf(s);
  const problem = validateSettings(s);
  const fixedLength = s.min_clip_s === s.max_clip_s;

  return (
    <fieldset disabled={disabled} className="settings">
      <div className="groups">
      <section className="group">
        <h3>File numbering</h3>
        <div className="grid">
          <label className="field">
            <span>First file number</span>
            <input type="number" min={1} value={s.start_index} onChange={num("start_index")} />
            <span className="help">Start above 1 to continue an existing dataset.</span>
          </label>
          <label className="field">
            <span>Last file number (optional)</span>
            <input
              type="number"
              min={1}
              placeholder="No limit"
              value={s.end_index ?? ""}
              onChange={(e) => onChange({ ...s, end_index: e.target.value === "" ? null : Number(e.target.value) })}
            />
            <span className="help">Leave empty to keep every good clip. Set a number to stop at a fixed count.</span>
          </label>
          <label className="field">
            <span>Extra clips to process (%)</span>
            <input type="number" min={0} max={100} value={s.buffer_pct} disabled={s.end_index === null} onChange={num("buffer_pct")} />
            <span className="help">
              {s.end_index === null ? "Only used when a last file number is set." : "A cushion so rejected clips can be replaced."}
            </span>
          </label>
        </div>
        {problem ? (
          <p className="inline-alert bad" role="alert" style={{ marginTop: 12 }}>
            {problem}
          </p>
        ) : (
          <p className="naming" style={{ marginTop: 12 }}>
            <span>Output files</span>
            <code>{fileName(s.start_index)}.wav</code>
            {slots === null || s.end_index === null ? (
              <strong>onward, one per kept clip</strong>
            ) : (
              <>
                <span>to</span>
                <code>{fileName(s.end_index)}.wav</code>
                <strong>({slots} clips)</strong>
              </>
            )}
          </p>
        )}
      </section>

      <section className="group">
        <h3>Audio quality</h3>
        <div className="grid">
          <label className="field">
            <span>Sample rate</span>
            <select value={s.sample_rate} onChange={(e) => onChange({ ...s, sample_rate: Number(e.target.value) })}>
              <option value={22050}>22,050 Hz (recommended)</option>
              <option value={24000}>24,000 Hz</option>
              <option value={16000}>16,000 Hz</option>
              <option value={44100}>44,100 Hz</option>
            </select>
          </label>
          <label className="field">
            <span>Noise reduction ({Math.round(s.denoise_strength * 100)}%)</span>
            <input type="range" min={0} max={1} step={0.05} value={s.denoise_strength} onChange={num("denoise_strength")} />
            <span className="help">Keep it light: heavy denoising changes the voice.</span>
          </label>
          <label className="field">
            <span>Background music</span>
            <select value={s.remove_music} onChange={(e) => onChange({ ...s, remove_music: e.target.value as Settings["remove_music"] })}>
              <option value="auto">Remove only if the recording has music</option>
              <option value="on">Always remove (slow: about 3x real time on CPU)</option>
              <option value="off">Never remove</option>
            </select>
          </label>
        </div>
      </section>

      <section className="group">
        <h3>Transcription</h3>
        <div className="grid">
          <label className="field wide">
            <span>Urdu speech model</span>
            <select value={s.whisper_model} onChange={(e) => onChange({ ...s, whisper_model: e.target.value })}>
              {MODELS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <span className="help">large-v3-turbo takes about 35 seconds per clip on a laptop CPU. Smaller models are faster and get more Urdu words wrong.</span>
          </label>
        </div>
        <label className="check" style={{ marginTop: 16 }}>
          <input type="checkbox" checked={s.auto_romanize} onChange={(e) => onChange({ ...s, auto_romanize: e.target.checked })} />
          <span>
            Write Roman Urdu automatically after transcription
            <span className="help hint"> (when an Anthropic API key is set, which you can add in the Review step)</span>
          </span>
        </label>
      </section>
      </div>

      <details className="advanced">
        <summary>Clip length and speech detection</summary>
        <div className="grid">
          <label className="field">
            <span>Shortest clip (s)</span>
            <input type="number" step={0.5} min={1} value={s.min_clip_s} onChange={num("min_clip_s")} />
            <span className="help">Your choice. Clips are packed to at least this long.</span>
          </label>
          <label className="field">
            <span>Longest clip (s)</span>
            <input type="number" step={0.5} min={3} value={s.max_clip_s} onChange={num("max_clip_s")} />
            <span className="help">Your choice. Up to about 60 seconds works well.</span>
          </label>
          <label className="field">
            <span>Join phrases closer than (s)</span>
            <input type="number" step={0.1} min={0.1} value={s.merge_gap_s} onChange={num("merge_gap_s")} />
          </label>
          <label className="field">
            <span>Pause that splits speech (ms)</span>
            <input type="number" step={50} min={100} value={s.vad_min_silence_ms} onChange={num("vad_min_silence_ms")} />
          </label>
          <label className="field">
            <span>Speech threshold</span>
            <input type="number" step={0.05} min={0.1} max={0.9} value={s.vad_threshold} onChange={num("vad_threshold")} />
          </label>
          <label className="field">
            <span>Padding around speech (ms)</span>
            <input type="number" step={50} min={0} value={s.pad_ms} onChange={num("pad_ms")} />
          </label>
          <label className="field">
            <span>Loudness (LUFS)</span>
            <input type="number" step={1} value={s.target_lufs} onChange={num("target_lufs")} />
          </label>
        </div>
        {fixedLength && (
          <p className="inline-alert" role="note" style={{ marginBottom: 14 }}>
            Shortest and longest are equal, so recordings are cut into exact {s.min_clip_s}-second windows on the clock,
            ignoring pauses. Words can be split in half. Use this only when you need an exact clip length.
          </p>
        )}
        <p className="hint" style={{ paddingBottom: 14 }}>
          Changing these only affects recordings analysed afterwards. Use “Re-segment” to redo existing ones.
        </p>
      </details>
    </fieldset>
  );
}
