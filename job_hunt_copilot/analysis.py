"""Deterministic resume ↔ job-posting analysis. No AI needed.

    extract_requirements(posting)  -> skills/keywords the posting asks for, with weights
    match_resume(resume, posting)  -> score, matched/missing keywords, evidence lines, ATS checks
    interview_questions(posting, match) -> likely questions (behavioral + role-specific)
"""

from __future__ import annotations

import re
from collections import Counter

# A compact skills dictionary. Each entry: canonical name -> aliases (lowercase regex fragments).
SKILLS: dict[str, list[str]] = {
    # software / data
    "Python": [r"python"], "SQL": [r"\bsql\b", r"postgres", r"mysql", r"sqlite", r"t-sql"], "JavaScript": [r"javascript", r"\bjs\b", r"typescript"],
    "React": [r"\breact(?:\.?js)?\b(?!ed|ing|ion)"], "Node.js": [r"node\.?js"], "Java": [r"\bjava\b"], "C#": [r"\bc#", r"\basp\.net", r"\.net (framework|core)", r"\bdotnet\b"], "Go": [r"\bgolang\b", r"\bgo (developer|programming|language)\b"],
    "AWS": [r"\baws\b", r"amazon web services"], "Azure": [r"\bazure\b"], "GCP": [r"\bgcp\b", r"google cloud"], "Docker": [r"docker", r"containeriz"], "Kubernetes": [r"kubernetes", r"\bk8s\b"],
    "Git": [r"\bgit\b", r"github", r"gitlab"], "CI/CD": [r"ci/cd", r"continuous integration", r"jenkins", r"github actions"], "Linux": [r"\blinux\b", r"\bunix\b", r"bash"],
    "REST APIs": [r"\brest\b", r"restful", r"\bapis?\b"], "Testing": [r"unit test", r"pytest", r"\bjest\b", r"\btdd\b", r"test automation", r"\bqa (engineer|testing|automation)\b", r"quality assurance"],
    "Machine Learning": [r"machine learning", r"\bml\b", r"deep learning", r"neural net"], "LLMs / GenAI": [r"\bllm", r"generative ai", r"\bgenai\b", r"gpt", r"prompt"], "Data Analysis": [r"data analy", r"\banalytics\b", r"statistic", r"\bkpis?\b"],
    "Pandas": [r"pandas", r"numpy"], "Tableau / Power BI": [r"tableau", r"power ?bi", r"looker", r"dashboards?"], "Excel": [r"microsoft excel", r"ms excel", r"\bexcel\b(?!\s+(in|at|as)\b)", r"spreadsheets?", r"pivot tables?"], "ETL": [r"\betl\b", r"data pipeline", r"airflow", r"dbt"],
    "Spark": [r"\bspark\b", r"databricks"], "Snowflake / BigQuery": [r"snowflake", r"bigquery", r"redshift"], "Security": [r"\b(cyber|information|network|it|application|cloud) ?security\b", r"security (analyst|engineer|operations|clearance|audit)", r"\bsoc\b", r"\bsiem\b", r"vulnerabilit", r"\bnist\b", r"iso 27001", r"\bcmmc\b", r"penetration test", r"\bincident response\b"],
    "Networking": [r"\bnetworking\b", r"tcp/ip", r"firewalls?\b", r"\bvpn\b", r"\bcisco\b"], "Agile / Scrum": [r"\bagile\b", r"\bscrum\b", r"kanban", r"sprint"], "Jira": [r"\bjira\b", r"confluence"],
    # business / general
    "Project Management": [r"project management", r"\bpmp\b", r"project manager", r"roadmap"], "Stakeholder Management": [r"stakeholder", r"partner(?:ed)? with", r"\b(regional|product|marketing|sales|finance) (managers?|teams?|leaders?)\b", r"\bvp\b", r"executives?", r"leadership team", r"used by the"], "Communication": [r"communicat", r"presentations?\b", r"\bpresent(?:ed|ing)? (to|findings|results|at)\b", r"written and verbal", r"plain language", r"\breports? (?:for|to|used by)\b", r"\breadouts?\b", r"findings"],
    "Leadership": [r"leadership", r"\b(team|tech|shift) lead\b", r"\bled (a |the )?(team|project|group|\d)", r"mentor", r"managed a team", r"supervis", r"trained \d+", r"coach(ed|ing)?\b"], "Customer Service": [r"customer service", r"customer support", r"client[- ]facing", r"customer success"],
    "Sales": [r"\bsales (rep|representative|associate|team|quota|target|cycle|calls?|goals?)", r"\bquota\b", r"sales pipeline", r"\bcrm\b", r"salesforce", r"hubspot", r"closing deals", r"\bb2b\b", r"\bupsell"], "Marketing": [r"\bmarketing\b", r"\bseo\b", r"ad campaigns?", r"content strategy", r"social media"],
    "Budgeting / Finance": [r"budget", r"forecast", r"p&l", r"financial", r"accounting", r"quickbooks", r"\bgaap\b"], "Operations": [r"\boperations\b", r"logistics", r"supply chain"],
    "Writing / Documentation": [r"documentation", r"technical writing", r"copywriting", r"editing"], "Problem Solving": [r"problem[- ]solving", r"troubleshoot", r"root cause"],
    "Teamwork": [r"collaborat", r"cross[- ]functional", r"team player"], "Time Management": [r"time management", r"prioritiz", r"\bdeadlines?\b", r"fast[- ]paced", r"multi-?task"],
    "Design / UX": [r"\bux\b", r"\bui\b", r"figma", r"user research", r"wireframe"], "Healthcare": [r"\bhipaa\b", r"clinical", r"patient care", r"\bpatients\b", r"\behr\b", r"\bemr\b", r"\brn\b", r"\bcna\b", r"nurs(e|ing)"],
    "Teaching / Training": [r"\btrain(ed|ing) (new|staff|employees|team|students)", r"\bteaching\b", r"curriculum", r"onboarding", r"instructor", r"lesson plans?"], "Bilingual": [r"bilingual", r"spanish", r"fluent in"],
    "Microsoft Office": [r"microsoft office", r"ms office", r"microsoft word", r"\bpowerpoint\b", r"\boutlook\b", r"google (docs|workspace|sheets)"], "Scheduling / Admin": [r"\bscheduling\b", r"calendar management", r"administrative", r"data entry", r"\bfiling\b", r"front desk", r"receptionist", r"answering phones"],
    "Driver's License": [r"driver'?s license", r"valid license", r"\bcdl\b"], "Forklift / Warehouse": [r"forklift", r"pallet(?:s| jack)", r"shipping and receiving", r"warehouse (associate|worker|team|floor)"],
    "Food Safety": [r"servsafe", r"food (safety|handler)", r"\bhaccp\b"],
    # healthcare
    "Nursing License (RN/LPN)": [r"\brn\b", r"\blpn\b", r"\blvn\b", r"registered nurse", r"nursing license", r"\bbsn\b", r"\badn\b"],
    "CNA / Patient Care Aide": [r"\bcna\b", r"nursing assistant", r"patient care (tech|aide|assistant)", r"\bpca\b", r"\bhha\b", r"home health aide"],
    "BLS / CPR": [r"\bbls\b", r"\bcpr\b", r"basic life support", r"first aid"],
    "ACLS / PALS": [r"\bacls\b", r"\bpals\b", r"\bnrp\b", r"\btncc\b", r"\benpc\b"],
    "Emergency / Critical Care": [r"emergency (department|room|nursing)", r"\b(er|ed|icu|picu|nicu)\b", r"critical care", r"trauma", r"\btriage\b", r"\bcode (blue|response)"],
    "Pediatrics": [r"pediatric", r"\bpeds\b", r"children'?s hospital", r"infants?\b"],
    "Medication Administration": [r"administer(ed|ing)? medication", r"medication administration", r"\biv (fluids|therapy|insertion)", r"start(ed)? ivs?\b", r"dosage", r"\bpicc\b", r"central line"],
    "Epic / EHR Charting": [r"\bepic\b", r"\bcerner\b", r"\bmeditech\b", r"\behr\b", r"\bemr\b", r"charting", r"electronic health record"],
    "Patient Education": [r"patient (and family )?education", r"educat(e|ed|ing) (patients|families)", r"discharge (teaching|instructions)"],
    "Phlebotomy / Vitals": [r"phlebotomy", r"venipuncture", r"vital signs", r"\bvitals\b", r"\bekg\b", r"\becg\b"],
    "Medical Terminology / Coding": [r"medical terminology", r"\bicd-?10\b", r"\bcpt\b", r"medical (billing|coding)", r"insurance verification", r"prior authorization"],
    "Dental": [r"\bdental\b", r"\bhygienist\b", r"dentist"],
    "Pharmacy": [r"\bpharmacy tech", r"pharmacist", r"\bptcb\b", r"dispens(e|ing) (medication|prescription)"],
    # retail / hospitality / service
    "Retail Sales Floor": [r"sales floor", r"\bretail\b", r"merchandis", r"planogram", r"stocking shelves", r"restock"],
    "Customer Complaints / De-escalation": [r"de-?escalat", r"customer complaints", r"difficult customers", r"resolve(d)? (customer )?issues", r"returns and exchanges"],
    "Shift Supervision": [r"shift (lead|supervisor|manager)", r"supervis(e|ed|ing) (a )?(team|staff|crew|\d)", r"opening and closing", r"keyholder", r"key holder", r"assistant manager", r"store manager"],
    "Inventory / Stock Control": [r"\binventory\b", r"cycle counts?", r"stock (levels|control|takes?)", r"receiving (shipments|freight)", r"\bshrink(age)?\b"],
    "Barista / Food Prep": [r"barista", r"food prep", r"line cook", r"prep cook", r"\bgrill\b", r"kitchen", r"\bespresso\b"],
    "Serving / Front of House": [r"\bserver\b", r"waitress|waiter", r"front of house", r"\bhost(ess)?\b", r"table service", r"\btips\b"],
    "Bartending": [r"bartend", r"\btips certified\b", r"mixology", r"alcohol service"],
    "Housekeeping / Cleaning": [r"housekeep", r"\bjanitor", r"custodian", r"cleaning", r"sanitiz"],
    "Hotel Front Desk": [r"front desk", r"check-?in", r"guest services?", r"concierge", r"\bopera pms\b", r"reservations?\b"],
    # trades / logistics / driving
    "Forklift Certification": [r"forklift (certif|licens|operat)", r"\bosha\b forklift", r"powered industrial truck", r"\breach truck\b", r"\border picker\b"],
    "Picking / Packing / Shipping": [r"pick(ing)? and pack", r"order (picking|fulfillment)", r"\brf scanner\b", r"\bscanner\b", r"shipping (and|&) receiving", r"\bpallets?\b", r"load(ing)? (and|&) unload", r"\bups\b|\bfedex\b"],
    "Heavy Lifting": [r"lift (up to )?\d+ ?(lbs|pounds)", r"heavy lifting", r"physically demanding", r"stand for long periods"],
    "CDL / Commercial Driving": [r"\bcdl\b", r"class [ab] license", r"commercial driver", r"\bdot\b medical", r"delivery driver", r"route driver"],
    "Electrical": [r"electrician", r"electrical (work|systems|wiring)", r"\bnec\b", r"journeyman", r"\bconduit\b"],
    "Plumbing": [r"plumb(er|ing)", r"\bpipe ?fitt", r"water heaters?"],
    "HVAC": [r"\bhvac\b", r"\bepa 608\b", r"refrigerat", r"air condition"],
    "Carpentry / Construction": [r"carpent", r"framing", r"drywall", r"construction site", r"general labor", r"power tools", r"blueprints?"],
    "Welding / Fabrication": [r"weld(er|ing)", r"\bmig\b|\btig\b", r"fabricat", r"\baws d1\.1"],
    "Automotive Repair": [r"\base\b certified", r"automotive (technician|repair)", r"mechanic", r"oil changes?", r"brakes? and", r"diagnos(e|tic) (vehicles|engines)"],
    "Landscaping": [r"landscap", r"lawn care", r"mow(ing)?\b", r"irrigation", r"groundskeep"],
    "Security Guard": [r"security (guard|officer)", r"\bguard card\b", r"patrol", r"access control", r"loss prevention"],
    "OSHA / Workplace Safety": [r"\bosha\b", r"safety (training|protocols|procedures)", r"\bppe\b", r"lockout", r"hazmat", r"\bsds\b"],
    # office / admin / finance / people
    "Bookkeeping / Payroll": [r"bookkeep", r"payroll", r"accounts (payable|receivable)", r"\bap/ar\b", r"invoic", r"reconcil", r"quickbooks", r"\badp\b"],
    "Typing / Data Entry Speed": [r"\d+ ?wpm\b", r"typing speed", r"10-?key", r"data entry"],
    "Phone / Call Center": [r"call center", r"inbound calls?", r"outbound calls?", r"phone (support|etiquette)", r"multi-?line phone", r"switchboard"],
    "HR / Recruiting": [r"recruit(er|ing)", r"human resources", r"\bhr\b", r"onboard(ing)? (new )?(hires|employees)", r"benefits administration", r"\bats\b"],
    "Event Planning": [r"event (planning|coordination|coordinator)", r"\bcatering\b", r"\bvendors?\b"],
    "Legal / Paralegal": [r"paralegal", r"legal (assistant|research)", r"\blitigation\b", r"\bcontracts?\b review", r"e-?discovery", r"notary"],
    "Real Estate": [r"real estate license", r"\brealtor\b", r"\bmls\b", r"property management", r"leasing (agent|consultant)"],
    # education / care
    "Classroom Teaching": [r"classroom", r"teaching (license|certificate|credential)", r"lesson plans?", r"\bk-?12\b", r"\biep\b", r"special education", r"substitute teach"],
    "Childcare": [r"child ?care", r"daycare", r"nanny", r"babysit", r"\binfants?\b and toddlers", r"\bcda\b", r"early childhood"],
    "Elder / Home Care": [r"elder(ly)? care", r"home care", r"caregiver", r"assisted living", r"memory care", r"activities of daily living", r"\badls?\b"],
    "Social Work / Case Management": [r"case management", r"social work", r"\blcsw\b|\blmsw\b|\bmsw\b", r"crisis intervention", r"counsel(ing|or)"],
    "Fitness / Coaching": [r"personal train", r"\bcpt\b", r"group fitness", r"coach(ing|ed) (youth|athletes|team)"],
    # general
    "Reliability / Attendance": [r"reliab", r"punctual", r"dependable", r"attendance record", r"flexible (schedule|hours|availability)", r"weekends and holidays", r"nights and weekends"],
    "Physical Stamina": [r"on your feet", r"stand(ing)? for (long|extended)", r"walk(ing)? (long|all day)", r"outdoor work", r"all weather"], "Cash Handling / POS": [r"cash handling", r"point of sale", r"\bpos (system|terminal)s?\b", r"cash register"],
}
_COMPILED = {name: [re.compile(p, re.I) for p in pats] for name, pats in SKILLS.items()}

