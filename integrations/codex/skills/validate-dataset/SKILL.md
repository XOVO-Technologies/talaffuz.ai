---
name: validate-dataset
description: Check an exported Talaffuz.ai dataset folder (wavs/ plus metadata.csv) against the fixed dataset format. Use before the user shares or merges a dataset, or after changing the export code.
---

# Validate a dataset

Folder to check: the one the user names. If none is given, use the newest `data/projects/*/output/dataset`.

Run:
`backend/.venv/Scripts/python.exe backend/scripts/validate_dataset.py <folder> --start <first> --end <last>`

Use the project's `settings.start_index` and `end_index` (omit `--end` when `end_index` is null; also `sample_rate` for `--sr`) from `project.json` next to
`output/`. The checker covers: UTF-8 without BOM, exactly three `|`-separated fields per line, `urdu_NNNNNN.wav`
names that are sequential with no gaps or repeats, a wav for every row and a row for every wav, Urdu script in
column 2, ASCII Roman Urdu in column 3, and mono 16-bit PCM at one sample rate.

Report the checker's output as is. Do not edit dataset files to make it pass; if it finds problems, say what they
are and which part of the pipeline (`backend/app/pipeline/export.py` or a clip in the Review table) to fix.
