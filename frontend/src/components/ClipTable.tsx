import { memo, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { capacityOf, fileName, needsLook } from "../format";
import type { Clip, Project } from "../types";
import { PlayIcon, StopIcon } from "./icons";

type Filter = "all" | "attention" | "no-roman" | "rejected";

const FILTERS: { id: Filter; label: string; test: (c: Clip) => boolean }[] = [
  { id: "all", label: "All", test: () => true },
  { id: "attention", label: "Needs a look", test: needsLook },
  { id: "no-roman", label: "No Roman Urdu", test: (c) => c.keep && !c.roman.trim() },
  { id: "rejected", label: "Rejected", test: (c) => !c.keep },
];

const FLAG_HELP: Record<string, string> = {
  empty: "Nothing was recognised",
  repetition: "Repeated words, usually a recognition glitch",
  not_urdu_script: "Mostly not Urdu script",
  digits: "Contains digits; spell numbers out in words",
  too_little_text: "Very little text for this much audio; words may be missing",
  too_much_text: "Too much text for this audio; check for hallucination",
  low_confidence: "The model was unsure",
  maybe_not_speech: "May not be speech",
  noisy: "Low signal-to-noise ratio",
  clipping: "Audio clipping",
};

type Patch = Partial<Pick<Clip, "urdu" | "roman" | "keep">>;

interface RowProps {
  clip: Clip;
  slot: number | null; // file number this clip will get, or null when rejected / over capacity
  playing: boolean;
  onPlay: (clip: Clip) => void;
  onSave: (id: string, patch: Patch) => void;
}

const Row = memo(function Row({ clip, slot, playing, onPlay, onSave }: RowProps) {
  const [urdu, setUrdu] = useState(clip.urdu);
  const [roman, setRoman] = useState(clip.roman);
  useEffect(() => setUrdu(clip.urdu), [clip.urdu]);
  useEffect(() => setRoman(clip.roman), [clip.roman]);
  const name = slot !== null ? fileName(slot) : "this clip";

  return (
    <tr className={`${clip.keep ? "" : "rejected"} ${playing ? "playing" : ""}`}>
      <td className="num">
        {slot !== null ? (
          fileName(slot)
        ) : clip.keep ? (
          <span className="extra muted" title="More good clips than file numbers; this one is left out of the export">
            extra
          </span>
        ) : (
          <span className="extra muted">rejected</span>
        )}
      </td>
      <td>
        <div className="clip-audio">
          <button
            className="play"
            onClick={() => onPlay(clip)}
            disabled={!clip.duration_s}
            aria-label={playing ? `Stop ${name}` : `Play ${name}`}
            title={playing ? "Stop" : "Play"}
          >
            {playing ? <StopIcon /> : <PlayIcon />}
          </button>
          <span className="muted small" title={clip.asr_confidence !== null ? "Speech recognition confidence" : undefined}>
            {clip.duration_s.toFixed(1)} s{clip.asr_confidence !== null && ` · ${Math.round(clip.asr_confidence * 100)}%`}
          </span>
        </div>
      </td>
      <td className="text">
        <textarea
          dir="rtl"
          lang="ur"
          className="urdu"
          rows={2}
          value={urdu}
          aria-label={`Urdu sentence for ${name}`}
          onChange={(e) => setUrdu(e.target.value)}
          onBlur={() => urdu !== clip.urdu && onSave(clip.id, { urdu })}
        />
        {(clip.flags.length > 0 || clip.error) && (
          <div className="flags">
            {clip.flags.map((f) => (
              <span key={f} className="flag" title={FLAG_HELP[f] ?? f}>
                {f.replace(/_/g, " ")}
              </span>
            ))}
            {clip.error && <span className="flag bad">{clip.error}</span>}
          </div>
        )}
      </td>
      <td className="text">
        <textarea
          dir="ltr"
          lang="ur-Latn"
          spellCheck={false}
          className="roman"
          rows={2}
          value={roman}
          placeholder="Roman Urdu"
          aria-label={`Roman Urdu for ${name}`}
          onChange={(e) => setRoman(e.target.value)}
          onBlur={() => roman !== clip.roman && onSave(clip.id, { roman })}
        />
      </td>
      <td className="keep">
        <label className="row" style={{ justifyContent: "center", gap: 6 }}>
          <input type="checkbox" checked={clip.keep} onChange={(e) => onSave(clip.id, { keep: e.target.checked })} />
          <span className="small muted">Keep</span>
        </label>
      </td>
    </tr>
  );
});

const PAGE = 40; // Nastaliq text is expensive to lay out, so only a page of rows is in the DOM at a time

export function ClipTable({ project, onPatched }: { project: Project; onPatched: (c: Clip) => void }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const search = useDeferredValue(query.trim().toLowerCase());
  const [limit, setLimit] = useState(PAGE);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const playingRef = useRef<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const projectId = project.id;
  useEffect(() => setLimit(PAGE), [filter, search]);

  const processed = useMemo(
    () => project.clips.filter((c) => c.status !== "pending").sort((a, b) => a.order - b.order),
    [project.clips],
  );
  const slots = useMemo(() => {
    const cap = capacityOf(project.settings);
    const map = new Map<string, number>();
    processed
      .filter((c) => c.keep && c.status === "processed")
      .slice(0, cap ?? undefined)
      .forEach((c, i) => map.set(c.id, project.settings.start_index + i));
    return map;
  }, [processed, project.settings]);

  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f.id, processed.filter(f.test).length])) as Record<Filter, number>,
    [processed],
  );

  const shown = useMemo(() => {
    const test = FILTERS.find((f) => f.id === filter)!.test;
    return processed.filter((c) => {
      if (!test(c)) return false;
      if (!search) return true;
      const slot = slots.get(c.id);
      return (
        c.urdu.includes(search) ||
        c.roman.toLowerCase().includes(search) ||
        (slot !== undefined && fileName(slot).includes(search))
      );
    });
  }, [processed, filter, search, slots]);

  useEffect(() => {
    const a = new Audio();
    const stop = () => {
      playingRef.current = null;
      setPlayingId(null);
    };
    a.onended = stop;
    a.onerror = stop;
    audio.current = a;
    return () => a.pause();
  }, []);

  // Stable identities so the memoised rows do not all re-render on every change.
  const play = useCallback(
    (clip: Clip) => {
      const a = audio.current;
      if (!a) return;
      if (playingRef.current === clip.id) {
        a.pause();
        playingRef.current = null;
        setPlayingId(null);
        return;
      }
      a.src = api.clipAudio(projectId, clip.id);
      void a.play().catch(() => {
        playingRef.current = null;
        setPlayingId(null);
      });
      playingRef.current = clip.id;
      setPlayingId(clip.id);
    },
    [projectId],
  );

  const save = useCallback(
    async (id: string, patch: Patch) => {
      onPatched(await api.patchClip(projectId, id, patch));
    },
    [projectId, onPatched],
  );

  if (processed.length === 0) {
    return <div className="empty">Clips appear here as they are processed. Start the run above to fill this table.</div>;
  }

  return (
    <div>
      <div className="toolbar">
        <div className="filters" role="group" aria-label="Filter clips">
          {FILTERS.map((f) => (
            <button key={f.id} className={filter === f.id ? "chip on" : "chip"} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
              {f.label} ({counts[f.id]})
            </button>
          ))}
        </div>
        <input
          type="search"
          className="search"
          placeholder="Search Urdu, Roman or file number"
          aria-label="Search clips"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {shown.length === 0 ? (
        <div className="empty">{search ? "No clips match your search." : "No clips in this view."}</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Audio</th>
                <th>Urdu sentence</th>
                <th>Roman Urdu</th>
                <th>Keep</th>
              </tr>
            </thead>
            <tbody>
              {shown.slice(0, limit).map((c) => (
                <Row key={c.id} clip={c} slot={slots.get(c.id) ?? null} playing={playingId === c.id} onPlay={play} onSave={save} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {shown.length > limit && (
        <div className="row" style={{ marginTop: 12, justifyContent: "center" }}>
          <button onClick={() => setLimit((n) => n + PAGE)}>
            Show {Math.min(PAGE, shown.length - limit)} more ({shown.length - limit} not shown)
          </button>
        </div>
      )}
    </div>
  );
}
