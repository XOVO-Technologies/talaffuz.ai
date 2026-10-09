"""Pydantic models shared by the store, pipeline and API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ProcessingSettings(BaseModel):
    # Numbering of the exported files: urdu_{start:06d}.wav onward. end_index caps the count; None keeps every clip.
    start_index: int = Field(1, ge=1, le=999999)
    end_index: int | None = Field(None, ge=1, le=999999)
    buffer_pct: int = Field(15, ge=0, le=100)  # extra clips to process so rejects can be replaced (needs end_index)

    sample_rate: Literal[16000, 22050, 24000, 44100] = 22050

    # Segmentation (seconds). Equal min/max switches the segmenter to fixed-length chunking
    # (strict clip_s windows, cut on the clock instead of at pauses) instead of pause-aware packing.
    min_clip_s: float = Field(2.5, ge=1.0, le=120)
    max_clip_s: float = Field(14.0, ge=3.0, le=120)
    merge_gap_s: float = Field(0.9, ge=0.1, le=3.0)
    vad_threshold: float = Field(0.5, ge=0.1, le=0.9)
    vad_min_silence_ms: int = Field(400, ge=100, le=2000)
    pad_ms: int = Field(250, ge=0, le=600)

    # Cleanup
    # "auto" probes a few clips per recording and only runs the (slow) music separator if music is found.
    remove_music: Literal["auto", "on", "off"] = "auto"
    denoise_strength: float = Field(0.5, ge=0.0, le=1.0)
    target_lufs: float = Field(-23.0, ge=-40.0, le=-10.0)

    # Transcription
    whisper_model: str = "large-v3-turbo"
    whisper_beam: int = Field(3, ge=1, le=8)
    auto_romanize: bool = True

    @field_validator("remove_music", mode="before")
    @classmethod
    def _legacy_bool(cls, v):
        # Early builds stored this as a boolean; keep those project files loadable.
        return ("on" if v else "off") if isinstance(v, bool) else v

    @model_validator(mode="after")
    def _check(self) -> "ProcessingSettings":
        if self.end_index is not None and self.end_index < self.start_index:
            raise ValueError("end_index must be >= start_index")
        if self.min_clip_s > self.max_clip_s:
            raise ValueError("min_clip_s must be smaller than (or equal to) max_clip_s")
        return self

    @property
    def capacity(self) -> int | None:
        """How many clips the dataset may hold, or None when there is no upper limit."""
        return None if self.end_index is None else self.end_index - self.start_index + 1


class SourceFile(BaseModel):
    id: str
    name: str
    path: str  # relative to the project directory
    size_bytes: int = 0
    status: Literal["uploaded", "analyzing", "analyzed", "error"] = "uploaded"
    duration_s: float | None = None
    work_wav: str | None = None  # 44.1 kHz mono working copy, relative to the project dir
    error: str | None = None


class Clip(BaseModel):
    id: str
    source_id: str
    order: int
    start_s: float
    end_s: float
    status: Literal["pending", "processed", "error"] = "pending"
    keep: bool = True
    urdu: str = ""
    roman: str = ""
    edited: bool = False
    duration_s: float = 0.0
    wav: str | None = None  # relative to the project dir
    asr_confidence: float | None = None
    snr_db: float | None = None
    flags: list[str] = Field(default_factory=list)
    error: str | None = None


class Project(BaseModel):
    id: str
    name: str
    created_at: float
    settings: ProcessingSettings = Field(default_factory=ProcessingSettings)
    sources: list[SourceFile] = Field(default_factory=list)
    clips: list[Clip] = Field(default_factory=list)
    last_export: dict | None = None


class ProjectCreate(BaseModel):
    name: str = "Urdu dataset"
    settings: ProcessingSettings | None = None


class ClipPatch(BaseModel):
    id: str | None = None  # only used by the bulk endpoint
    urdu: str | None = None
    roman: str | None = None
    keep: bool | None = None


class ProcessRequest(BaseModel):
    extra: int = Field(0, ge=0, le=2000)  # raise the processing goal by this many clips


class RomanizeRequest(BaseModel):
    only_missing: bool = True


class KeyRequest(BaseModel):
    key: str  # the Anthropic API key; checked by hand so a bad value is never echoed back in an error
    remember: bool = False  # also save it to the git-ignored backend/.env


class ModelRequest(BaseModel):
    model: str
    remember: bool = False  # also save it to the git-ignored backend/.env


class ImportRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1024)  # an audio file, or a folder of audio files


class ExportRequest(BaseModel):
    force: bool = False  # write the files even if validation reports errors