DEGREE_RE = re.compile(r"(\bbachelor'?s?\b|\bmaster'?s?\b|\bb\.[as]\.|\bm\.[as]\.|\b(?:ba|bs|ma|ms|bsc|msc)\b(?=,? (?:in|of) )|\bmba\b|\bph\.?d\b|\bassociate'?s? (?:degree|of)\b|\bhigh school diploma\b|\bged\b)", re.I)
YEARS_RE = re.compile(r"\b(\d{1,2})\+?\s?(?:-\s?\d{1,2}\s?)?years?", re.I)
CERT_RE = re.compile(r"\b(pmp|cpa|cissp|security\+|comptia [a-z+]+|aws certified[^,.;\n]*|rn\b|cna\b|cdl\b|servsafe|six sigma|scrum master|csm\b|ccna|itil)\b", re.I)
ACTION_VERBS = ("led", "built", "managed", "designed", "launched", "improved", "reduced", "increased", "delivered", "created", "implemented", "developed", "automated", "trained", "negotiated", "grew", "saved", "achieved", "coordinated", "resolved")
WEAK_PHRASES = ("responsible for", "duties included", "helped with", "worked on", "assisted with", "tasked with", "participated in")
NUMBER_RE = re.compile(r"\d+%|\$\d|\d+\s*(k|m|million|thousand|people|customers|clients|users|team|projects?|hours|days)\b|\b\d{2,}\b", re.I)

