# Architecture (for developers)

Job Hunt Copilot is a local-first FastAPI app with a single static page. The analysis is deterministic; the LLM is used for three writing tasks, each wrapped in a review mechanism and a no-AI fallback.

```
Browser (127.0.0.1) ── static/index.html + app.js + app.css (vanilla JS, no CDN)
        │ JSON
server.py (FastAPI)
  /api/resume/file  ─► extract.py (pdf/docx/txt)        /api/resume/save|get  ─► ~/.job_hunt_copilot/resume.txt
  /api/match        ─► analysis.match_resume + interview_questions  ─► apps/<id>.json
  /api/tailor       ─► ai.tailor_resume  ─► diff_lines + fact_check
  /api/cover-letter ─► ai.cover_letter   ─► fact_check
  /api/grade        ─► ai.grade_answer
  /api/apps…        ─► per-application JSON store (status, answers)
llm/providers.py: Ollama | OpenAI-compatible | Gemini | Offline   (shared with sister projects)
```

## Design decisions

**Analysis without AI.** `analysis.py` holds a ~60-entry skills dictionary (canonical name → regex aliases), section-aware requirement extraction (a "Required"/"Nice to have" heading sets the weight for lines beneath it), evidence capture (the resume line that matched, bullets ranked above job-header lines), degree/years/cert detection, and plain ATS checks. The score is weighted keyword coverage — honest about what it is.

**Review, don't trust.** The rewrite returns a line-level diff (`difflib.SequenceMatcher`) and `fact_check()` flags numbers, years, and mid-sentence capitalised terms that appear in the output but not the input. Sentence-initial capitals are ignored (they're verbs). The UI forces the diff view first.

**Fallbacks that are still useful.** No-AI mode returns a concrete checklist (missing skill + the posting's wording + ATS fixes), a letter template pre-filled with top matched skills, and rules-based answer feedback (length, numbers, I-vs-we, STAR coverage).

**Local store.** One JSON per application under `~/.job_hunt_copilot/apps/`, created `0600`. IDs are 12-hex and validated (`isalnum`) before touching the filesystem.

**Security.** `TrustedHostMiddleware` (DNS rebinding) + an Origin/Sec-Fetch-Site guard on state-changing methods (CSRF). No remote access, so no auth.

## Testing

```
tests/unit/    requirement extraction, matching accuracy on the samples, false-positive guards, ATS checks, diff/fact-check, every fallback, fake-AI edge cases
tests/smoke/   API via TestClient, store lifecycle, uploads, path traversal, privacy (socket guard), cross-site guard, file permissions
tests/ui/      Playwright: first-run → input → all four panes → status → My jobs → settings; responsive overflow; screenshots
scripts/       selfcheck.py, readability_check.py, fresh_install_test.sh
```

## Extending

- New skill → one entry in `analysis.SKILLS` (specific aliases; use `\b` to avoid substring hits).
- New ATS check → append to `ats_checks()`.
- New role question → `analysis.SKILL_QUESTIONS[skill]`.
- Prompts live at the top of `ai.py`; keep the HARD RULES block.
