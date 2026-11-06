# Troubleshooting

**First, run the checker.** It finds most problems and tells you the fix:

```bash
source .venv/bin/activate
python scripts/selfcheck.py
```

---

## Starting the app

| What you see | Why | Fix |
|---|---|---|
| `python3: command not found` | Python isn't installed | `sudo apt install python3 python3-venv` |
| `...ensurepip is not available` | Debian/Ubuntu ships Python without venv | `sudo apt install python3-venv` then redo step 2 of the README (or use the no-admin line in the README) |
| `Some required packages are not installed yet` | You skipped `pip install` or forgot to activate the venv | `source .venv/bin/activate` then `pip install -r requirements.txt` |
| `Port 8767 is busy, using 8768 instead` | Something else uses that port | Nothing to fix — use the address the app prints |
| Browser didn't open | Some Linux setups block auto-open | Open a browser yourself and go to `http://127.0.0.1:8767` |
| "The app's server isn't answering. Go back to the terminal…" | The terminal running `python app.py` was closed | Start it again with `python app.py` and reload the page |
| "The app couldn't load its settings" | The settings file is unreadable | Run `python scripts/selfcheck.py`; if needed delete `~/.job_hunt_copilot/config.json` |

---

## Adding your resume

| What you see | Why | Fix |
|---|---|---|
| "This PDF seems to be a scanned picture with no text layer" | The PDF is just an image | Export your resume again from Word/Google Docs as a text PDF, or paste the text |
| "Reading photos needs the free Tesseract OCR tool" | You dropped an image | Paste the text instead, or `sudo apt install tesseract-ocr` |
| "'.doc' files are not supported" | Old Word format | Save as `.docx` or paste the text |
| "This file doesn't look like a real PDF" | Damaged or renamed file | Open it in a PDF viewer and save again, or paste the text |
| "That file is bigger than 15 MB" | A resume shouldn't be that big | Export without large images, or paste the text |
| "Paste your whole resume first (it looks too short)" | Fewer than 100 characters | Paste the full resume |
| The text came out jumbled (columns mixed) | Two-column PDF layouts confuse text extraction | Paste the text from the original document instead |

---

## The match

| What you see | Why | Fix |
|---|---|---|
| "Paste the full job posting — the description and the requirements" | Fewer than 80 characters | Paste the whole posting, not just the title |
| Score seems too low | The posting uses words your resume doesn't, even for things you've done | Look at "Missing from your resume": if you've done it, add it in those words. The score counts words, not ability. |
| A skill shows as matched but the evidence line is weak | The resume mentions the word in passing | Add a stronger bullet about it |
| A skill I have isn't recognized | The app's skill list doesn't know that word yet | Add the posting's exact term to your Skills section; and please open an issue with the term so we can add it |
| "The posting didn't state years, degree, or certifications" | It really didn't, or it used unusual wording | Nothing to fix |

---

## Rewriting and the cover letter

| What you see | Why | Fix |
|---|---|---|
| "No AI selected — you'll get a checklist and a fill-in template" | You chose No AI | Settings → pick an AI option. The checklist is still useful. |
| "The AI returned something too short to be your resume, so here is a checklist instead" | The model gave a bad answer | Click **Try again**. If it keeps happening, try a bigger model (`qwen2.5:7b`) or a cloud key. |
| ⚠️ "New numbers appeared that weren't in your original" | The AI may have invented a figure | Find it in the green lines and delete or correct it. Never send a number you can't back up. |
| ⚠️ "New names or terms appeared" | The AI may have added a tool or company you didn't list | Same — check and remove |
| ⚠️ "The AI copied N lines from the job posting into your resume" | Small models sometimes paste the posting's duties as if you did them. The app caught and removed those lines. | Nothing to fix. If the rewrite now looks thin, click **Try again** or use a bigger model. |
| ⚠️ "Numbers / dates / tools from your original were dropped" | The AI cut a real bullet of yours | Look at the red lines in the before/after view and paste the good ones back in the clean copy |
| "The AI option has a problem: …" | The AI you picked can't be reached right now | Read the message after the colon — it names the fix. Settings → **Test** shows the same thing. |
| The pill at the top says "— problem" | Same as above, shown in short | Click the pill to open Settings and press **Test** |
| Rewrite takes 4+ minutes | Local AI on an older CPU | Wait, or use `llama3.2:1b` for speed / a cloud key for quality. You can switch tabs meanwhile. |
| The rewrite changed a date or employer | The model broke a rule | Use **Try again**, or fix by hand in the clean copy. The red/green view makes this easy to spot. |
| Letter sounds generic | Not much to go on | Add specifics in "Anything you want it to say" — why this company, a story, a gap to explain |

---

## Interview practice

| What you see | Why | Fix |
|---|---|---|
| 🎤 button is disabled | Your browser doesn't support speech input | Use Chrome, or just type |
| "Microphone didn't work" | Browser blocked the mic | Click the 🔒 icon in the address bar and allow the microphone |
| "Type or speak your answer first" | Empty box | Answer, then click Get feedback |
| Feedback seems basic | You're in No AI mode | Rules-based feedback checks length, numbers, "I" vs "we", and STAR parts. Turn on an AI option for coaching. |

---

## The AI (optional)

| What you see | Why | Fix |
|---|---|---|
| "Ollama isn't running (or isn't installed)" | Ollama not installed or not started | Install: `curl -fsSL https://ollama.com/install.sh \| sh` then `ollama pull llama3.2:3b`. If installed, run `ollama serve` in another terminal. |
| "Could not reach Ollama at http://127.0.0.1:11434" | Ollama was installed but isn't running right now | Open another terminal and run `ollama serve`. Leave it open. Then click **Test** again. |
| The rewrite stopped with "timed out" | The local model is slow on this computer | The app waits up to 15 minutes. Try a smaller model (`llama3.2:1b`) or close other heavy programs. |
| "Model '…' is not downloaded" | | `ollama pull llama3.2:3b` |
| "'…' is not a valid address" | Typo in the Ollama address | Use `http://127.0.0.1:11434` |
| "No API key saved. Paste your key in Settings." | Cloud option without a key | Settings → paste → Test → Save |
| "The API key was rejected" | Typo or expired key | Paste it again and click **Test** |
| Test says "ready" but Save says "isn't running" | An environment variable is overriding settings | Settings shows a note listing them; unset them and restart |

### Which model should I use?

| Model | RAM | Speed on CPU | Writing quality |
|---|---|---|---|
| `llama3.2:1b` | ~2 GB | Fast | Basic |
| `llama3.2:3b` (default) | ~4 GB | Medium | OK |
| `qwen2.5:7b` / `llama3.1:8b` | ~8 GB | Slow | Good — worth it for the resume rewrite |

---

## Data

| | |
|---|---|
| Where is my data? | `~/.job_hunt_copilot/` — `resume.txt`, one JSON file per job in `apps/`, and `config.json` |
| Delete everything | My jobs → **Delete all saved jobs and my resume**, or delete the folder |
| Move the data folder | `JOBHUNT_DATA_DIR=/some/folder python app.py` |

## Still stuck?

1. Run `python app.py --verbose` and look at the terminal.
2. Open an issue on GitHub with the output of `python scripts/selfcheck.py` (no resume text or keys in it).
