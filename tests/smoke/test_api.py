"""G2 — API smoke, G6 — privacy, app store lifecycle."""

import io
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RESUME = (ROOT / "samples" / "resume.txt").read_text()
POSTING = (ROOT / "samples" / "job_posting.txt").read_text()


def test_health_ui_status(client):
    assert client.get("/api/health").json()["ok"]
    assert "Job Hunt Copilot" in client.get("/").text
    d = client.get("/api/status").json()
    assert d["provider"]["name"] == "offline" and d["apps"] == [] and d["saved_resume"] is False


def test_sample_and_match(client):
    s = client.get("/api/sample").json()
    assert len(s["resume"]) > 500 and len(s["posting"]) > 500
    r = client.post("/api/match", json={"resume": s["resume"], "posting": s["posting"], "company": "Northstar"}).json()
    assert r["match"]["score"] >= 80 and r["id"] and r["questions"]["role"]
    apps = client.get("/api/apps").json()
    assert len(apps) == 1 and apps[0]["company"] == "Northstar" and apps[0]["status"] == "draft"
    # re-match same inputs with the id updates rather than duplicating
    client.post("/api/match", json={"resume": s["resume"], "posting": s["posting"], "company": "Northstar", "app_id": r["id"]})
    assert len(client.get("/api/apps").json()) == 1


def test_match_validation(client):
    assert client.post("/api/match", json={"resume": "short", "posting": POSTING}).status_code == 400
    assert client.post("/api/match", json={"resume": RESUME, "posting": "Analyst"}).status_code == 400


def test_resume_file_upload(client):
    import docx

    d = docx.Document()
    for ln in RESUME.split("\n"):
        d.add_paragraph(ln)
    buf = io.BytesIO()
    d.save(buf)
    r = client.post("/api/resume/file", files={"file": ("resume.docx", buf.getvalue(), "application/octet-stream")}).json()
    assert "Brightcart" in r["text"]
    bad = client.post("/api/resume/file", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400


def test_resume_save_and_load_private(client):
    import os
    import stat

    from job_hunt_copilot.config import data_dir

    client.post("/api/resume/save", json={"text": RESUME})
    assert client.get("/api/resume").json()["text"] == RESUME
    assert stat.S_IMODE(os.stat(data_dir() / "resume.txt").st_mode) == 0o600
    assert client.get("/api/status").json()["saved_resume"] is True


def test_tailor_letter_grade_offline(client):
    r = client.post("/api/match", json={"resume": RESUME, "posting": POSTING}).json()
    t = client.post("/api/tailor", json={"app_id": r["id"]}).json()
    assert t["engine"] == "checklist" and t["checklist"]
    letter = client.post("/api/cover-letter", json={"app_id": r["id"], "details": "Moving in January.", "tone": "warm"}).json()
    assert letter["engine"] == "template" and "Moving in January" in letter["text"]
    g = client.post("/api/grade", json={"app_id": r["id"], "question": "Tell me about yourself.", "answer": "I am a data analyst with 5 years of experience. I led a project that cut returns by a third."}).json()
    assert 1 <= g["score"] <= 5
    doc = client.get(f"/api/apps/{r['id']}").json()
    assert doc["tailored"]["engine"] == "checklist" and len(doc["answers"]) == 1
    assert client.post("/api/tailor", json={"app_id": "nope"}).status_code == 404


def test_status_and_delete(client):
    r = client.post("/api/match", json={"resume": RESUME, "posting": POSTING}).json()
    assert client.post(f"/api/apps/{r['id']}/status", json={"status": "applied"}).json()["ok"]
    assert client.get("/api/apps").json()[0]["status"] == "applied"
    assert client.post(f"/api/apps/{r['id']}/status", json={"status": "bogus"}).status_code == 400
    assert client.delete(f"/api/apps/{r['id']}").json()["deleted"] is True
    assert client.get(f"/api/apps/{r['id']}").status_code == 404
    client.post("/api/match", json={"resume": RESUME, "posting": POSTING})
    client.post("/api/resume/save", json={"text": RESUME})
    assert client.delete("/api/apps").json()["deleted"] == 1
    assert client.get("/api/resume").json()["text"] == ""


def test_history_off_keeps_session_in_memory_only(client):
    from job_hunt_copilot.config import data_dir

    client.post("/api/settings", json={"save_history": False})
    r = client.post("/api/match", json={"resume": RESUME, "posting": POSTING}).json()
    # AI steps must still work in the same session…
    assert client.post("/api/tailor", json={"app_id": r["id"]}).status_code == 200
    assert client.post("/api/cover-letter", json={"app_id": r["id"]}).status_code == 200
    # …but nothing is written to disk
    assert not list((data_dir() / "apps").glob("*.json"))
    assert client.get("/api/apps").json()[0]["unsaved"] is True


def test_bad_base_url_rejected_and_status_survives(client):
    r = client.post("/api/settings", json={"provider": "openai", "openai_base_url": "http://[::1"})
    assert r.status_code == 400 and "valid server address" in r.json()["detail"]
    assert client.get("/api/status").status_code == 200


def test_status_does_not_contact_cloud_with_key(client, monkeypatch):
    monkeypatch.setenv("JOBHUNT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234567890abcdef")
    calls = []

    def guard(self, *a, **k):
        calls.append(a)
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", guard)
    d = client.get("/api/status").json()
    assert d["provider"]["ok"] is True and "Click Test" in d["provider"]["message"] and calls == []


def test_origin_check_is_exact_host(client):
    assert client.post("/api/resume/save", json={"text": "x"}, headers={"Origin": "http://localhost.evil.example"}).status_code == 403
    assert client.post("/api/resume/save", json={"text": "x"}, headers={"Origin": "http://localhost:8767"}).status_code == 200


def test_long_or_unicode_ids_are_rejected_cleanly(client):
    assert client.get("/api/apps/" + "a" * 300).status_code == 404
    assert client.get("/api/apps/ａｂｃ１２３ａｂｃ１２３").status_code == 404


def test_key_containing_asterisk_can_be_saved(client):
    client.post("/api/settings", json={"openai_api_key": "sk-ab*cd*ef*gh*ij*kl"})
    assert client.get("/api/status").json()["settings"]["has_openai_key"] is True


def test_path_traversal_ids_rejected(client):
    assert client.get("/api/apps/..%2F..%2Fetc").status_code in (404, 400)
    assert client.delete("/api/apps/..").status_code in (404, 400)
    assert client.delete("/api/apps/%2e%2e").status_code == 400


def test_foreign_host_and_cross_site_blocked(client):
    from fastapi.testclient import TestClient

    from job_hunt_copilot.server import app

    assert TestClient(app, base_url="http://evil.example").get("/api/apps").status_code == 400
    assert client.post("/api/resume/save", json={"text": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_no_network_in_offline_mode(client, monkeypatch):
    r = client.post("/api/match", json={"resume": RESUME, "posting": POSTING}).json()
    calls = []

    def guard(self, *a, **k):
        calls.append(a)
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    assert client.get("/api/status").status_code == 200
    assert client.post("/api/tailor", json={"app_id": r["id"]}).status_code == 200
    assert client.post("/api/cover-letter", json={"app_id": r["id"]}).status_code == 200
    assert client.post("/api/grade", json={"app_id": r["id"], "question": "q", "answer": "an answer"}).status_code == 200
    assert calls == []