REQUIRED_WORDS = re.compile(r"\b(required|must have|must be|minimum|essential|need(?:ed)?|at least)\b", re.I)
PREFERRED_WORDS = re.compile(r"\b(preferred|nice to have|bonus|plus|ideally|desired|a plus)\b", re.I)
# "Benefits: medical, dental, 401(k)..." / "Perks: ..." / "We offer ..." / "Compensation: ..." / "Salary: ..."
BENEFITS_LINE = re.compile(r"^\W*(benefits|perks|we offer|compensation|salary|pay( range)?)\b", re.I)


MAX_LINE = 400
MAX_LINES = 2000


def _bound(text: str) -> str:
    """Cap line length and count so regexes can't be fed pathological input."""
    out = []
    for ln in text.replace("\r", "").split("\n")[:MAX_LINES]:
        out.append(ln[:MAX_LINE])
    return "\n".join(out)


def _lines(text: str) -> list[str]:
    return [ln.strip(" •-*\t·") for ln in _bound(text).split("\n") if ln.strip()]


GENERIC_STOP = set("""a an the and or of to in on for with at by from as is are be been being our your you we they it its this that these those will can may must should would could
about above after again against all also am any because before below between both but did do does doing down during each few further had has have having he her here hers him his how
if into just me more most my no nor not now off once only other out over own same she so some such than then there through too under until up very was were what when where which while who whom why
experience experienced required requirement requirements preferred prefer plus bonus nice ideally ideal minimum ability able strong strongly excellent good great demonstrated proven solid knowledge skills skill
years year team teams work working works role position job candidate candidates applicant successful including include includes related relevant equivalent degree field area areas environment
responsibilities responsibility duties duty perform performs performing provide provides providing support supporting supports ensure ensures ensuring maintain maintains maintaining assist assists assisting
within across using use used based level levels high highly new day daily weekly monthly hour hours shift shifts time full part opportunity company benefits salary pay location apply applicants
qualifications qualification summary description overview department department department hospital center clinic store office employer employees employee people others other
communication communicate written verbal detail details oriented organized organization organizational interpersonal professional professionalism attitude positive customer customers service
""".split())
MIN_RECOGNISED = 4  # below this many dictionary skills, also mine the posting's own words


