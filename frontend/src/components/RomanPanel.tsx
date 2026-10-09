import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { formatUsd } from "../format";
import type { KeyStatus, ModelList, ModelOption, RomanEstimate } from "../types";

const COMMAND = "/romanize";

const note = (id: string) =>
  id.includes("haiku")
    ? "Fastest and lowest cost."
    : id.includes("sonnet")
      ? "Balanced cost and capability."
      : id.includes("opus")
        ? "More capable, higher cost."
        : "Most capable, highest cost.";

const price = (m: ModelOption) =>
  m.input_per_mtok === null || m.output_per_mtok === null
    ? "Price not listed"
    : `$${m.input_per_mtok.toFixed(2)} in, $${m.output_per_mtok.toFixed(2)} out per 1M tokens`;

interface Props {
  projectId: string;
  missing: number;
  running: boolean;
  autoOn: boolean; // the "write Roman Urdu automatically" setting
  status: KeyStatus | null;
  onSaveKey: (key: string, remember: boolean) => Promise<boolean>;
  onRemoveKey: () => Promise<void>;
  onSetModel: (model: string, remember: boolean) => Promise<void>;
  onGenerate: () => Promise<void>;
}

/** Roman Urdu from Claude Code (no key), or from an Anthropic API key with a visible choice of model and a cost estimate. */
export function RomanPanel({ projectId, missing, running, autoOn, status, onSaveKey, onRemoveKey, onSetModel, onGenerate }: Props) {
  const configured = status?.configured ?? false;
  const [key, setKey] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [models, setModels] = useState<ModelList | null>(null);
  const [estimate, setEstimate] = useState<RomanEstimate | null>(null);
  const current = status?.model ?? models?.current ?? "";

  // The model options come from the Anthropic Models API once a key is set, and from a built-in list before that.
  useEffect(() => {
    let live = true;
    api.models().then((m) => live && setModels(m)).catch(() => {});
    return () => {
      live = false;
    };
  }, [configured]);

  useEffect(() => {
    let live = true;
    api.romanEstimate(projectId).then((e) => live && setEstimate(e)).catch(() => {});
    return () => {
      live = false;
    };
  }, [projectId, missing, current]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(COMMAND);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard can be blocked; the command is visible to type by hand */
    }
  }

  async function saveAndGenerate(e: FormEvent) {
    e.preventDefault();
    if (!key.trim()) return;
    setBusy(true);
    try {
      if (await onSaveKey(key.trim(), remember)) {
        setKey("");
        if (missing > 0) await onGenerate();
      }
    } finally {
      setBusy(false);
    }
  }

  const cheapest = models?.models.find((m) => m.cheapest);

  const modelOptions = models && (
    <fieldset className="models" disabled={running}>
      <legend>
        Model for Roman Urdu
        <small>{models.source === "api" ? "Listed from your Anthropic account" : "Built-in list"}</small>
      </legend>
      <div className="model-grid">
        {models.models.map((m) => (
          <label key={m.id} className={`model${m.id === current ? " on" : ""}`}>
            <input type="radio" name="roman-model" checked={m.id === current} onChange={() => void onSetModel(m.id, status?.saved ?? false)} />
            <span className="model-name">
              {m.name}
              {m.cheapest && <span className="low">Lowest cost</span>}
            </span>
            <span className="model-note">{note(m.id)}</span>
            <span className="model-price">{price(m)}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );

  const cost =
    estimate && missing > 0 ? (
      <p className="estimate" aria-live="polite">
        {estimate.cost_usd === null ? (
          <>The price of this model is not listed here, so no estimate is shown.</>
        ) : (
          <>
            Estimated cost for the {estimate.rows} {estimate.rows === 1 ? "clip" : "clips"} that need Roman Urdu with{" "}
            <strong>{models?.models.find((m) => m.id === estimate.model)?.name ?? estimate.model}</strong>:{" "}
            <strong>{formatUsd(estimate.cost_usd)}</strong>
            {cheapest && cheapest.id !== estimate.model ? ` (${cheapest.name} is the lowest-cost option)` : ""}. It is billed to your Anthropic account.
          </>
        )}
      </p>
    ) : null;

  if (configured) {
    return (
      <section className="roman" aria-label="Roman Urdu with the Anthropic API">
        <div className="roman-bar">
          <span>
            <strong>Anthropic API key is set</strong>
            {status?.saved ? " and saved on this computer." : " for this session only."}
            {autoOn ? " New clips get Roman Urdu right after transcription." : ""}
          </span>
          <button className="ghost sm" onClick={() => void onRemoveKey()} disabled={running}>
            Remove key
          </button>
        </div>
        {modelOptions}
        {cost}
        <div className="row">
          <button className="primary" disabled={running || missing === 0} onClick={() => void onGenerate()}>
            Generate missing Roman Urdu
          </button>
          {missing === 0 && <span className="hint">Every kept clip already has Roman Urdu.</span>}
        </div>
      </section>
    );
  }

  return (
    <section className="roman" aria-label="Ways to get Roman Urdu">
      <div className="roman-head">
        <strong>
          {missing} {missing === 1 ? "clip needs" : "clips need"} Roman Urdu
        </strong>
        <span>Pick how it gets written. You can also type it in any row of the table.</span>
      </div>
      <div className="roman-options">
        <div className="opt">
          <h3>Claude Code or Codex</h3>
          <p>No key needed. Open Claude Code in this project folder and run the command, or ask Codex to run $romanize. This table fills in a few seconds later.</p>
          <div className="notice-actions">
            <code>{COMMAND}</code>
            <button className="sm" onClick={() => void copy()}>
              {copied ? "Copied" : "Copy command"}
            </button>
          </div>
        </div>

        <form className="opt" onSubmit={(e) => void saveAndGenerate(e)}>
          <h3>Anthropic API key</h3>
          <p>The app writes it for you, right after transcription or when you press the button. Your key stays on this computer.</p>
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="sk-ant-..."
            autoComplete="off"
            spellCheck={false}
            aria-label="Anthropic API key"
          />
          <label className="check small">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            <span>Remember on this computer (saved in backend/.env, which Git ignores)</span>
          </label>
          <button type="submit" className="primary" disabled={busy || !key.trim() || running}>
            {busy ? "Checking the key…" : "Save key and generate"}
          </button>
        </form>
      </div>
      {modelOptions}
      {cost}
    </section>
  );
}
