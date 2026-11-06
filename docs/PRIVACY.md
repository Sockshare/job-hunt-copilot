# Privacy

Short version: **in "On my computer" and "No AI" modes, your resume never leaves your computer.**

## What goes where

| Mode | Your resume | The job posting | Your typed interview answers | Anything sent to the internet? |
|---|---|---|---|---|
| 🔒 No AI | Stays on your PC | Stays on your PC | Stay on your PC | **No** |
| 💻 On my computer (Ollama) | Sent to Ollama *on your own PC* | Same | Same | **No** |
| ☁️ OpenAI / compatible | **Sent to that company** when you click Rewrite / Write it / Get feedback | Same | Same | **Yes** |
| ☁️ Gemini | **Sent to Google** when you click those buttons | Same | Same | **Yes** |

The gap analysis, score, format checks and interview question list never use AI, so they never send anything in any mode.

The pill in the top-right corner shows which mode is on. So does the privacy line on the input screen.

## The microphone button (🎤)

Speech-to-text is done by your **browser**, not by this app. In Chrome, that means your audio is sent to Google's speech service while you talk. The app asks you to confirm this the first time you press 🎤. If you'd rather keep everything local, just type your answers — typing never leaves your PC in local modes.

## What the app stores on your computer

All in one folder: `~/.job_hunt_copilot/`

- `resume.txt` — your resume, if you left "Remember my resume" checked.
- `apps/<id>.json` — one file per job you compared: the posting, the match, any rewrite, letter and practice answers. Only if "Save the jobs I compare" is on (it is by default).
- `config.json` — your settings. If you typed in an API key, it is here too.

Only your user account can read these files. Delete the folder and everything is gone. Or use **My jobs → Delete all**.

## What the app never does

- It never uploads your resume to a job site or anywhere else.
- It never applies to jobs for you or contacts employers.
- It has no tracking. No analytics. No crash reports. It never "phones home."
- It listens only on `127.0.0.1`. Other computers on your network cannot reach it.
- A web page open in another tab cannot send data into the app (cross-site guard).

## How we check this

- One automated test blocks every network connection, then runs the match, the rewrite, the letter and the feedback in No-AI mode. If the app tried to reach the internet, the test would fail.
- Another test checks that files are created readable only by your user.

See `tests/smoke/test_api.py`.

## Cloud mode: what the AI company sees

If you choose OpenAI or Gemini, your resume text, the posting, and your typed answers are sent to them when you click an AI button. Read their privacy policy. Do not use cloud mode with information you are not allowed to share. "On my computer" is always available as a private choice.

## Keys

API keys live only in `config.json`. The browser never shows them in full. They are never written to logs.
