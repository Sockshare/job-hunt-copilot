"""AI tasks for Job Hunt Copilot, each with an honest no-AI fallback.

    tailor_resume(resume, posting, match)   -> rewritten resume + a diff the user can review line by line
    cover_letter(resume, posting, match, details) -> letter text
    grade_answer(question, answer, posting) -> feedback on a mock-interview answer

Rules the prompts enforce: never invent experience, employers, dates, degrees, or numbers.
The diff view makes any slip visible, and the UI tells the user to check every changed line.
"""

from __future__ import annotations

import difflib
import logging
import re

from .config import Settings
from .llm import ProviderError, extract_json, get_provider

log = logging.getLogger("job_hunt_copilot.ai")

TAILOR_SYSTEM = """You are a careful resume editor. You rewrite the candidate's OWN resume so it speaks to a specific job posting.
HARD RULES:
- Never invent experience, employers, job titles, dates, degrees, certifications, tools, or numbers. Only rephrase and reorder what is there.
- NEVER copy sentences or bullet points from the job posting into the resume. The posting describes what THEY want; the resume must only describe what the candidate HAS DONE. If a posting requirement is not shown in the resume, leave it out and list it under "could_not_address".
- Do not add tools or product names (e.g. BigQuery, Looker) that the resume does not already mention.
- You may add a keyword from the posting ONLY where the resume already shows that skill in other words.
- Keep every employer, title, and date exactly as written.
- Keep the same overall structure and roughly the same length.
- Prefer short bullets starting with a strong verb. Keep real numbers; do not add new ones.
Return ONE JSON object: {"resume": "<full rewritten resume text>", "changes": ["one short line per meaningful change, e.g. 'Reworded bullet 2 under Acme to mention SQL (you listed Postgres)'"], "could_not_address": ["posting requirements the resume genuinely does not show"]}"""

TAILOR_USER = """JOB POSTING:
\"\"\"
{posting}
\"\"\"

KEYWORDS THE POSTING ASKS FOR THAT THE RESUME DOES NOT MENTION: {missing}
KEYWORDS ALREADY MATCHED: {matched}

CANDIDATE'S RESUME (rewrite this, same facts):
\"\"\"
{resume}
\"\"\""""

LETTER_SYSTEM = """You write short, specific, human cover letters (under 280 words). Plain words. No clichés ("I am writing to express my interest", "team player", "passionate").
Use ONLY facts from the resume and the extra details provided. Never invent experience or numbers.
Shape: 1) one-line hook tying the candidate to this company/role, 2) two short paragraphs with 2–3 concrete examples that map to the posting's needs, 3) honest line about any gap if one is given, 4) short close with a specific ask.
Use [brackets] for anything unknown, like [Hiring Manager's name]. Return only the letter."""

LETTER_USER = """JOB POSTING:
\"\"\"
{posting}
\"\"\"

RESUME:
\"\"\"
{resume}
\"\"\"

Extra details from the candidate (why this job, anything to explain): {details}
Posting keywords the resume matches: {matched}
Tone: {tone}"""

GRADE_SYSTEM = """You are a friendly interview coach. Grade ONE answer to ONE interview question.
Be specific and kind. Return ONE JSON object:
{"score": 1-5, "strengths": ["..."], "improve": ["concrete, doable suggestions"], "better_answer_outline": "3-5 short bullet points the candidate could say, using only what they told you", "missing_star": ["Situation"|"Task"|"Action"|"Result" parts that were missing, if any]}"""

GRADE_USER = """JOB (for context): {title}
QUESTION: {question}
CANDIDATE'S ANSWER:
\"\"\"
{answer}
\"\"\""""


