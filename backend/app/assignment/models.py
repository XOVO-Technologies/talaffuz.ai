from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .ids import roll_text, speaker_id


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("|", "/")).strip()


class Experience(BaseModel):
    hours_recording: str = Field("", max_length=60)
    hours_cutting: str = Field("", max_length=60)
    hours_text: str = Field("", max_length=60)
    difficulty: int | None = Field(None, ge=1, le=5)
    difficulty_note: str = Field("", max_length=400)
    hardest: str = Field("", max_length=600)
    helpful: str = Field("", max_length=600)
    issues: str = Field("", max_length=600)
    redo: str = Field("", max_length=600)
    learned: str = Field("", max_length=600)

    @field_validator("*", mode="before")
    @classmethod
    def _tidy(cls, value):
        return one_line(value) if isinstance(value, str) else value


class Profile(BaseModel):
    name: str = Field("", max_length=120)
    section: Literal["7C", "7D", "7F", "7G", "7J"] = "7C"
    roll_no: int | None = Field(None, ge=1, le=999)
    gender: Literal["M", "F"] = "M"
    phone_model: str = Field("", max_length=120)
    location: str = Field("", max_length=120)
    date_from: str = Field("", max_length=10)
    date_to: str = Field("", max_length=10)
    source_path: str = Field("", max_length=1024)
    total: int = Field(500, ge=1, le=999)
    train: int = Field(400, ge=1, le=998)
    lowercase_roman: bool = True
    experience: Experience = Field(default_factory=Experience)

    @field_validator("name", "phone_model", "location", "date_from", "date_to", mode="before")
    @classmethod
    def _tidy(cls, value):
        return one_line(value) if isinstance(value, str) else value

    @property
    def sid(self) -> str:
        return speaker_id(self.section, self.roll_no or 0, self.gender)

    @property
    def roll(self) -> str:
        return roll_text(self.roll_no or 0)

    @property
    def dates(self) -> str:
        if self.date_from and self.date_to and self.date_from != self.date_to:
            return f"{self.date_from} to {self.date_to}"
        return self.date_from or self.date_to

    def missing(self) -> list[str]:
        gaps: list[str] = []
        if self.roll_no is None:
            gaps.append("Roll number")
        if not self.name:
            gaps.append("Your name")
        if not self.phone_model:
            gaps.append("Phone model")
        if not self.location:
            gaps.append("Place of recording")
        if not self.dates:
            gaps.append("Recording dates")
        if self.train >= self.total:
            gaps.append("Train count must be smaller than the total")
        exp = self.experience
        for label, value in (
            ("Time spent recording", exp.hours_recording),
            ("Time spent cutting audio", exp.hours_cutting),
            ("Time spent on text and metadata", exp.hours_text),
            ("Difficulty (1 to 5)", exp.difficulty),
            ("Hardest part", exp.hardest),
            ("What helped most", exp.helpful),
            ("Problems in the dataset", exp.issues),
            ("What you would do differently", exp.redo),
            ("What you learned", exp.learned),
        ):
            if value in ("", None):
                gaps.append(label)
        return gaps
