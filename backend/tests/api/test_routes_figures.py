"""figures API 통합 테스트.

업로드(비동기 파이프라인: 파싱 → Figure 추출 → 매칭) 완료 후 figures 목록 → 상세 →
이미지 파일 → 매칭까지 검증한다. paper2(ResNet)를 사용 — Figure 7개 전부 벡터 그래픽이라
렌더링-크롭 주 경로를 커버한다. 매칭은 mock Provider라 명시 참조(결정론)만 산출된다.
"""
import pytest

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _require_pdf(sample_pdf_dir, name):
    pdf_path = sample_pdf_dir / name
    if not pdf_path.exists():
        pytest.skip(f"샘플 PDF 없음: {pdf_path}")
    return pdf_path


def _upload_and_wait(client, pdf_path):
    with open(pdf_path, "rb") as f:
        paper = client.post(
            "/papers", files={"file": (pdf_path.name, f, "application/pdf")}
        ).json()
    got = client.get(f"/papers/{paper['id']}").json()
    return got


def test_upload_to_figure_image_e2e(client, sample_pdf_dir):
    pdf_path = _require_pdf(sample_pdf_dir, "paper2.pdf")

    # 1. 업로드 → 백그라운드 처리 완료 후 done
    paper = _upload_and_wait(client, pdf_path)
    assert paper["upload_status"] == "done", paper

    # 2. Figure 목록: 7개 전부, 필드 무결성, 페이지 순 정렬
    response = client.get(f"/papers/{paper['id']}/figures")
    assert response.status_code == 200
    figures = response.json()
    assert len(figures) == 7
    assert [f["figure_number"] for f in figures] == [f"Figure {i}" for i in range(1, 8)]
    pages = [f["page"] for f in figures]
    assert pages == sorted(pages)
    for figure in figures:
        assert figure["paper_id"] == paper["id"]
        assert figure["caption"].lower().startswith(("figure", "fig."))
        assert figure["image_uri"].startswith("local://figures/")
        assert len(figure["bbox"]) == 4
        assert 0 < figure["extraction_confidence"] <= 1.0
        # M4: 파이프라인이 explain까지 완료하면 status가 explained로 전이한다
        assert figure["status"] == "explained"

    # 3. 상세 조회
    fid = figures[0]["id"]
    response = client.get(f"/papers/{paper['id']}/figures/{fid}")
    assert response.status_code == 200
    assert "Training error" in response.json()["caption"]  # 골든의 Figure 1 캡션

    # 4. 이미지 파일 응답 (M5 뷰어용)
    response = client.get(f"/papers/{paper['id']}/figures/{fid}/image")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(PNG_MAGIC)


def test_figure_detail_includes_explanation(client, sample_pdf_dir):
    """GET .../figures/{fid}에 M4 설명이 포함된다 (M4 DoD). mock에서도 설명은 생성되며
    근거 없음이 정직하게 표시된다(none_found)."""
    pdf_path = _require_pdf(sample_pdf_dir, "paper1.pdf")
    paper = _upload_and_wait(client, pdf_path)
    assert paper["upload_status"] == "done"

    figures = client.get(f"/papers/{paper['id']}/figures").json()
    fid = figures[0]["id"]
    detail = client.get(f"/papers/{paper['id']}/figures/{fid}").json()
    assert "explanation" in detail
    exp = detail["explanation"]
    assert exp is not None, "파이프라인이 explain까지 완료했으므로 설명이 있어야 함"
    assert exp["figure_type"] in ("architecture", "plot", "qualitative", "other")
    assert exp["summary"] or exp["detailed_explanation"]
    # grounding은 최소 1개 항목 (none_found여도 명시적으로 기록 — 빈 리스트 금지)
    assert len(exp["grounding"]) >= 1
    assert all(g["source"] in ("paragraph", "caption", "none_found") for g in exp["grounding"])
    assert exp["model_used"]


