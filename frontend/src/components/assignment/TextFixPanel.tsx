import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { AssignmentProblem } from "../../types";

const LONG_DASHES = String.fromCharCode(0x2013, 0x2014);
const URDU_MARKS = new RegExp(`[۔؟!،؛:"'“”‘’«»()\\[\\]{}…\\-/\\\\|*_.,?;${LONG_DASHES}]`, "g");
const ROMAN_JOINERS = new RegExp(`[-/_${LONG_DASHES}]+`, "g");

const countUrdu = (text: string) => text.replace(URDU_MARKS, " ").split(/\s+/).filter(Boolean).length;
const countRoman = (text: string) => text.replace(ROMAN_JOINERS, "").replace(/[^A-Za-z0-9\s']/g, " ").split(/\s+/).filter(Boolean).length;
const label = (p: AssignmentProblem) => `R${String(p.number).padStart(3, "0")}${p.sentence === null ? "" : ` S${String(p.sentence + 1).padStart(2, "0")}`}`;

interface ItemProps {
  item: AssignmentProblem;
  onSaved: (next: AssignmentProblem | null) => void;
  onError: (message: string) => void;
}

function ProblemItem({ item, onSaved, onError }: ItemProps) {
  const [urdu, setUrdu] = useState(item.urdu);
  const [roman, setRoman] = useState(item.roman);
  const [busy, setBusy] = useState(false);
  const u = countUrdu(urdu);
  const r = countRoman(roman);
  const changed = urdu !== item.urdu || roman !== item.roman;
  const reason =
    item.reason === "sentence_count"
      ? "The Urdu and the Roman Urdu have a different number of sentences. Make each sentence end with a full stop in both."
      : item.reason === "unpairable"
        ? "The words could not be paired automatically."
        : item.reason === "too_many"
          ? "A sentence or recording is too long for the file names. Split it with a full stop."
          : item.status === "check"
            ? "Fixed automatically. Check that each Roman word sits under the right Urdu word."
            : "Word counts differ.";

  async function save() {
    setBusy(true);
    try {
      const result = await api.assignmentEdit({ key: item.key, sentence: item.sentence, urdu, roman });
      onSaved("removed" in result ? null : result);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`problem ${item.status}`}>
      <div className="problem-head">
        <strong>{label(item)}</strong>
        <span className={`pill ${item.status === "bad" ? "err" : "work"}`}>{item.status === "bad" ? "Needs a fix" : "Check"}</span>
        <span className="small">{reason}</span>
      </div>
      {item.pairs.length > 0 && (
        <ul className="pairs" dir="rtl" aria-label="Word pairs">
          {item.pairs.map(([ur, ro], i) => (
            <li key={i} className="pair">
              <span className="pair-ur" lang="ur">
                {ur}
              </span>
              <span className="pair-ro" dir="ltr">
                {ro}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="problem-edit">
        <label className="field">
          <span>
            Urdu <small className={u === r ? "good" : "bad"}>{u} words</small>
          </span>
          <textarea className="urdu" dir="rtl" lang="ur" rows={item.scope === "recording" ? 6 : 3} value={urdu} onChange={(e) => setUrdu(e.target.value)} />
        </label>
        <label className="field">
          <span>
            Roman Urdu <small className={u === r ? "good" : "bad"}>{r} words</small>
          </span>
          <textarea rows={item.scope === "recording" ? 6 : 3} lang="ur-Latn" spellCheck={false} value={roman} onChange={(e) => setRoman(e.target.value)} />
        </label>
      </div>
      <div className="row">
        <button className="primary sm" disabled={busy || !changed} onClick={() => void save()}>
          {busy ? "Saving…" : "Save"}
        </button>
        {changed && (
          <button
            className="ghost sm"
            onClick={() => {
              setUrdu(item.urdu);
              setRoman(item.roman);
            }}
          >
            Undo
          </button>
        )}
      </div>
    </li>
  );
}

interface Props {
  bad: number;
  check: number;
  version: number;
  onChanged: () => void;
  onError: (message: string) => void;
}

const PAGE = 10;

export function TextFixPanel({ bad, check, version, onChanged, onError }: Props) {
  const [kind, setKind] = useState<"bad" | "check">(bad > 0 || check === 0 ? "bad" : "check");
  const [items, setItems] = useState<AssignmentProblem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = useCallback(
    async (offset: number) => {
      setLoading(true);
      try {
        const page = await api.assignmentProblems(kind, offset, PAGE);
        setItems((old) => (offset === 0 ? page.items : [...old, ...page.items]));
        setTotal(page.total);
      } catch (e) {
        onError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [kind, onError],
  );

  useEffect(() => {
    void load(0);
  }, [load, version]);

  useEffect(() => {
    if (kind === "bad" && bad === 0 && check > 0) setKind("check");
  }, [kind, bad, check]);

  function saved(index: number, next: AssignmentProblem | null) {
    if (next && next.status === kind) setItems((old) => old.map((it, i) => (i === index ? next : it)));
    else setItems((old) => old.filter((_, i) => i !== index));
    onChanged();
  }

  return (
    <div className="textfix">
      <div className="filters" role="tablist" aria-label="Sentences to look at">
        <button role="tab" aria-selected={kind === "bad"} className={`chip${kind === "bad" ? " on" : ""}`} onClick={() => setKind("bad")}>
          Needs a fix ({bad})
        </button>
        <button role="tab" aria-selected={kind === "check"} className={`chip${kind === "check" ? " on" : ""}`} onClick={() => setKind("check")}>
          Fixed automatically, worth a look ({check})
        </button>
      </div>
      {items.length === 0 && !loading && (
        <p className="empty">{kind === "bad" ? "Nothing needs a fix. Every sentence has the same number of Urdu and Roman Urdu words." : "No automatic fix needs a second look."}</p>
      )}
      <ul className="problems">
        {items.map((item, index) => (
          <ProblemItem key={`${item.key}-${item.sentence}-${item.urdu}-${item.roman}`} item={item} onError={onError} onSaved={(next) => saved(index, next)} />
        ))}
      </ul>
      {items.length < total && (
        <button className="sm" disabled={loading} onClick={() => void load(items.length)}>
          {loading ? "Loading…" : `Show more (${total - items.length} left)`}
        </button>
      )}
    </div>
  );
}
