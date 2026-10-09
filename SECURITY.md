# Security policy

## Reporting a problem

If you find a security problem, please report it privately so it can be fixed before it is public.

1. Open the repository's **Security** tab and choose **Report a vulnerability**.
2. Describe what you found, how to reproduce it, and what it affects.

If that option is not available, open an issue that says you have a security report and ask for a private way to send it. Leave the details out of the public issue.

You can expect an acknowledgement within a few days, and a fix or a clear plan as soon as the problem is understood.

## Supported versions

Fixes go into the latest version on the `main` branch. Please update before reporting.

## How the app handles sensitive data

- **It runs on your machine.** The server listens on `127.0.0.1` only, so other computers on your network cannot reach it. Recordings, clips and transcripts stay in the `data/` folder.
- **The Anthropic API key is private to you.** It is held in memory for the session and, only if you tick "Remember on this computer", saved in `backend/.env`, which Git ignores. The API never sends the key back to the browser, and it is never written to logs, project files or exports.
- **Only text leaves your machine for Roman Urdu.** When you use an API key or Claude Code, the Urdu sentences are sent to Anthropic. Audio is never sent.
- **Uploads and imports.** Files are copied into the project folder. The import-by-path feature only copies audio and video files.

## For contributors

Never commit keys, tokens or recordings. Keep secrets in `backend/.env`. If you accidentally commit one, revoke it first, then tell the maintainers.