def test_none_found_for_unmatched_figure_e2e(client, sample_pdf_dir):
    """★M4 핵심 DoD (실제 재료로 검증): 근거 문단이 없는 Figure는 grounding.source='none_found'로
    정직하게 표시되고, 지어낸 근거가 붙지 않는다.

    paper1 Figure 3(부록 attention 시각화)은 본문 명시 참조가 0건이라(M3 Step 2 확정) 파이프라인
    끝에서 매칭이 비어 있다 — none_found 케이스의 실제 재료. 그럼에도 설명 자체는 생성된다
    (근거가 없다고 설명을 포기하지 않고, 관찰에 근거해 설명하되 지어낸 인용을 붙이지 않는다)."""
    pdf_path = _require_pdf(sample_pdf_dir, "paper1.pdf")
    paper = _upload_and_wait(client, pdf_path)
    assert paper["upload_status"] == "done"

    figures = client.get(f"/papers/{paper['id']}/figures").json()
    fig3 = next(f for f in figures if f["figure_number"] == "Figure 3")

    # Fig 3는 명시 참조 0건 → 매칭 비어 있음
    matches = client.get(f"/papers/{paper['id']}/figures/{fig3['id']}/matches").json()
    assert matches == [], "paper1 Fig 3는 명시 참조가 없어 매칭 0건이어야 함"

    # 핵심: 근거 없음이 none_found로 정직하게 표시, 지어낸 paragraph 근거 없음
    detail = client.get(f"/papers/{paper['id']}/figures/{fig3['id']}").json()
    exp = detail["explanation"]
    assert exp is not None
    assert all(g["source"] == "none_found" for g in exp["grounding"]), "근거 없으면 none_found 강제"
    assert all(g["paragraph_id"] is None for g in exp["grounding"]), "지어낸 문단 근거가 없어야 함"
    assert exp["grounding"][0]["note"], "사용자에게 보일 '근거 없음' 문구가 있어야 함"
    # 그럼에도 설명 자체는 존재한다 (근거가 없다고 설명을 포기하지 않는다)
    assert exp["summary"] or exp["detailed_explanation"]


def test_figure_matches_endpoint(client, sample_pdf_dir):
    """매칭 조회: paper2 Figure들은 명시 참조가 풍부해 mock에서도 explicit 매칭이 나온다.
    근거 문단 원문이 포함되고 관련도 내림차순으로 정렬된다."""
    pdf_path = _require_pdf(sample_pdf_dir, "paper2.pdf")
    paper = _upload_and_wait(client, pdf_path)
    assert paper["upload_status"] == "done"

    figures = client.get(f"/papers/{paper['id']}/figures").json()
    # 논문 전체에서 최소 한 Figure는 매칭을 가진다 (명시 참조 다수)
    total_matches = 0
    for figure in figures:
        matches = client.get(
            f"/papers/{paper['id']}/figures/{figure['id']}/matches"
        ).json()
        total_matches += len(matches)
        scores = [m["relevance_score"] for m in matches]
        assert scores == sorted(scores, reverse=True), "관련도 내림차순 정렬"
        for m in matches:
            assert m["match_type"] in ("explicit_reference", "semantic_similarity")
            assert m["paragraph_text"].strip()  # 근거 원문 포함
            if m["match_type"] == "explicit_reference":
                assert m["relevance_score"] == 1.0
                assert m["quote_span"] is not None
    assert total_matches > 0, "명시 참조가 풍부한 논문인데 매칭이 0건일 수 없음"


def test_figures_404_cases(client, sample_pdf_dir):
    # 존재하지 않는 paper
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/papers/{missing}/figures").status_code == 404
    # 존재하는 paper + 존재하지 않는 figure
    pdf_path = _require_pdf(sample_pdf_dir, "paper2.pdf")
    paper = _upload_and_wait(client, pdf_path)
    assert client.get(f"/papers/{paper['id']}/figures/{missing}").status_code == 404
    assert client.get(f"/papers/{paper['id']}/figures/{missing}/image").status_code == 404
    assert client.get(f"/papers/{paper['id']}/figures/{missing}/matches").status_code == 404


def test_failed_paper_has_empty_figures(client):
    """파싱 실패한 논문도 figures 조회는 200 + 빈 목록 (M1 에러 정책과 일관)."""
    import io

    paper = client.post(
        "/papers",
        files={"file": ("broken.pdf", io.BytesIO(b"garbage"), "application/pdf")},
    ).json()
    got = client.get(f"/papers/{paper['id']}").json()
    assert got["upload_status"] == "failed"
    response = client.get(f"/papers/{paper['id']}/figures")
    assert response.status_code == 200
    assert response.json() == []
