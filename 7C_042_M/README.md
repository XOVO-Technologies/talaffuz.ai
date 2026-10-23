---
language:
- ur
pretty_name: "Urdu Speech Dataset - 7C_042_M"
task_categories:
- automatic-speech-recognition
configs:
- config_name: recordings
  data_dir: recordings
- config_name: sentences
  data_dir: sentences
  default: true
- config_name: words
  data_dir: words
---

# Urdu Speech Dataset - 7C_042_M

## Speaker

| Field | Value |
|---|---|
| speaker_id | 7C_042_M |
| name | Ali Raza |
| section | 7C |
| roll_no | 042 |
| gender | M |
| language | Urdu (ur), Urdu script + Roman Urdu |
| recording_device | Samsung Galaxy A14 (phone mic) |
| recording_place | Ghar ka kamra (quiet room) |
| recording_dates | 2026-10-13 to 2026-10-21 |
| audio_format | WAV, 16000 Hz, mono, 16-bit PCM |

## Counts

| Level | train | test | total |
|---|---|---|---|
| recordings | 4 | 1 | 5 |
| sentences | 9 | 3 | 12 |
| words | 51 | 16 | 67 |

## Split

Recordings R001-R400 are in train, R401-R500 in test. A recording's sentences and words are always in the same split as the recording.
(This sample has only 5 recordings: R001-R004 train, R005 test. The audio is placeholder beeps.)

## Notes

- Sentence start_sec/end_sec are measured in the recording file.
- Word start_sec/end_sec are also measured in the recording file.
