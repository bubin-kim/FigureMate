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
# 그림 라벨의 중국어 번역(siren → 汽笛), 키릴 혼입("다иск리트傅里叶變換"), 합쇼체.
# 한국어 판정(_looks_korean)만으로는 전부 통과해버려 별도 문체 게이트가 필요했다.


def test_looks_korean_accepts_korean_with_english_terms():
    assert _looks_korean("이 그림은 Mel-Spectrogram 변환 과정을 보여주는 구조도이다.")


def test_looks_korean_rejects_english():
    assert not _looks_korean("This figure shows the Mel-Spectrogram pipeline.")


def test_clean_style_rejects_chinese_translation():
    # 실측 원문: "다양한 소음 종류(예: 자동차汽笛, 청소기)" — 한국어 판정은 통과하는 케이스
    text = "다양한 소음 종류(예: 자동차汽笛, 청소기)에 대한 분류 결과이다."
    assert _looks_korean(text), "한국어 판정만으로는 걸러지지 않는 전제 확인"
    assert not _clean_style(text)


def test_clean_style_rejects_cyrillic_mixing():
    # 실측 원문: "효율적인 DFT(다иск리트傅里叶變換) 구현입니다" (Figure 4, temp=0)
    assert not _clean_style("FFT는 효율적인 DFT(다иск리트 푸리에 변환) 구현이다.")


def test_clean_style_rejects_polite_form():
    # prompt.md 문체 규칙: "~다/~한다"체 통일. 합쇼체가 섞이면 Figure마다 톤이 오락가락한다.
    # "받침 ㅂ + 니다" 일반형 검사 — 줍니다/됩니다/습니다/입니다 전부 걸린다.
    assert not _clean_style("이 그림은 STFT 변환 과정을 보여줍니다.")
    assert not _clean_style("스펙트로그램이 생성됩니다.")
    assert not _clean_style("이것은 혼동 행렬입니다.")


def test_clean_style_plain_anida_not_false_positive():
    # 평서형 "아니다"는 합쇼체가 아니다 — 단순 "니다" 매칭이면 오탐하는 케이스
    assert _clean_style("이 값은 절대적인 기준이 아니다.")


def test_clean_style_clean_korean_passes():
    assert _clean_style("사이렌, 청소기, 거리 음악에 대한 SVM 분류 혼동 행렬이다.")
