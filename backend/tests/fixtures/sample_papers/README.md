# 테스트용 샘플 논문

M1 작업을 시작하기 전에 사람이 직접 채워야 하는 폴더입니다 (`docs/milestones/M1.md`의
"사전 준비물" 참고).

필요한 파일 (2세트 이상 권장):

```
paper1.pdf
paper1.expected.json
paper2.pdf
paper2.expected.json
```

## `*.expected.json` 형식

```json
{
  "sections": [
    {"title": "1. Introduction", "min_paragraphs": 2},
    {"title": "2. Related Work", "min_paragraphs": 1},
    {"title": "3. Method", "min_paragraphs": 3},
    {"title": "4. Experiments", "min_paragraphs": 2},
    {"title": "5. Conclusion", "min_paragraphs": 1}
  ]
}
```

`title`은 PDF에 실제 등장하는 표기와 가깝게 적되, 테스트는 fuzzy match를 쓰므로 완전히
동일할 필요는 없습니다. `min_paragraphs`는 해당 섹션에서 최소한 이만큼의 문단이 파싱되어야
"파싱이 깨지지 않았다"고 판단하는 기준입니다.

## 선택 기준

- 1편은 섹션 번호가 명확한 전형적인 논문 (예: 단일 컬럼, 명확한 "1. Introduction" 스타일)
- 1편은 레이아웃이 조금 다른 논문 (2단 컬럼, 관용적 헤딩 이름 사용 등)으로 골라 파서의
  일반화 정도를 확인하는 것을 권장합니다.

PDF 원본은 저작권 문제로 저장소에 커밋하지 않는 것을 권장합니다 (`.gitignore` 참고).
로컬 개발 환경에만 두고, CI에서는 별도 아카이브에서 내려받는 방식을 추후 고려하세요.
