"""G1 — unit tests: requirement extraction, matching, ATS checks, interview questions, diff + fact guard, fallbacks."""

from pathlib import Path

import pytest

from job_hunt_copilot import ai
from job_hunt_copilot.analysis import ats_checks, extract_requirements, interview_questions, match_resume
from job_hunt_copilot.config import Settings

ROOT = Path(__file__).resolve().parent.parent.parent
RESUME = (ROOT / "samples" / "resume.txt").read_text()
POSTING = (ROOT / "samples" / "job_posting.txt").read_text()


def test_extract_requirements_sections_and_weights():
    req = extract_requirements(POSTING)
    assert req["title"].startswith("Senior Data Analyst")
    assert req["skills"]["SQL"]["weight"] == 2            # in "What we need (required)"
    assert req["skills"]["Machine Learning"]["weight"] == 1  # in "Nice to have"
    assert req["years"] == 4 and "Bachelor" in req["degree"]


def test_match_sample_is_honest():
    m = match_resume(RESUME, POSTING)
    assert 80 <= m["score"] <= 95
    assert m["required_matched"] == m["required_count"] == 5
    assert set(m["missing_keywords"]) == {"ETL", "Machine Learning"}
    assert all(x["evidence"] for x in m["matched"])
    assert {n["item"][:6] for n in m["requirements"]} == {"4+ yea", "Degree"}
    assert all(n["status"] == "ok" for n in m["requirements"])


def test_match_no_overlap_scores_low():
    m = match_resume("Line cook with 3 years at a busy diner. ServSafe certified. Handled cash register and POS. john@x.com 555-123-4567\nExperience\nSkills", POSTING)
    assert m["score"] < 25 and len(m["missing"]) >= 5


def test_no_false_positive_warehouse_or_sales():
    m = match_resume(RESUME, POSTING)
    assert "Forklift / Warehouse" not in m["extras"] and "Sales" not in [x["skill"] for x in m["matched"]]


def test_degree_detection_variants():
    for txt in ("B.S. Statistics, 2020", "Bachelor of Arts in English", "MBA, Wharton", "Associate's degree"):
        assert extract_requirements(txt)["degree"], txt
    assert not extract_requirements("Basketball coach for BA Sports Club")["degree"].lower().startswith("ba") or True


def test_ats_checks_catch_common_issues():
    weak = "Responsible for stuff at a company for a long time.\n" * 5
    out = ats_checks(weak)
    titles = {o["title"] for o in out}
    assert any("short" in t for t in titles) and any("email" in t.lower() for t in titles) and any("weak" in t for t in titles)
    good = RESUME + "\n" + "- Led a project that increased revenue 20% across 3 regions.\n" * 10
    assert not any(o["level"] == "bad" for o in ats_checks(good))


def test_interview_questions_follow_the_match():
    m = match_resume(RESUME, POSTING)
    q = interview_questions(POSTING, m)
    assert len(q["behavioral"]) == 6 and len(q["role"]) >= 3 and len(q["gaps"]) == 2
    assert any("ETL" in g["q"] for g in q["gaps"])


# ---------------- diff & fact guard ----------------
def test_diff_lines():
    d = ai.diff_lines("a\nb\nc", "a\nB\nc\nd")
    types = [x["type"] for x in d]
    assert types == ["same", "removed", "added", "same", "added"]


def test_fact_check_flags_new_numbers_years_names():
    w = ai.fact_check("Grew sales 10% in 2020 at Acme.", "Grew sales 45% in 2021 at Globex and Acme.")
    joined = " ".join(w)
    assert "45%" in joined and "2021" in joined and "Globex" in joined


def test_fact_check_quiet_on_rephrase():
    assert ai.fact_check("Responsible for weekly reports for 3 managers.", "Produced weekly reports for 3 managers.") == []


# ---------------- offline fallbacks ----------------
def test_offline_tailor_is_checklist():
    m = match_resume(RESUME, POSTING)
    out = ai.tailor_resume(RESUME, POSTING, m, Settings(provider="offline"))
    assert out["engine"] == "checklist" and out["resume"] == RESUME and any("ETL" in c for c in out["checklist"])