# ---------------------------------------------------------------------------
def _str_list(v, limit: int = 30) -> list[str]:
    """LLM JSON is sloppy: accept list/str/number/None, always return a clean list of strings."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip()][:limit] if v.strip() else []
    if isinstance(v, (int, float, bool)):
        return [str(v)]
    if isinstance(v, dict):
        v = list(v.values())
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()][:limit]
    return []


def diff_lines(before: str, after: str) -> list[dict]:
    """Line-level diff for the review UI: [{'type': 'same|removed|added', 'text': ...}]."""
    a = [ln.rstrip() for ln in before.replace("\r", "").split("\n")]
    b = [ln.rstrip() for ln in after.replace("\r", "").split("\n")]
    out: list[dict] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend({"type": "same", "text": ln} for ln in a[i1:i2])
        else:
            out.extend({"type": "removed", "text": ln} for ln in a[i1:i2])
            out.extend({"type": "added", "text": ln} for ln in b[j1:j2])
    return out


_NUM = re.compile(r"\d[\d,.%$kKmM+]*")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _norm_line(ln: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", ln.lower()).strip()


_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by", "from", "as", "is", "are", "be", "our", "your", "we", "you", "that", "this", "will", "across", "into"}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s", "e"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _content_words(n: str) -> set[str]:
    return {_stem(w) for w in n.split() if w not in _STOP and len(w) > 2}


def posting_leaks(after: str, posting: str, original: str = "") -> list[str]:
    """Lines in the rewritten resume that were lifted (verbatim OR lightly paraphrased) from the job
    posting — the #1 way small models fabricate experience. Lines that already existed in the user's
    original resume are never flagged, even if they happen to match the posting."""
    orig_lines = {_norm_line(ln.lstrip(" -•*")) for ln in original.split("\n")}
    post_lines = [_norm_line(ln.lstrip(" -•*")) for ln in posting.split("\n") if len(ln.split()) >= 3]
    post_blob = " " + " ".join(post_lines) + " "
    post_sets = [(pl, _content_words(pl)) for pl in post_lines if len(_content_words(pl)) >= 3]
    leaks = []
    for ln in after.split("\n"):
        n = _norm_line(ln.lstrip(" -•*"))
        if len(n.split()) < 3 or n in orig_lines:
            continue
        if n in post_lines:
            leaks.append(ln.strip())
            continue
        words = n.split()
        # 6-word verbatim shingle
        if len(words) >= 6 and any((" " + " ".join(words[i : i + 6]) + " ") in post_blob for i in range(len(words) - 5)):
            leaks.append(ln.strip())
            continue
        # paraphrase: ≥80% of this line's content words sit in ONE posting line (and it isn't just 2 shared words)
        cw = _content_words(n)
        if len(cw) >= 4:
            for _, ps in post_sets:
                if len(cw & ps) / len(cw) >= 0.8:
                    leaks.append(ln.strip())
                    break
    return leaks


_NUMBER_WORDS = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|dozen|half|double|triple)\b", re.I)
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9+#./-]{1,6}\b")


def _tool_terms(text: str) -> set[str]:
    """Tool/skill words found by the shared skills dictionary, as whole words from the text
    (so a prefix alias like "communicat" reports "communicated", not a stem)."""
    from .analysis import _COMPILED

    found = set()
    for pats in _COMPILED.values():
        for pat in pats:
            for m in pat.finditer(text):
                a, b = m.start(), m.end()
                while a > 0 and (text[a - 1].isalnum() or text[a - 1] in "+#"):
                    a -= 1
                while b < len(text) and (text[b].isalnum() or text[b] in "+#"):
                    b += 1
                term = text[a:b].strip().lower()
                if term:
                    found.add(term)
    return found


def fact_check(before: str, after: str, extra_known: str = "") -> list[str]:
    """Guard against invented facts: new numbers, number-words, years, acronyms, tool names, or
    capitalised names that weren't in the original. `extra_known` is text whose terms are allowed
    (e.g. the company/role lines of a posting when writing a cover letter)."""
    warnings = []
    before_all = before + "\n" + extra_known
    new_numwords = sorted({w.lower() for w in _NUMBER_WORDS.findall(after)} - {w.lower() for w in _NUMBER_WORDS.findall(before_all)})
    if new_numwords:
        warnings.append("New quantities written as words appeared: " + ", ".join(new_numwords[:8]) + ". Make sure each one is true.")
    new_tools = sorted(_tool_terms(after) - _tool_terms(before_all))
    if new_tools:
        warnings.append("New tools or skills appeared that your original never mentioned: " + ", ".join(new_tools[:10]) + ". Remove any you don't actually have.")
    new_acr = sorted({a for a in _ACRONYM.findall(after)} - {a for a in _ACRONYM.findall(before_all)} - {"I", "A", "STAR", "CV", "PDF", "US", "USA", "UK", "EU", "OK"})
    if new_acr:
        warnings.append("New acronyms appeared: " + ", ".join(new_acr[:10]) + ". Check them.")
    nums_before = set(_NUM.findall(before_all))
    new_nums = sorted(n for n in set(_NUM.findall(after)) - nums_before if len(n) > 1)
    if new_nums:
        warnings.append("New numbers appeared that weren't in your original: " + ", ".join(new_nums[:8]) + ". Make sure each one is true.")
    years_before = set(re.findall(r"\b(?:19|20)\d{2}\b", before_all))
    new_years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", after)) - years_before)
    if new_years:
        warnings.append("A year changed or was added (" + ", ".join(new_years) + "). Check all dates.")
    # Capitalised words that appear mid-sentence are names/products; ones only at a line start are
    # almost always verbs ("Produced", "Streamlined") and would cry wolf.
    def mid_caps(text: str) -> set[str]:
        out = set()
        for ln in text.split("\n"):
            # split sentences too, so the word after a period is treated as a sentence start
            for sent in re.split(r"(?<=[.!?])\s+", ln):
                words = re.findall(r"[A-Za-z][A-Za-z]*", sent)  # punctuation stripped: "Looker." -> "Looker"
                for w in words[1:]:
                    if re.match(r"^[A-Z][a-z]{3,}$", w):
                        out.add(w)
        return out

    headings = {"Experience", "Education", "Skills", "Summary", "Professional", "Certifications", "Projects", "Technical", "Core", "Competencies", "Work", "History",
                "Dear", "Hiring", "Manager", "Sincerely", "Best", "Regards", "Thank", "However", "Additionally", "With", "This", "That", "These", "Your", "Phone", "Email", "Name"}
    known_lower = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", before_all)} | {h.lower() for h in headings}
    new_caps = sorted(w for w in mid_caps(after) if w.lower() not in known_lower)
    if new_caps:
        warnings.append("New names or terms appeared: " + ", ".join(new_caps[:10]) + ". Remove any you don't actually have.")
    return warnings


def dropped_facts(before: str, after: str) -> list[str]:
    """The opposite guard: real things from the ORIGINAL that the rewrite silently lost
    (numbers, years, tools, mid-sentence names). Small models drop bullets; the user should know."""
    warnings = []
    lost_nums = sorted(n for n in set(_NUM.findall(before)) - set(_NUM.findall(after)) if len(n) > 1)
    lost_years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", before)) - set(re.findall(r"\b(?:19|20)\d{2}\b", after)))
    lost_nums = [n for n in lost_nums if n not in lost_years]
    lost_tools = sorted(_tool_terms(before) - _tool_terms(after))
    after_lower = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", after)}
    lost_names: set[str] = set()
    for ln in before.split("\n"):
        words = re.findall(r"[A-Za-z][A-Za-z]*", ln)
        for w in words[1:]:  # mid-line capitalised words only (line-start words are usually verbs)
            if re.match(r"^[A-Z][a-z]{3,}$", w) and w.lower() not in after_lower:
                lost_names.add(w)
    lost_names = sorted(lost_names)
    if lost_years:
        warnings.append("Dates from your original are missing in the rewrite (" + ", ".join(lost_years[:8]) + "). Put them back if the job is still listed.")
    if lost_nums:
        warnings.append("Numbers from your original were dropped: " + ", ".join(lost_nums[:8]) + ". Real results with numbers are your strongest lines — add them back.")
    if lost_tools:
        warnings.append("Tools or skills from your original are gone: " + ", ".join(lost_tools[:10]) + ". Add them back if they matter for this job.")
    if lost_names:
        warnings.append("Names from your original (employers, products, schools) are missing: " + ", ".join(lost_names[:8]) + ". Check nothing important was cut.")
    return warnings


def _template_tailor(resume: str, match: dict) -> dict:
    """No AI: give the user a concrete checklist instead of pretending to rewrite."""
    tips = []
    for m in match["missing"][:8]:
        asked = m["asked"][0] if m["asked"] else ""
        tips.append(f"Posting wants **{m['skill']}**" + (f" (\"{asked[:90]}\")" if asked else "") + ". If you've done this, add a bullet that uses the words \"{0}\" and a result with a number.".format(m["skill"]))
    for a in match["ats"]:
        if a["level"] in ("warn", "bad"):
            tips.append(f"{a['title']}: {a['detail']}")
    return {"resume": resume, "changes": [], "could_not_address": [m["skill"] for m in match["missing"]], "checklist": tips, "engine": "checklist"}


def tailor_resume(resume: str, posting: str, match: dict, settings: Settings) -> dict:
    provider = get_provider(settings)
    if provider.name == "offline":
        return _template_tailor(resume, match)
    try:
        raw = provider.complete(
            TAILOR_SYSTEM,
            TAILOR_USER.format(posting=posting[:8000], resume=resume[:9000], missing=", ".join(match["missing_keywords"][:12]) or "none", matched=", ".join(m["skill"] for m in match["matched"][:12]) or "none"),
            want_json=True,
        )
    except ProviderError as exc:
        out = _template_tailor(resume, match)
        out["error"] = str(exc)
        return out
    parsed = extract_json(raw) or {}
    new = str(parsed.get("resume") or "").strip()
    if len(new) < len(resume) * 0.5:
        out = _template_tailor(resume, match)
        out["error"] = "The AI returned something too short to be your resume, so here is a checklist instead. Try again."
        return out
    leaks = posting_leaks(new, posting, original=resume)
    if leaks:
        # Strip the lifted lines rather than hand the user fabricated experience.
        kept = [ln for ln in new.split("\n") if ln.strip() not in {l for l in leaks}]
        new = "\n".join(kept)
    changes = _str_list(parsed.get("changes"), 30)
    cna = _str_list(parsed.get("could_not_address"), 15)
    warnings = fact_check(resume, new) + dropped_facts(resume, new)
    if leaks:
        warnings.insert(0, f"The AI copied {len(leaks)} line{'s' if len(leaks) != 1 else ''} from the job posting into your resume as if you had done them. Those lines were removed. If the rest looks thin, click Try again or use a bigger model.")
    if len(new) < len(resume) * 0.5:
        out = _template_tailor(resume, match)
        out["error"] = "The AI mostly copied the job posting instead of rewriting your resume, so here is a checklist instead. Try again, or try a bigger model (qwen2.5:7b) or a cloud key."
        return out
    return {"resume": new, "changes": changes, "could_not_address": cna, "diff": diff_lines(resume, new), "warnings": warnings, "engine": provider.name, "leaks_removed": len(leaks)}


def _template_letter(resume: str, match: dict, details: str, tone: str) -> str:
    title = match.get("title") or "the [Job Title] role"
    top = [m["skill"] for m in match["matched"][:3]]
    body = f"""Dear [Hiring Manager's name],

I'm applying for {title}. [One sentence on why this company or role, in your own words.]

In my recent work I have {", ".join(top[:-1]) + " and " + top[-1] if len(top) > 1 else (top[0] if top else "[your main relevant skill]")} experience. For example: [a specific thing you did, with a number — e.g. "cut report turnaround from 3 days to 1" or "handled 40+ customer calls a day"]. [A second example that matches something in the posting.]

{details.strip() if details.strip() else "[Optional: one honest line about anything they might wonder about — a gap, a career change, relocation.]"}

I'd welcome a short conversation about how I can help. Thank you for your time.

Sincerely,
[Your name]
[Phone] · [Email]"""
    return body


def cover_letter(resume: str, posting: str, match: dict, details: str, tone: str, settings: Settings) -> dict:
    provider = get_provider(settings)
    if provider.name == "offline":
        return {"text": _template_letter(resume, match, details, tone), "engine": "template"}
    try:
        text = provider.complete(LETTER_SYSTEM, LETTER_USER.format(posting=posting[:6000], resume=resume[:7000], details=details.strip() or "none", matched=", ".join(m["skill"] for m in match["matched"][:10]) or "none", tone=tone))
        header = "\n".join(posting.split("\n")[:8])  # title / company / location — not the requirements list
        return {"text": text.strip(), "engine": provider.name, "warnings": fact_check(resume + "\n" + details, text, extra_known=header)}
    except ProviderError as exc:
        return {"text": _template_letter(resume, match, details, tone), "engine": "template", "error": str(exc)}


def _template_grade(question: str, answer: str) -> dict:
    words = len(answer.split())
    low = answer.lower()
    star = {"Situation": any(w in low for w in ("when", "at my", "we had", "there was", "last year", "in my role")), "Task": any(w in low for w in ("i needed", "my job was", "i had to", "goal", "asked to")), "Action": any(w in low for w in ("i ", "so i", "i decided", "i built", "i talked", "i called")), "Result": any(w in low for w in ("result", "ended up", "so that", "which led", "%", "saved", "increased", "reduced", "improved"))}
    missing = [k for k, v in star.items() if not v]
    strengths, improve = [], []
    if words >= 60:
        strengths.append("Good length — you gave real detail.")
    else:
        improve.append(f"Only about {words} words. Aim for 60–150: a short story with a beginning, what you did, and how it ended.")
    if not missing:
        strengths.append("You covered the situation, what you did, and the result.")
    if re.search(r"\d", answer):
        strengths.append("You used a number — that makes it concrete.")
    else:
        improve.append("Add a number if you can: how many, how much, how long.")
    if "we " in low and " i " not in f" {low} ":
        improve.append("Say 'I' more than 'we' — they want to know what *you* did.")
    if any(w in low for w in ("um", "like,", "you know")):
        improve.append("Trim filler words.")
    score = max(1, min(5, 3 + (1 if words >= 60 else -1) + (1 if not missing else 0) + (1 if re.search(r"\d", answer) else 0) - (1 if len(missing) >= 3 else 0)))
    return {"score": score, "strengths": strengths or ["You answered the question directly."], "improve": improve or ["Practice it out loud once or twice until it flows."], "better_answer_outline": "• Set the scene in one sentence\n• Say what you had to do\n• 2–3 things you did, in order\n• The result, with a number if possible\n• One line on what you learned", "missing_star": missing, "engine": "rules"}


def grade_answer(question: str, answer: str, title: str, settings: Settings) -> dict:
    if not answer.strip():
        return {"score": 0, "strengths": [], "improve": ["Type or say your answer first."], "better_answer_outline": "", "missing_star": [], "engine": "none"}
    provider = get_provider(settings)
    if provider.name == "offline":
        return _template_grade(question, answer)
    try:
        raw = provider.complete(GRADE_SYSTEM, GRADE_USER.format(title=title or "the role", question=question[:300], answer=answer[:3000]), want_json=True)
    except ProviderError as exc:
        out = _template_grade(question, answer)
        out["error"] = str(exc)
        return out
    parsed = extract_json(raw) or {}
    try:
        score = int(parsed.get("score", 3))
    except (TypeError, ValueError):
        score = 3
    return {
        "score": max(1, min(5, score)),
        "strengths": _str_list(parsed.get("strengths"), 5) or ["You answered the question."],
        "improve": _str_list(parsed.get("improve"), 5),
        "better_answer_outline": "\n".join(_str_list(parsed.get("better_answer_outline"), 8)) if not isinstance(parsed.get("better_answer_outline"), str) else parsed.get("better_answer_outline", ""),
        "missing_star": [x for x in _str_list(parsed.get("missing_star"), 4) if x in ("Situation", "Task", "Action", "Result")],
        "engine": provider.name,
    }
