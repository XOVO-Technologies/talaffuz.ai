# Contributing to Talaffuz.ai

Thanks for helping. Bug reports, ideas, documentation fixes, tests and code are all welcome, and so are small changes. This page covers how to get a working copy, what to check before you open a pull request, and the few rules that keep the dataset format stable.

By taking part you agree to follow the [code of conduct](CODE_OF_CONDUCT.md). Your contributions are released under the project's [MIT license](LICENSE).

## Ways to help

- **Report a bug.** Open an issue with the bug template. The most useful reports include what you did, what you expected, what happened, and the version (`git rev-parse --short HEAD`).
- **Suggest a feature.** Open an issue with the feature template and describe the problem first. A short example of your recordings or your target format helps a lot.
- **Improve the docs.** The README, the in-app wording and the landing page in `site/` are all fair game. Plain, specific sentences beat clever ones.
- **Add tests.** Every format rule in the export has a test, and more edge cases are always useful.
- **Fix something.** Pick any open issue. For anything bigger than a small fix, comment on the issue first so two people do not build the same thing.

## Set up a working copy

You need Windows 10 or 11 with PowerShell, [uv](https://docs.astral.sh/uv/), [Node.js](https://nodejs.org/) 20.19 or newer (or 22.12 or newer), and Git. Linux and macOS work with the manual commands in the README.

```powershell
git clone https://github.com/<your-username>/talaffuz.ai.git
cd talaffuz.ai
./setup.ps1 -SkipModels      # Python 3.12 environment, npm packages, built UI; skips the 1.6 GB model download
./start.ps1 -Dev             # API with reload on :8000, UI with hot reload on :5173
```

The Whisper model downloads the first time you press Start in the app. Run `./setup.ps1` without `-SkipModels` if you want it up front.

## Before you open a pull request

Run both checks. They are the same ones to run after any change.

```powershell
backend/.venv/Scripts/python.exe -m pytest backend
cd frontend; npm run build          # also type-checks the UI
```

Then look over this list:

- The change does one thing. Unrelated clean-up goes in its own pull request.
- New behaviour has a test. A change to anything in `backend/app/pipeline/export.py` needs a test in `backend/tests/test_export.py`.
- Screenshots are attached for any visible UI change, at desktop and phone width.
- The README or the in-app text is updated if the behaviour changed.
- No secrets are committed. `backend/.env` is ignored by Git, and API keys never go anywhere else.

## The rules that matter most

**The dataset format is a contract.** Training code downstream reads these files, so the layout stays fixed: `urdu_NNNNNN.wav` files that are mono 16-bit PCM, a `metadata.csv` that is UTF-8 without a byte-order mark with no header and three `|`-separated fields per line, and a `metadata.xlsx` with a `Final` formula column. A row's wav, Urdu text and Roman Urdu always belong together. If a change touches the format, say so in the pull request and cover it with tests.

**Backend conventions:**

- Heavy imports (`torch`, `demucs`, `faster_whisper`, `silero_vad`) stay inside functions so the API starts fast and the tests stay light.
- Change project state only through `store.edit(pid)` and read it with `store.get(pid)`.
- Pipeline code takes a `threading.Event` and raises `InterruptedError` when cancelled. Never swallow it.
- Open text files with `encoding="utf-8"`. Urdu breaks on the Windows default.
- Urdu text goes through `normalize_urdu` and Roman text through `clean_roman`.

**Frontend conventions:**

- Colours come from the CSS variables at the top of `frontend/src/styles.css`. Do not hard-code colours in components. The palette is light only: page `#edf1f5`, text `#222022` and one accent blue `#4778f3`.
- Fonts are Space Grotesk for headings and Urbanist for body text, both self-hosted in `frontend/src/assets/fonts/`. Urdu text keeps the Nastaliq font stack.
- Urdu text fields use `dir="rtl"` and `lang="ur"`. Roman Urdu fields are left to right.
- Uploads use the raw-body `PUT`, not `FormData`, so multi-GB files stream to disk.
- The clip table can hold hundreds of rows, so rows stay memoised and there is one shared `Audio` element.

**Writing.** User-facing text is plain and specific: no slogans, no filler words, no em dashes. Name real numbers and real steps.

**API keys.** The Anthropic key is read from the environment or the git-ignored `backend/.env`. It is never logged, never returned by the API, and never written anywhere else.

## Commit messages and pull requests

Write the commit message in the imperative ("Add path import for large recordings"), with a short first line and, when the reason is not obvious, a sentence on why. Keep pull requests small enough to review in one sitting. The pull request template asks for a summary, how you tested it and any screenshots.

## Questions

Open an issue and ask. If you are unsure whether an idea fits, ask before you build it.
