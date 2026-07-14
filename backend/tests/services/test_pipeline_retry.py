"""pipeline._retry_llm 단위 테스트 (architecture.md 5절 재시도 정책).

M5 Step 6 E2E에서 Vision 호출의 transient 실패가 실제 관찰되어 구현된 로직이다.
base_delay=0으로 대기 없이 검증한다.
"""
import pytest

from app.services.pipeline import _clean_style, _looks_korean, _retry_llm


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError(f"transient {calls['n']}")
        return "ok"

    assert _retry_llm(flaky, base_delay=0) == "ok"
    assert calls["n"] == 3, "두 번 실패 후 세 번째에 성공"


def test_retry_exhaustion_raises_last_exception():
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise TimeoutError(f"attempt {calls['n']}")

    with pytest.raises(TimeoutError, match="attempt 3"):
        _retry_llm(always_fail, base_delay=0)
    assert calls["n"] == 3, "최대 3회 시도 후 마지막 예외를 올림"


def test_retry_no_retry_on_immediate_success():
    calls = {"n": 0}

    def ok():
        calls["n"] += 1
        return 42

    assert _retry_llm(ok, base_delay=0) == 42
    assert calls["n"] == 1


# --- 설명 품질 게이트 (explain_stage_one 재시도 루프의 판정 함수) ---
# 실측 사례(2026-07-14): qwen2.5vl이 temp=0 불량 모드에서 언어·문체 지시를 무시한다 —
# 그림 라벨의 중국어 번역(siren → 汽笛), 키릴 혼입("다иск리트傅里叶變換"), 문체 혼용.
# 한국어 판정(_looks_korean)만으로는 전부 통과해버려 별도 문체 게이트가 필요했다.
# 문체 표준은 합쇼체(존댓말) — 7b가 '-다'체 지시를 3회 재시도 전부 무시할 만큼 합쇼체
# 성향이 강해, 모델 성향에 맞춰 표준을 정했다 (pipeline._polite_korean docstring 참고).


def test_looks_korean_accepts_korean_with_english_terms():
    assert _looks_korean("이 그림은 Mel-Spectrogram 변환 과정을 보여주는 구조도입니다.")


def test_looks_korean_rejects_english():
    assert not _looks_korean("This figure shows the Mel-Spectrogram pipeline.")


def test_clean_style_rejects_chinese_translation():
    # 실측 원문: "다양한 소음 종류(예: 자동차汽笛, 청소기)" — 한국어 판정은 통과하는 케이스
    text = "다양한 소음 종류(예: 자동차汽笛, 청소기)에 대한 분류 결과입니다."
    assert _looks_korean(text), "한국어 판정만으로는 걸러지지 않는 전제 확인"
    assert not _clean_style(text)


def test_clean_style_rejects_cyrillic_mixing():
    # 실측 원문: "효율적인 DFT(다иск리트傅里叶變換) 구현입니다" (Figure 4, temp=0)
    assert not _clean_style("FFT는 효율적인 DFT(다иск리트 푸리에 변환) 구현입니다.")


def test_clean_style_rejects_plain_form():
    # 합쇼체 표준 — '-다'체 문장이 하나라도 섞이면 재생성 (Figure별 톤 통일)
    assert not _clean_style("이 그림은 STFT 변환 과정을 보여준다.")
    assert not _clean_style("가로축은 시간입니다. 세로축은 주파수를 나타낸다.")


def test_clean_style_accepts_polite_korean():
    assert _clean_style("이 그림은 STFT 변환 과정을 보여줍니다. 가로축은 시간(초)입니다.")
    # 문장 끝의 괄호·영문·숫자는 어미 판정에서 무시된다
    assert _clean_style("겹치기는 25%로 설정됩니다 (512/2048 샘플).")


def test_clean_style_rejects_noun_fragment_summary():
    # 명사구로 끝나는 요약("~하는 과정")은 문장이 아니다 — 재생성 대상
    assert not _clean_style("FFT를 사용하여 스펙트로그램을 생성하는 과정")
    # 실측 누락 사례: summary가 명사구여도 뒤 문장과 공백으로 이어지면 잡아야 한다
    # (pipeline은 summary와 detailed를 공백으로 잇는다)
    assert not _clean_style("FFT 행렬을 보여주는 그림. 이 그림은 두 부분으로 구성되어 있습니다.")


def test_clean_style_clean_korean_passes():
    assert _clean_style("사이렌, 청소기, 거리 음악에 대한 SVM 분류 혼동 행렬입니다.")