def _posting_keywords(lines: list[str], section_of: dict[int, int]) -> dict[str, dict]:
    """Salient terms from the posting itself: acronyms/certifications (PALS, CDL), capitalised product
    names (Epic), and uncommon words in requirement bullets (triage, pediatric). Used for any job the
    skills dictionary doesn't cover well."""
    out: dict[str, dict] = {}
    for i, ln in enumerate(lines):
        weight = 2 if section_of.get(i) == 2 else 1
        for m in re.finditer(r"\b[A-Z][A-Z0-9&/-]{1,6}\b", ln):            # PALS, BLS, CDL, OSHA, RN
            tok = m.group(0)
            if tok in ("AND", "OR", "THE", "A", "I", "US", "USA", "PM", "AM", "PTO", "EOE", "LLC", "INC", "PST", "EST", "ET", "PT", "FT"):
                continue
            out.setdefault(tok, {"weight": 0, "mentions": 0, "lines": [], "kind": "term"})
            out[tok]["weight"] = max(out[tok]["weight"], weight); out[tok]["mentions"] += 1
            if len(out[tok]["lines"]) < 2:
                out[tok]["lines"].append(ln[:160])
        if section_of.get(i) in (0, 2):  # requirement / nice-to-have sections only
            words = re.findall(r"[A-Za-z][a-z]{4,}", ln)
            for j, w in enumerate(words):
                low = w.lower()
                if low in GENERIC_STOP or (j > 0 and w[0].isupper() is False and low.endswith(("ing", "ly"))):
                    continue
                if w[0].isupper() and j > 0:  # capitalised mid-line: product/brand (Epic, Salesforce)
                    key = w
                elif low in GENERIC_STOP:
                    continue
                else:
                    key = low
                out.setdefault(key, {"weight": 0, "mentions": 0, "lines": [], "kind": "term"})
                out[key]["weight"] = max(out[key]["weight"], weight); out[key]["mentions"] += 1
                if len(out[key]["lines"]) < 2 and ln[:160] not in out[key]["lines"]:
                    out[key]["lines"].append(ln[:160])
    # keep the most repeated / required ones
    ranked = sorted(out.items(), key=lambda kv: (-kv[1]["weight"], -kv[1]["mentions"], kv[0].lower()))
    return dict(ranked[:14])


