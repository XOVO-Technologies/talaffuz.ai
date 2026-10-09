export interface Settings {
  start_index: number;
  end_index: number | null; // null: no last file number, keep every good clip
  buffer_pct: number;
  sample_rate: number;
  min_clip_s: number;
  max_clip_s: number;
  merge_gap_s: number;
  vad_threshold: number;
  vad_min_silence_ms: number;
  pad_ms: number;
  remove_music: "auto" | "on" | "off";
  denoise_strength: number;
  target_lufs: number;
  whisper_model: string;
  whisper_beam: number;
  auto_romanize: boolean;
}

export interface Source {
  id: string;
  name: string;
  size_bytes: number;
  status: "uploaded" | "analyzing" | "analyzed" | "error";
  duration_s: number | null;
  error: string | null;
}

export interface Clip {
  id: string;
  source_id: string;
  order: number;
  start_s: number;
  end_s: number;
  status: "pending" | "processed" | "error";
  keep: boolean;
  urdu: string;
  roman: string;
  duration_s: number;
  asr_confidence: number | null;
  snr_db: number | null;
  flags: string[];
  error: string | null;
}

export interface ExportReport {
  written: boolean;
  ok: boolean;
  errors: string[];
  warnings: string[];
  count: number;
  expected: number | null;
  first: string | null;
  last: string | null;
  total_seconds: number;
  output_dir: string | null;
}

export interface Project {
  id: string;
  name: string;
  settings: Settings;
  sources: Source[];
  clips: Clip[];
  last_export: ExportReport | null;
  running: string | null;
  exported: boolean;
}

export interface ProjectSummary {
  id: string;
  name: string;
  clips: number;
  sources: number;
}

export interface Health {
  ok: boolean;
  ffmpeg: boolean;
  romanize_available: boolean;
  romanize_model: string;
  device: string;
  name: string;
}

export interface KeyStatus {
  configured: boolean; // an Anthropic API key is set for this server
  saved: boolean; // ...and it is also saved in backend/.env
  model: string; // the model that writes Roman Urdu
  verified?: boolean;
}

export interface ModelOption {
  id: string;
  name: string;
  input_per_mtok: number | null; // USD per million tokens, null when unknown
  output_per_mtok: number | null;
  cheapest: boolean;
}

export interface ModelList {
  source: "api" | "builtin"; // "api" means the list came from the user's Anthropic account
  current: string;
  cheapest: string;
  models: ModelOption[];
}

export interface RomanEstimate {
  rows: number;
  batches: number;
  input_tokens: number;
  output_tokens: number;
  model: string;
  cost_usd: number | null;
}

export interface JobEvent {
  seq: number;
  stage: string;
  message: string | null;
  progress: number | null;
  done?: number;
  total?: number;
}