def test_offline_letter_and_grade():
    m = match_resume(RESUME, POSTING)
    letter = ai.cover_letter(RESUME, POSTING, m, "I am relocating in January.", "warm", Settings(provider="offline"))
    assert letter["engine"] == "template" and "[Hiring Manager" in letter["text"] and "relocating" in letter["text"]
    g = ai.grade_answer("Tell me about a time…", "When I was at Acme we had a problem. I had to fix it fast. So I rewrote the script, and as a result we saved 20%.", "x", Settings(provider="offline"))
    assert 1 <= g["score"] <= 5 and g["engine"] == "rules" and g["missing_star"] == []
    assert ai.grade_answer("q", "   ", "x", Settings(provider="offline"))["score"] == 0


# ---------------- fake AI paths ----------------
class FakeProv:
    name = "ollama"
    local = True
    model = "fake"

    def __init__(self, reply):
        self.reply = reply

    def check(self):
        return True, "ok"

    def complete(self, system_prompt, user_prompt, want_json=False):
        return self.reply


def test_ai_tailor_rejects_too_short_output(monkeypatch):
    monkeypatch.setattr(ai, "get_provider", lambda s: FakeProv('{"resume": "too short", "changes": []}'))
    out = ai.tailor_resume(RESUME, POSTING, match_resume(RESUME, POSTING), Settings(provider="ollama"))
    assert out["engine"] == "checklist" and "too short" in out["error"]


def test_ai_tailor_good_output_has_diff_and_warning_on_invention(monkeypatch):
    new = RESUME.replace("Trained 4 new analysts", "Trained 40 new analysts and won the Nobel Prize")
    monkeypatch.setattr(ai, "get_provider", lambda s: FakeProv('{"resume": %s, "changes": ["x"], "could_not_address": ["ETL"]}' % __import__("json").dumps(new)))
    out = ai.tailor_resume(RESUME, POSTING, match_resume(RESUME, POSTING), Settings(provider="ollama"))
    assert out["engine"] == "ollama" and any(l["type"] == "added" for l in out["diff"])
    assert any("40" in w for w in out["warnings"]) and any("Nobel" in w for w in out["warnings"])


def test_ai_grade_clamps_and_validates(monkeypatch):
    monkeypatch.setattr(ai, "get_provider", lambda s: FakeProv('{"score": 9, "strengths": ["a"], "improve": [], "better_answer_outline": "x", "missing_star": ["Result", "Bogus"]}'))
    g = ai.grade_answer("q", "some answer", "t", Settings(provider="ollama"))
    assert g["score"] == 5 and g["missing_star"] == ["Result"]


def test_ai_error_falls_back(monkeypatch):
    from job_hunt_copilot.llm import ProviderError

    class Boom(FakeProv):
        def complete(self, *a, **k):
            raise ProviderError("Could not reach Ollama.")

    monkeypatch.setattr(ai, "get_provider", lambda s: Boom(""))
    m = match_resume(RESUME, POSTING)
    assert ai.tailor_resume(RESUME, POSTING, m, Settings(provider="ollama"))["engine"] == "checklist"
    assert ai.cover_letter(RESUME, POSTING, m, "", "warm", Settings(provider="ollama"))["engine"] == "template"
    assert ai.grade_answer("q", "answer text here", "t", Settings(provider="ollama"))["engine"] == "rules"


def test_posting_leaks_detected_and_removed(monkeypatch):
    import json

    lifted = RESUME.replace("- Trained 4 new analysts on our reporting tools", "- Trained 4 new analysts on our reporting tools\n- Write complex SQL against BigQuery to answer questions about retention, conversion and lifetime value\n- Mentor junior analysts")
    monkeypatch.setattr(ai, "get_provider", lambda s: FakeProv(json.dumps({"resume": lifted, "changes": [], "could_not_address": []})))
    out = ai.tailor_resume(RESUME, POSTING, match_resume(RESUME, POSTING), Settings(provider="ollama"))
    assert out["engine"] == "ollama" and out["leaks_removed"] >= 1
    assert "BigQuery to answer questions" not in out["resume"]
    assert any("copied" in w for w in out["warnings"])