def extract_requirements(posting: str) -> dict:
    """Skills with weight 2 (required) / 1 (preferred/mentioned), plus degree/years/certs if stated.
    If the dictionary recognises few skills (non-tech jobs), the posting's own key terms are added."""
    posting = _bound(posting)
    lines = _lines(posting)
    skills: dict[str, dict] = {}
    section_of: dict[int, int] = {}
    section = 1  # 1 = normal, 2 = inside a "Requirements/Must have" section, 0 = inside a "Nice to have" section
    # 3 = inside a Benefits/Perks section: never a requirement ("medical, dental" is not a skill)
    for i, ln in enumerate(lines):
        section_of[i] = section
        has_skill = any(p.search(ln) for pats in _COMPILED.values() for p in pats)
        is_heading = len(ln.split()) <= 6 and (ln.endswith(":") or not ln.endswith(".")) and not has_skill
        if is_heading and re.search(r"\b(require|must|qualifications|what we need|you have|you bring|minimum)\b", ln, re.I):
            section = 2
            continue
        if is_heading and re.search(r"\b(nice to have|preferred|bonus|plus|desired|ideal)\b", ln, re.I):
            section = 0
            continue
        if is_heading and re.search(r"\b(benefits|perks|compensation|salary|what we offer)\b", ln, re.I):
            section = 3
            continue
        if is_heading and re.search(r"\b(about (us|the company)|what you'll do|responsibilities)\b", ln, re.I):
            section = 1
            continue
        if section == 3 or BENEFITS_LINE.match(ln):
            continue
        if PREFERRED_WORDS.search(ln) and not REQUIRED_WORDS.search(ln):
            weight = 1
        elif section == 2 or REQUIRED_WORDS.search(ln):
            weight = 2
        else:
            weight = 1
        for name, pats in _COMPILED.items():
            if any(p.search(ln) for p in pats):
                cur = skills.setdefault(name, {"weight": 0, "mentions": 0, "lines": []})
                cur["weight"] = max(cur["weight"], weight)
                cur["mentions"] += 1
                if len(cur["lines"]) < 2:
                    cur["lines"].append(ln[:160])
    # Frequency bumps importance: mentioned 3+ times -> treat as required
    for v in skills.values():
        v.setdefault("kind", "skill")
        if v["mentions"] >= 3:
            v["weight"] = 2
    # Non-tech / unusual postings: add the posting's own key terms so the gap list is never empty or silly
    generic_used = False
    if len(skills) < MIN_RECOGNISED:
        for k, v in _posting_keywords(lines, section_of).items():
            if k not in skills and not any(k.lower() in name.lower() for name in skills):
                skills[k] = v
        generic_used = True
    degree = DEGREE_RE.search(posting)
    years = [int(m.group(1)) for m in YEARS_RE.finditer(posting) if int(m.group(1)) <= 30]
    certs = sorted({m.group(1).strip().title() for m in CERT_RE.finditer(posting)})
    title = ""
    for ln in lines[:6]:
        if 3 <= len(ln.split()) <= 10 and not ln.endswith(".") and not ln.lower().startswith(("about", "we are", "job", "location")):
            title = ln
            break
    return {
        "title": title,
        "skills": dict(sorted(skills.items(), key=lambda kv: (-kv[1]["weight"], -kv[1]["mentions"]))),
        "degree": degree.group(0) if degree else "",
        "years": max(years) if years else None,
        "certs": certs,
        "generic_used": generic_used,
    }


