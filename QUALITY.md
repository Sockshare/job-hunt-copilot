# Quality Report

Every release of Job Hunt Copilot must pass the nine gates below before it is pushed.

**Release:** 1.0.0  ·  **Platform tested:** Debian/Ubuntu-family Linux, Python 3.13, 8-core CPU, no GPU

## The nine gates

| # | Gate | What it proves | How to run it | Result |
|---|------|----------------|---------------|--------|
| G1 | Unit tests | Requirement extraction (required vs. nice-to-have sections, benefits lines ignored, frequency bumps); ~105-entry skills dictionary with false-positive guards (`R`, `C`, `Go`, `Excel` in prose); generic-term fallback for non-tech postings; evidence capture; degree/years/cert detection; resume health checks; diff; fact-check (invented numbers, years, tools, names) and dropped-facts check; posting-leak detection; every No-AI fallback | `pytest tests/unit` | ✅ pass |
| G2 | API smoke tests | Every endpoint; file upload (PDF/DOCX/TXT/image) with friendly 400s for bad, fake, huge and scanned files; saved-job CRUD and status; in-memory store when saving is off; cross-site write guard; id validation | `pytest tests/smoke` | ✅ pass |
| G3 | Fresh install | README's 3 commands work in a brand-new venv in a temp folder; app starts; the example resume + posting compare end to end | `bash scripts/fresh_install_test.sh` | ✅ pass |
| G4 | UI in a real browser | Playwright: first-run → paste → compare → every pane (fit, resume, letter, interview) → saved jobs → settings → help, at desktop/laptop/phone. Zero console errors, no `undefined`/`null` leaks, no horizontal overflow | `pytest tests/ui` | ✅ pass |
| G5 | Readability | README, User Guide, Troubleshooting, FAQ, Privacy all at grade ≤ 7 | `python scripts/readability_check.py` | ✅ pass (worst 6.2) |
| G6 | Privacy | Socket-blocked test: compare, interview questions, checklist and template all work with zero network in No-AI mode. `/api/status` never contacts Ollama or a cloud API unless asked (`?probe=1`). Config and saved jobs created `600`. Speech input asks consent and explains it is browser-provided | `pytest tests/smoke -k "network or private or cross_site or probe"` | ✅ pass |
| G7 | Independent novice-user review | Separate reviewer agent installed from the README and ran a nurse résumé, a retail résumé, odd file formats and the sample through every screen | report in review process | ✅ 2 P0 · 5 P1 (all fixed) · 17 P2 (14 fixed, 3 accepted) |
| G8 | Independent code & security review | Separate reviewer agent, 21 repro tests | report in review process | ✅ 3 P0 · 12 P1 (all fixed) · 15 P2 (11 fixed, 4 accepted) |
| G9 | Real local-AI run | Resume rewrite, cover letter and answer grading with real `llama3.2:3b` via Ollama on CPU | manual, recorded below | ✅ pass |

## What the reviews found and what changed

**Non-tech jobs scored like nonsense (G7 P0):** A nurse's résumé against a nursing posting scored 100% because the skills dictionary knew nothing about nursing, so there was nothing to miss. The dictionary now has ~45 non-tech entries (clinical, trades, retail, food service, education, admin, logistics, care work) and, when it still recognises fewer than four skills in a posting, it falls back to the posting's own key terms from its Requirements section. Nurse now scores 67% with sensible gaps (Pediatrics, Bilingual, Case management); retail 81%.

**Fabricated experience (G8 P0 / G7 P0):** The 3B local model copies lines from the job posting into the résumé as if the user did them. `posting_leaks()` detects lifted lines using 6-word shingles plus stemmed-paraphrase matching (never flagging the user's own original lines), removes them, and tells the user how many were removed. If what's left is under half the original length the app hands back the checklist instead of a hollow résumé. A second guard, `dropped_facts()`, warns when numbers, dates, tools or names from the original vanish in the rewrite.

**Saved-job store (G8 P0):** With "save history" off, jobs were written to disk anyway. Now they live in memory only and the list marks them "not saved". Writes are atomic (temp file + rename) under a lock; ids are validated as 12-hex before touching the filesystem; the posting URL is validated before it is persisted.

**Fact-check gaps (G8 P1):** lowercase tool names (`dbt`, `pandas`), acronyms, number-words ("three", "dozen") and punctuation-attached names ("Looker.") were slipping through. Cover-letter checks now treat only the posting's header (company/role lines) as known, not the whole posting. All regex inputs are bounded (400 chars/line, 2,000 lines) so a pathological paste can't stall the server.

**Privacy (G8):** `/api/status` no longer probes Ollama or sends the API key to a cloud endpoint unless Settings explicitly asks (`probe=1`); uploads are size-checked while streaming, not after; exact Origin-host check for cross-site writes; the microphone button asks consent the first time and explains that Chrome sends audio to Google's speech service.

**Usability (G7):** Reopening a saved job now brings back the rewrite, cover letter and last practice answer, not just the score; Delete asks first; "ATS checks" renamed "Resume health" everywhere; singular/plural grammar in health checks; the before/after view is taller; the troubleshooting guide gained rows for every message the app can show ("Could not reach Ollama", "— problem" pill, "copied N lines from the posting", "numbers were dropped", time-outs).

**Accepted (documented, not changed):**
- The score is keyword coverage, not a judgement of ability; the UI says so in words next to the ring.
- Two-column PDF layouts can come out jumbled; the guide says to paste the text instead.
- Speech-to-text is browser-provided (Chrome → Google); typing keeps everything local. Documented and gated behind a consent prompt.
- `uvicorn[standard]` is heavier than needed; kept for consistency with the sister projects.

## G9 record — real local model

- Model: `llama3.2:3b` via Ollama on an 8-core CPU, machine under test load (~4 tokens/s).
- Sample résumé + posting → **Rewrite (109 s):** the model pasted 4 lines from the posting into the résumé; `posting_leaks` removed all four and the warning appeared. It also dropped the "18% in Q3 2024" bullet and the Snowflake mention; `dropped_facts` flagged 2024, 18%, Snowflake and the two lost skills. New-term warnings named Communication / Stakeholder Management (which the model added). Nothing invented got through silently.
- **Cover letter (94 s):** readable, used the real Brightcart/dashboard facts; flagged "stakeholder" and "mentor" as new terms for the user to check.
- **Interview grading (27 s):** 4/5 stars, named the 18% figure as a strength and asked for more detail on the follow-through — a fair read.
- Repeat-token failures and 300 s time-outs seen in early runs are mitigated: `repeat_penalty 1.15`, automatic retry at lower temperature, and a 15-minute local read timeout. The UI tells users to expect 1–4 minutes and lets them switch tabs.

## Re-running everything

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt && python -m playwright install chromium
pytest                                   # G1, G2, G4, G6
bash scripts/fresh_install_test.sh       # G3
python scripts/readability_check.py      # G5
```
