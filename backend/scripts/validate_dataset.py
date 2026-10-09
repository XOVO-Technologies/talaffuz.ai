"""Check a finished dataset folder against the team's format guide.

    python scripts/validate_dataset.py <dataset_dir> [--start 1] [--end N] [--sr 22050]

<dataset_dir> is the folder that holds wavs/ and metadata.csv. Exit code 1 if any error is found.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import soundfile as sf

NAME = re.compile(r"^urdu_(\d{6})\.wav$")
ARABIC = re.compile("[؀-ۿ]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset_dir", type=Path)
    ap.add_argument("--start", type=int, help="expected first file number")
    ap.add_argument("--end", type=int, help="expected last file number")
    ap.add_argument("--sr", type=int, help="expected sample rate")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    errors: list[str] = []
    warnings: list[str] = []
    root, wavs_dir, meta = args.dataset_dir, args.dataset_dir / "wavs", args.dataset_dir / "metadata.csv"
    if not wavs_dir.is_dir():
        errors.append(f"missing folder: {wavs_dir}")
    if not meta.is_file():
        errors.append(f"missing file: {meta}")
    if errors:
        print("\n".join("ERROR " + e for e in errors))
        return 1

    raw = meta.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("metadata.csv starts with a UTF-8 BOM (the first filename would be read wrongly)")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        print(f"ERROR metadata.csv is not valid UTF-8: {exc}")
        return 1

    seen: dict[str, int] = {}
    numbers: list[int] = []
    rates: set[int] = set()
    durations: list[float] = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            errors.append(f"line {n}: blank line")
            continue
        parts = line.split("|")
        if len(parts) != 3:
            errors.append(f"line {n}: expected 3 fields separated by '|', found {len(parts)}")
            continue
        name, urdu, roman = (p.strip() for p in parts)
        m = NAME.match(name)
        if not m:
            errors.append(f"line {n}: bad filename {name!r} (expected urdu_000001.wav style)")
            continue
        numbers.append(int(m.group(1)))
        if name in seen:
            errors.append(f"line {n}: {name} repeats line {seen[name]}")
        seen[name] = n
        if not urdu or not ARABIC.search(urdu):
            errors.append(f"line {n} ({name}): the Urdu sentence is empty or not Urdu script")
        if not roman:
            errors.append(f"line {n} ({name}): the Roman Urdu is empty")
        elif ARABIC.search(roman):
            errors.append(f"line {n} ({name}): Roman Urdu contains Urdu script")
        path = wavs_dir / name
        if not path.is_file():
            errors.append(f"line {n}: {name} is not in wavs/")
            continue
        info = sf.info(str(path))
        rates.add(info.samplerate)
        durations.append(info.frames / info.samplerate)
        if info.channels != 1:
            errors.append(f"{name}: {info.channels} channels (expected mono)")
        if info.subtype != "PCM_16":
            errors.append(f"{name}: {info.subtype} (expected PCM_16)")
        if not 1.0 <= durations[-1] <= 20.0:
            warnings.append(f"{name}: duration {durations[-1]:.1f} s is outside 1-20 s")

    on_disk = {p.name for p in wavs_dir.glob("*.wav")}
    for extra in sorted(on_disk - set(seen)):
        errors.append(f"wavs/{extra} has no row in metadata.csv")
    if numbers:
        expected = list(range(numbers[0], numbers[0] + len(numbers)))
        if numbers != expected:
            errors.append("filenames are not sequential in metadata.csv (gap, reorder or duplicate)")
        if args.start is not None and numbers[0] != args.start:
            errors.append(f"first file is {numbers[0]}, expected {args.start}")
        if args.end is not None and numbers[-1] != args.end:
            errors.append(f"last file is {numbers[-1]}, expected {args.end}")
    if len(rates) > 1:
        errors.append(f"mixed sample rates: {sorted(rates)}")
    if args.sr and rates and rates != {args.sr}:
        errors.append(f"sample rate is {sorted(rates)}, expected {args.sr}")

    for e in errors:
        print("ERROR  ", e)
    for w in warnings[:20]:
        print("WARNING", w)
    total = sum(durations)
    print(f"\n{len(lines)} rows, {len(on_disk)} wavs, {total / 60:.1f} min of audio, "
          f"sample rate {sorted(rates)}; {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