def _term_in(term: str, text: str) -> list[str]:
    """Evidence lines in `text` containing a generic posting term (word-bounded, light stemming)."""
    stem = term.lower()
    for suf in ("ing", "ed", "es", "s"):
        if len(stem) > 5 and stem.endswith(suf):
            stem = stem[: -len(suf)]
            break
    rx = re.compile(rf"\b{re.escape(stem)}\w{{0,3}}\b", re.I)
    return [ln[:160] for ln in _lines(text) if rx.search(ln)][:2]


HEADER_LIKE = re.compile(r"(\b(19|20)\d{2}\b.*\b(present|current|(19|20)\d{2})\b)|—|\|", re.I)


def _resume_skills(resume: str) -> dict[str, list[str]]:
    """Skill -> evidence lines, with real bullets ranked ahead of job-header lines."""
    found: dict[str, list[tuple[int, str]]] = {}
    for ln in _lines(resume):
        is_header = bool(HEADER_LIKE.search(ln)) and len(ln.split()) <= 14
        for name, pats in _COMPILED.items():
            if any(p.search(ln) for p in pats):
                found.setdefault(name, [])
                if all(ln != x[1] for x in found[name]):
                    found[name].append((1 if is_header else 0, ln[:160]))
    return {k: [t for _, t in sorted(v, key=lambda x: x[0])[:3]] for k, v in found.items()}


