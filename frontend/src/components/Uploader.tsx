import { useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { formatBytes, formatDuration } from "../format";
import type { Project, Source } from "../types";
import { useDialog } from "./Dialog";
import { AudioFileIcon, UploadIcon } from "./icons";
import { ProgressBar } from "./ProgressBar";

interface Props {
  project: Project;
  onUploaded: () => void;
  onError: (message: string) => void;
}

const STATUS: Record<Source["status"], [label: string, tone: string]> = {
  uploaded: ["Ready to analyse", ""],
  analyzing: ["Analysing…", "work"],
  analyzed: ["Analysed", "ok"],
  error: ["Failed", "err"],
};

export function Uploader({ project, onUploaded, onError }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const dialog = useDialog();
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [path, setPath] = useState("");
  const [importing, setImporting] = useState(false);
  const locked = project.running !== null;

  async function upload(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      setProgress((p) => ({ ...p, [file.name]: 0 }));
      try {
        await api.uploadFile(project.id, file, (f) => setProgress((p) => ({ ...p, [file.name]: f })));
      } catch (e) {
        onError(`${file.name}: ${(e as Error).message}`);
      }
      setProgress(({ [file.name]: _gone, ...rest }) => rest);
      onUploaded();
    }
  }

  async function remove(source: Source) {
    const ok = await dialog.confirm({
      title: "Remove this recording?",
      message: `"${source.name}" and every clip cut from it will be deleted from this project.`,
      confirmLabel: "Remove",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteSource(project.id, source.id);
      onUploaded();
    } catch (e) {
      onError((e as Error).message);
    }
  }

  async function importPath(e: FormEvent) {
    e.preventDefault();
    if (!path.trim()) return;
    setImporting(true);
    try {
      await api.importSources(project.id, path.trim());
      setPath("");
      onUploaded();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setImporting(false);
    }
  }

  const choose = () => !locked && input.current?.click();
  const uploading = Object.entries(progress);

  return (
    <div>
      <div
        className={`drop${over ? " over" : ""}${locked ? " locked" : ""}${project.sources.length > 0 ? " compact" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!locked) void upload(e.dataTransfer.files);
        }}
        onClick={choose}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            choose();
          }
        }}
        role="button"
        tabIndex={locked ? -1 : 0}
        aria-disabled={locked}
        aria-label="Add recordings: drop files here or press Enter to choose"
      >
        <UploadIcon />
        <strong>{locked ? "Recordings are locked while a job runs" : "Drop long recordings here"}</strong>
        <span>or click to choose files. wav, mp3, m4a, flac, ogg and mp4 all work, and several GB is fine.</span>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          accept="audio/*,video/*,.wav,.mp3,.m4a,.flac,.ogg,.opus,.aac,.wma,.mp4,.mkv,.webm"
          onChange={(e) => {
            if (e.target.files) void upload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      <details className="pathbox">
        <summary>Add files that are already on this computer</summary>
        <form onSubmit={(e) => void importPath(e)}>
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="C:\Recordings\talk.wav   or a folder such as C:\Recordings"
            aria-label="Path to an audio file or a folder"
            disabled={locked}
          />
          <button type="submit" className="primary" disabled={locked || importing || !path.trim()}>
            {importing ? "Copying…" : "Add"}
          </button>
        </form>
        <p className="hint">
          Paste the path of one audio file, or of a folder to add every audio file inside it. The files are copied into this
          project, so nothing is pushed through the browser. Useful for very large files.
        </p>
      </details>

      {(uploading.length > 0 || project.sources.length > 0) && (
        <ul className="sources">
          {uploading.map(([name, fraction]) => (
            <li key={name} className="source">
              <span className="source-icon">
                <AudioFileIcon />
              </span>
              <span className="source-main">
                <span className="source-name">{name}</span>
                <span className="source-meta">Uploading… {Math.round(fraction * 100)}%</span>
              </span>
              <ProgressBar value={fraction} label={`Uploading ${name}`} />
            </li>
          ))}
          {project.sources.map((s) => {
            const [label, tone] = STATUS[s.status];
            return (
              <li key={s.id} className={`source${s.status === "error" ? " error" : ""}`}>
                <span className="source-icon">
                  <AudioFileIcon />
                </span>
                <span className="source-main">
                  <span className="source-name" title={s.name}>
                    {s.name}
                  </span>
                  <span className="source-meta">
                    {formatBytes(s.size_bytes)}
                    {s.duration_s ? ` · ${formatDuration(s.duration_s)}` : ""}
                    {s.error ? ` · ${s.error}` : ""}
                  </span>
                </span>
                <span className={`pill ${tone}`}>{label}</span>
                <button className="ghost danger sm" disabled={locked} onClick={() => void remove(s)}>
                  Remove
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
