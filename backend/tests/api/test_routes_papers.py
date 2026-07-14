"""papers API 통합 테스트.

M3에서 비동기로 전환: POST /papers는 upload_status="parsing"으로 즉시 응답하고
파이프라인(parse→figure→matching)은 백그라운드로 실행된다. TestClient는 BackgroundTasks를
응답 직후 동기로 돌리고, 테스트는 mock Provider(기본)라 즉시 완료되므로, POST 응답 직후의
GET에서 최종 상태(done/failed)를 관찰할 수 있다 (conftest의 processor override 참고).
"""
import io
import uuid

import pytest


def _require_pdf(sample_pdf_dir, name):
    pdf_path = sample_pdf_dir / name
    if not pdf_path.exists():
        pytest.skip(f"샘플 PDF 없음: {pdf_path} — M1 사전 준비물을 먼저 넣으세요.")
    return pdf_path


def _upload(client, pdf_path):
    with open(pdf_path, "rb") as f:
        return client.post(
            "/papers", files={"file": (pdf_path.name, f, "application/pdf")}
        )


def test_upload_responds_immediately_then_processes(client, sample_pdf_dir):
    pdf_path = _require_pdf(sample_pdf_dir, "paper1.pdf")

    # 1. 업로드 → 즉시 "parsing"으로 응답 (비동기 전환의 핵심)
    response = _upload(client, pdf_path)
    assert response.status_code == 200, response.text
    paper = response.json()
    assert paper["upload_status"] == "parsing"
    assert paper["filename"] == "paper1.pdf"

    # 2. 백그라운드 처리 완료 후 상태 조회 → done
    response = client.get(f"/papers/{paper['id']}")
    assert response.status_code == 200
    done = response.json()
    assert done["upload_status"] == "done"
    assert done["page_count"] == 15
    assert done["error_message"] is None

    # 3. 섹션 조회: 중첩 JSON, order 정렬, 문단 UUID 발급
    response = client.get(f"/papers/{paper['id']}/sections")
    assert response.status_code == 200
    sections = response.json()
    assert len(sections) > 0
    assert any("Introduction" in s["title"] for s in sections)
    assert [s["order"] for s in sections] == list(range(len(sections)))
    for section in sections:
        assert section["paper_id"] == paper["id"]
        assert [p["order"] for p in section["paragraphs"]] == list(
            range(len(section["paragraphs"]))
        )
        for paragraph in section["paragraphs"]:
            assert paragraph["id"]
            assert paragraph["text"].strip()


def test_get_unknown_paper_returns_404(client):
    assert client.get("/papers/00000000-0000-0000-0000-000000000000").status_code == 404
    assert (
        client.get("/papers/00000000-0000-0000-0000-000000000000/sections").status_code
        == 404
    )


def test_upload_rejects_non_pdf(client):
    response = client.post(
        "/papers", files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    )
    assert response.status_code == 422


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/papers", files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
    )
    assert response.status_code == 422


def test_corrupted_pdf_marked_failed(client):
    """파싱 실패는 HTTP 에러가 아니라 Paper 상태로 표현한다 (docs/architecture.md 5절).
    비동기 전환 후: POST는 parsing으로 응답하고, 백그라운드에서 failed로 전이한다."""
    response = client.post(
        "/papers",
        files={"file": ("broken.pdf", io.BytesIO(b"garbage bytes"), "application/pdf")},
    )
    assert response.status_code == 200
    paper = response.json()
    assert paper["upload_status"] == "parsing"

    # 백그라운드 처리 후 failed + error_message
    got = client.get(f"/papers/{paper['id']}").json()
    assert got["upload_status"] == "failed"
    assert got["error_message"]

    # 실패한 Paper도 섹션 조회는 200 + 빈 목록
    response = client.get(f"/papers/{paper['id']}/sections")
    assert response.status_code == 200
    assert response.json() == []


def test_list_papers_returns_history_newest_first(client, db_session, sample_pdf_dir):
    """GET /papers — 홈 화면 히스토리 목록: 최신순 정렬 + figure_count 포함."""
    from datetime import datetime, timedelta, timezone

    from app.models import Paper

    paper1 = _upload(client, _require_pdf(sample_pdf_dir, "paper1.pdf")).json()
    paper2 = _upload(client, _require_pdf(sample_pdf_dir, "paper2.pdf")).json()
    # created_at은 func.now()(트랜잭션 시작 시각)라 테스트 트랜잭션 안에서는 동률 —
    # 실사용(요청별 트랜잭션)의 시간차를 재현해 최신순 정렬을 검증한다.
    db_session.get(Paper, uuid.UUID(paper1["id"])).created_at = datetime.now(
        timezone.utc
    ) - timedelta(hours=1)
    db_session.flush()

    response = client.get("/papers")
    assert response.status_code == 200
    papers = response.json()
    assert [p["id"] for p in papers[:2]] == [paper2["id"], paper1["id"]], "최신 업로드가 먼저"
    by_id = {p["id"]: p for p in papers}
    # 골든 기준 Figure 수 (tests/fixtures/sample_papers/*.figures.expected.json)
    assert by_id[paper1["id"]]["figure_count"] == 5
    assert by_id[paper2["id"]]["figure_count"] == 7
    assert by_id[paper1["id"]]["upload_status"] == "done"


def test_list_papers_empty_is_ok(client):
    assert client.get("/papers").json() == []


def test_reupload_same_pdf_creates_new_paper(client, sample_pdf_dir):
    """같은 PDF 재업로드는 새 Paper로 취급되며 에러 없이 동작한다."""
    pdf_path = _require_pdf(sample_pdf_dir, "paper2.pdf")
    first = _upload(client, pdf_path).json()
    second = _upload(client, pdf_path).json()
    assert first["id"] != second["id"]
    assert client.get(f"/papers/{first['id']}").json()["upload_status"] == "done"
    assert client.get(f"/papers/{second['id']}").json()["upload_status"] == "done"