def ats_checks(resume: str) -> list[dict]:
    """Simple, honest checks of things applicant-tracking systems and recruiters trip on."""
    resume = _bound(resume)
    out = []
    lines = _lines(resume)
    text = resume.lower()
    words = len(resume.split())
    bullets = [ln for ln in lines if len(ln.split()) >= 6 and not ln.endswith(":")]
    weak = [ln for ln in bullets if any(w in ln.lower() for w in WEAK_PHRASES)]
    with_numbers = [ln for ln in bullets if NUMBER_RE.search(ln)]
    strong_start = [ln for ln in bullets if ln.split()[0].lower().rstrip(",.") in ACTION_VERBS]
    if words < 250:
        out.append({"level": "warn", "title": "Resume looks short", "detail": f"About {words} words. Most one-page resumes have 350–600. Add a line or two of results for each role."})
    if words > 900:
        out.append({"level": "warn", "title": "Resume looks long", "detail": f"About {words} words. Recruiters skim; aim for one page (two if 10+ years)."})
    if not re.search(r"\S{1,64}@[A-Za-z0-9-]{1,63}\.[A-Za-z]{2,}", resume):
        out.append({"level": "bad", "title": "No email address found", "detail": "Put your email near the top so the system can match you to your application."})
    if not re.search(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", resume):
        out.append({"level": "warn", "title": "No phone number found", "detail": "Add a phone number near the top."})
    if not re.search(r"\b(experience|employment|work history)\b", text):
        out.append({"level": "warn", "title": "No 'Experience' heading", "detail": "Use standard headings — Experience, Education, Skills — so software can find each section."})
    if not re.search(r"\b(skills|technical skills|core competencies)\b", text):
        out.append({"level": "warn", "title": "No 'Skills' section", "detail": "A short Skills list is the easiest place to match the posting's keywords."})
    if weak:
        out.append({"level": "warn", "title": f"{len(weak)} line{'s' if len(weak) != 1 else ''} start{'' if len(weak) != 1 else 's'} with weak phrases", "detail": "Replace 'responsible for' / 'helped with' with what you did: Led, Built, Reduced, Increased… Example: " + weak[0][:120]})
    if bullets and len(with_numbers) < max(2, len(bullets) // 3):
        out.append({"level": "warn", "title": "Few numbers", "detail": f"Only {len(with_numbers)} of {len(bullets)} lines {'have' if len(with_numbers) != 1 else 'has'} a number. Add results: how many, how much, how fast, how often."})
    if bullets and len(strong_start) < len(bullets) // 2:
        out.append({"level": "info", "title": "Start lines with action words", "detail": "Begin each bullet with a verb (Led, Built, Managed…). It reads faster and sounds stronger."})
    if re.search(r"\b(references available|objective:)", text):
        out.append({"level": "info", "title": "Old-fashioned lines", "detail": "'References available upon request' and 'Objective' sections are no longer expected. Use the space for results."})
    if not out:
        out.append({"level": "ok", "title": "Basics look good", "detail": "Contact info, standard headings, numbers and action words are all there."})
    return out


def match_resume(resume: str, posting: str) -> dict:
    resume, posting = _bound(resume), _bound(posting)
    req = extract_requirements(posting)
    have = _resume_skills(resume)
    matched, missing = [], []
    total_w = sum(v["weight"] for v in req["skills"].values()) or 1
    got_w = 0
    for name, info in req["skills"].items():
        if info.get("kind") == "term":
            ev = _term_in(name, resume)
        else:
            ev = have.get(name, [])[:2]
        if ev:
            got_w += info["weight"]
            matched.append({"skill": name, "weight": info["weight"], "evidence": ev, "asked": info["lines"][:1], "kind": info.get("kind", "skill")})
        else:
            missing.append({"skill": name, "weight": info["weight"], "asked": info["lines"][:1], "kind": info.get("kind", "skill")})
    score = round(100 * got_w / total_w) if req["skills"] else 0
    # Extras the resume has that the posting didn't ask for (could cut or keep brief)
    extras = sorted(set(have) - set(req["skills"]))
    # years / degree / certs
    notes = []
    if req["years"]:
        ry = [int(m.group(1)) for m in YEARS_RE.finditer(resume) if int(m.group(1)) <= 40]
        notes.append({"item": f"{req['years']}+ years experience", "status": "unclear" if not ry else ("ok" if max(ry) >= req["years"] else "gap"), "tip": "Say your total years plainly in your summary line, e.g. 'Data analyst with 6 years…'."})
    if req["degree"]:
        notes.append({"item": f"Degree: {req['degree']}", "status": "ok" if DEGREE_RE.search(resume) else "unclear", "tip": "List your highest degree under Education, even if it's in progress."})
    for c in req["certs"]:
        notes.append({"item": f"Certification: {c}", "status": "ok" if re.search(re.escape(c), resume, re.I) else "gap", "tip": "If you have it, add it to a Certifications line. If not, consider whether it's worth getting."})
    return {
        "score": score,
        "title": req["title"],
        "matched": matched,
        "missing": missing,
        "missing_keywords": [m["skill"] for m in missing],
        "extras": extras[:12],
        "requirements": notes,
        "ats": ats_checks(resume),
        "required_count": sum(1 for v in req["skills"].values() if v["weight"] == 2),
        "required_matched": sum(1 for m in matched if m["weight"] == 2),
        "generic_used": req["generic_used"],
        "recognised": len(req["skills"]),
    }


BEHAVIORAL = [
    "Tell me about yourself.",
    "Why do you want this job, and why us?",
    "Tell me about a time you had a conflict with a coworker. What did you do?",
    "Describe a mistake you made at work and what you learned.",
    "Tell me about a time you had too much to do and not enough time.",
    "Give an example of a goal you reached and how you got there.",
    "Tell me about a time you had to learn something new quickly.",
    "What's your biggest weakness?",
    "Where do you see yourself in a few years?",
    "Do you have any questions for us?",
]
SKILL_QUESTIONS = {
    "Python": "Walk me through a Python project you're proud of. What would you do differently?",
    "SQL": "How would you find the top 5 customers by revenue last quarter? Talk me through the query.",
    "Leadership": "Tell me about a time you had to get a team to do something they didn't want to do.",
    "Customer Service": "A customer is angry about something that wasn't your fault. What do you do?",
    "Sales": "Walk me through how you'd take a lead from first call to close.",
    "Project Management": "A project is slipping. How do you find out why and what do you do first?",
    "Communication": "Explain something technical from your last job to me like I'm new.",
    "Security": "How do you decide which vulnerability to fix first when there are fifty?",
    "Data Analysis": "You find a number that doesn't match what the business expects. What's your process?",
    "Machine Learning": "How do you know a model is actually good and not just lucky on the test set?",
    "LLMs / GenAI": "How do you keep an LLM feature from making things up in production?",
    "Teamwork": "Tell me about working with someone from a very different team or background.",
    "Problem Solving": "Describe the hardest problem you solved recently. How did you break it down?",
    "Budgeting / Finance": "Tell me about a time you had to cut costs without hurting results.",
    "Teaching / Training": "How do you tell whether someone you trained actually learned it?",
    "Operations": "What would you check first on day one to find waste in this operation?",
    "Marketing": "A campaign underperforms. How do you figure out why?",
    "Healthcare": "How do you protect patient privacy in your day-to-day work?",
    "Design / UX": "How do you handle feedback that a design you love isn't working for users?",
    "AWS": "Describe how you'd set up a small service on the cloud securely and cheaply.",
}


def interview_questions(posting: str, match: dict) -> dict:
    role = []
    for m in match["matched"][:8]:
        q = SKILL_QUESTIONS.get(m["skill"]) if m.get("kind", "skill") == "skill" else None
        if not q and m["weight"] == 2:
            q = f"Tell me about your experience with {m['skill']}. Walk me through a specific time it mattered."
        if q and len(role) < 6:
            role.append({"q": q, "why": f"They asked for {m['skill']} — be ready with a real example."})
    gaps = []
    for m in match["missing"][:3]:
        gaps.append({"q": f"We're looking for {m['skill']} experience. How would you handle that part of the job?", "why": "This is a gap on your resume. Have an honest answer: related experience, how fast you learn, what you've already started."})
    return {"behavioral": [{"q": q, "why": "Standard question. Use the STAR shape: Situation, Task, Action, Result."} for q in BEHAVIORAL[:6]], "role": role, "gaps": gaps}
