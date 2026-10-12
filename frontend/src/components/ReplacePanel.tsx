import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import type { Project, ReplaceRequest, ReplaceResult } from "../types";
import { useDialog } from "./Dialog";

type Field = ReplaceRequest["field"];

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

interface Props {
  project: Project;
  onDone: () => void;
  onError: (message: string) => void;
}

/** Fix a word the transcription keeps getting wrong, or make one Roman Urdu spelling consistent, in every clip at once. */
export function ReplacePanel({ project, onDone, onError }: Props) {
  const dialog = useDialog();
  const [field, setField] = useState<Field>("roman");
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [wholeWord, setWholeWord] = useState(true);
  // The count is kept with the search it belongs to, so a count for older input is never shown or acted on.
  const [preview, setPreview] = useState<(ReplaceResult & { key: string }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const urdu = field === "urdu";
  const key = JSON.stringify([field, find, replace, wholeWord]);
  const count = find.trim() && preview?.key === key ? preview : null;

  // Count what would change while the user types. The clips are a dependency so the count follows edits and new clips.
  useEffect(() => {
    if (!find.trim()) return;
    let live = true;
    const t = setTimeout(() => {
      api
        .replaceText(project.id, { field, find, replace, whole_word: wholeWord, dry_run: true })
        .then((r) => live && setPreview({ ...r, key }))
        .catch(() => live && setPreview(null)); // e.g. a search of only "|", which is never in the text
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [project.id, project.clips, field, find, replace, wholeWord, key]);

  async function run(e: FormEvent) {
    e.preventDefault();
    if (!count || count.clips === 0) return;
    const column = urdu ? "Urdu" : "Roman Urdu";
    const ok = await dialog.confirm({
      title: `Replace in ${plural(count.clips, "clip")}?`,
      message: replace.trim() ? (
        <>
          “<bdi>{find.trim()}</bdi>” becomes “<bdi>{replace.trim()}</bdi>” in {plural(count.places, "place")} of the {column} text.
          There is no undo.
        </>
      ) : (
        <>
          “<bdi>{find.trim()}</bdi>” is removed from {plural(count.places, "place")} of the {column} text. There is no undo.
        </>
      ),
      confirmLabel: "Replace",
    });
    if (!ok) return;
    setBusy(true);
    try {
      const r = await api.replaceText(project.id, { field, find, replace, whole_word: wholeWord, dry_run: false });
      setFind("");
      setReplace("");
      setDone(`Replaced in ${plural(r.clips, "clip")}.`);
      onDone();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const textProps = urdu
    ? { dir: "rtl" as const, lang: "ur", className: "urdu-input" }
    : { dir: "ltr" as const, lang: "ur-Latn", spellCheck: false };

  return (
    <details className="advanced replace">
      <summary>Find and replace in every clip</summary>
      <form onSubmit={(e) => void run(e)}>
        <p className="hint replace-help">
          Fix a word the transcription keeps getting wrong, or make a spelling the same across the dataset, such as{" "}
          <code>bohot</code> to <code>bohat</code>. Clips that are not processed yet are left alone.
        </p>
        <label className="field">
          <span>Column</span>
          <select value={field} onChange={(e) => setField(e.target.value as Field)}>
            <option value="roman">Roman Urdu</option>
            <option value="urdu">Urdu sentence</option>
          </select>
        </label>
        <label className="field">
          <span>Find</span>
          <input
            type="text"
            value={find}
            onChange={(e) => {
              setFind(e.target.value);
              setDone(null);
            }}
            maxLength={200}
            {...textProps}
          />
        </label>
        <label className="field">
          <span>Replace with</span>
          <input
            type="text"
            value={replace}
            onChange={(e) => setReplace(e.target.value)}
            maxLength={200}
            placeholder="Leave empty to remove"
            {...textProps}
          />
        </label>
        <div className="replace-foot">
          <label className="check small">
            <input type="checkbox" checked={wholeWord} onChange={(e) => setWholeWord(e.target.checked)} />
            <span>Whole words only</span>
          </label>
          <span className="small" aria-live="polite">
            {find.trim()
              ? count && (count.clips === 0 ? "No clip would change." : `Changes ${plural(count.places, "place")} in ${plural(count.clips, "clip")}.`)
              : done}
          </span>
          <button type="submit" className="primary sm" disabled={busy || !count || count.clips === 0}>
            {busy ? "Replacing…" : "Replace all"}
          </button>
        </div>
      </form>
    </details>
  );
}