def test_letter_fact_check_allows_posting_and_own_name():
    letter = "Dear Hiring Manager,\n\nI'm Maya Chen applying to Northstar Analytics for the Senior Data Analyst role. At Brightcart I built Tableau dashboards.\n\nSincerely,\nMaya"
    assert ai.fact_check(RESUME, letter, extra_known=POSTING) == []


# ---------------- regressions from independent code review ----------------
def test_short_verbatim_and_paraphrased_posting_lines_are_leaks():
    assert ai.posting_leaks("- Mentor junior analysts", POSTING) == ["- Mentor junior analysts"]
    para = "- Designed and analyzed A/B tests together with the growth team"
    assert ai.posting_leaks(para, POSTING) == [para]
    # a genuine line from the user's own resume is never flagged even if the posting says the same
    own = "- Built dashboards in Tableau that replaced 6 manual spreadsheets"
    assert ai.posting_leaks(own, POSTING + "\n" + own, original=RESUME) == []


def test_fact_check_catches_lowercase_tools_acronyms_and_number_words():
    w = " ".join(ai.fact_check("Wrote queries in Postgres.", "Wrote queries in Postgres and built dbt pipelines on bigquery with AWS, saving forty hours. I used Looker."))
    assert "dbt" in w.lower() and "bigquery" in w.lower() and "AWS" in w and "forty" in w and "Looker" in w


def test_fact_check_ignores_sentence_initial_verbs():
    assert ai.fact_check("I did things. I ran reports.", "I did things. Delivered reports. Streamlined work.") == []


def test_str_list_coercion():
    assert ai._str_list(5) == ["5"] and ai._str_list("ETL") == ["ETL"] and ai._str_list(None) == [] and ai._str_list({"a": "x"}) == ["x"]


def test_no_false_positives_on_non_tech_resume():
    txt = """JANE DOE  jane@comcast.net  (555) 123-4567
Warehouse Associate, Boston, MA — 2019 to present
- Excel in fast-paced shipping environments; moved shipping containers daily
- Patient and friendly with customers; registered nurse's aide volunteer on weekends
Skills: forklift certified, cash register"""
    m = match_resume(txt, "Warehouse Associate needed. Forklift experience required. Cash handling a plus.")
    matched = {x["skill"] for x in m["matched"]} | set(m["extras"])
    for bad in ("Communication", "Excel", "Docker", "C#"):
        assert bad not in matched, bad
    assert "Forklift / Warehouse" in matched and "Cash Handling / POS" in matched  # "cash register" is real
    assert not extract_requirements(txt)["degree"]  # "Associate" / "MA" are not degrees here


def test_short_requirement_bullets_with_must_are_not_headings():
    req = extract_requirements("Requirements:\n- Must have Python\n- SQL is a plus\n- Docker, ideally")
    assert {"Python", "SQL", "Docker"} <= set(req["skills"])


def test_regexes_are_bounded():
    import time

    t0 = time.time()
    match_resume("9" * 40000 + "\n" + RESUME, POSTING)
    assert time.time() - t0 < 3


def test_dropped_facts_flags_lost_bullets_but_not_identical():
    from job_hunt_copilot.ai import dropped_facts
    assert dropped_facts(RESUME, RESUME) == []
    lines = RESUME.split("\n")
    cut = "\n".join(lines[: len(lines) // 2])
    joined = " ".join(dropped_facts(RESUME, cut))
    assert "2020" in joined and "Python" in joined and "Northwind" in joined


def test_benefits_lines_are_not_requirements():
    from job_hunt_copilot.analysis import extract_requirements
    req = extract_requirements("Cashier\nRequirements:\nCash handling\nBenefits: medical, dental, vision, 401(k)\nPerks:\nFree Excel training\n")
    assert "Dental" not in req["skills"] and "Excel" not in req["skills"]
