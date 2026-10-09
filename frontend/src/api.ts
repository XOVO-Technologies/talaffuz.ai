import type { Clip, ExportReport, Health, KeyStatus, ModelList, Project, ProjectSummary, RomanEstimate, Settings, Source } from "./types";

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

const send = (method: string, url: string, body?: unknown) =>
  fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const api = {
  health: () => fetch("/api/health").then(parse<Health>),
  keyStatus: () => fetch("/api/anthropic-key").then(parse<KeyStatus>),
  saveKey: (key: string, remember: boolean) => send("PUT", "/api/anthropic-key", { key, remember }).then(parse<KeyStatus>),
  removeKey: () => send("DELETE", "/api/anthropic-key").then(parse<KeyStatus>),
  models: () => fetch("/api/anthropic-models").then(parse<ModelList>),
  setModel: (model: string, remember: boolean) => send("PUT", "/api/anthropic-model", { model, remember }).then(parse<KeyStatus>),
  romanEstimate: (id: string) => fetch(`/api/projects/${id}/romanize-estimate`).then(parse<RomanEstimate>),
  listProjects: () => fetch("/api/projects").then(parse<ProjectSummary[]>),
  createProject: (name: string) => send("POST", "/api/projects", { name }).then(parse<Project>),
  getProject: (id: string) => fetch(`/api/projects/${id}`).then(parse<Project>),
  deleteProject: (id: string) => send("DELETE", `/api/projects/${id}`).then(parse<unknown>),
  putSettings: (id: string, s: Settings) => send("PUT", `/api/projects/${id}/settings`, s).then(parse<Project>),
  resegment: (id: string) => send("POST", `/api/projects/${id}/resegment`).then(parse<Project>),
  importSources: (id: string, path: string) => send("POST", `/api/projects/${id}/sources/import`, { path }).then(parse<Source[]>),
  deleteSource: (id: string, sid: string) => send("DELETE", `/api/projects/${id}/sources/${sid}`).then(parse<Project>),
  process: (id: string, extra = 0) => send("POST", `/api/projects/${id}/process`, { extra }).then(parse<unknown>),
  romanize: (id: string, onlyMissing: boolean) =>
    send("POST", `/api/projects/${id}/romanize`, { only_missing: onlyMissing }).then(parse<unknown>),
  cancel: (id: string) => send("POST", `/api/projects/${id}/cancel`).then(parse<unknown>),
  patchClip: (id: string, cid: string, patch: Partial<Pick<Clip, "urdu" | "roman" | "keep">>) =>
    send("PATCH", `/api/projects/${id}/clips/${cid}`, patch).then(parse<Clip>),
  exportDataset: (id: string, force: boolean) =>
    send("POST", `/api/projects/${id}/export`, { force }).then(parse<ExportReport>),
  clipAudio: (id: string, cid: string) => `/api/projects/${id}/clips/${cid}/audio`,
  download: (id: string, kind: "zip" | "csv" | "xlsx") => `/api/projects/${id}/download/${kind}`,

  /** Raw-body upload (not multipart) so multi-GB files stream straight to disk and report progress. */
  uploadFile(id: string, file: File, onProgress: (fraction: number) => void): Promise<Source> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", `/api/projects/${id}/sources?filename=${encodeURIComponent(file.name)}`);
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) return resolve(JSON.parse(xhr.responseText));
        let message = xhr.statusText;
        try {
          message = JSON.parse(xhr.responseText).detail ?? message;
        } catch {
          /* keep statusText */
        }
        reject(new Error(message));
      };
      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.send(file);
    });
  },
};
