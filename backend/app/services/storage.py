"""파일 저장 인터페이스. M1은 로컬 파일시스템으로 시작하고, 이후 S3 등으로 교체 가능하게
인터페이스를 분리한다 (docs/milestones/M1.md Step 4 참고).

저장 URI 규약: 백엔드 종류를 URI 스킴으로 구분한다.
- 로컬: "local://<파일명>" — 실제 위치는 settings.storage_local_path 아래
- S3 (M2 이후): "s3://<bucket>/<key>" 형태로 확장 예정

호출부(라우트, 파서)는 스킴을 해석하지 않고 save_pdf()/get_pdf_path()만 사용한다.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()

_LOCAL_SCHEME = "local://"


def save_pdf(file_bytes: bytes, filename: str) -> str:
    """PDF 파일을 저장하고 저장 위치 URI를 반환한다.

    파일명 충돌을 피하기 위해 uuid4 기반 이름으로 저장한다. 원본 filename은
    Paper.filename에 별도로 보존되므로 여기서는 사용하지 않는다.
    """
    if settings.storage_backend != "local":
        raise NotImplementedError(f"지원하지 않는 스토리지 백엔드: {settings.storage_backend}")
    storage_dir = Path(settings.storage_local_path)
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.pdf"
    (storage_dir / stored_name).write_bytes(file_bytes)
    return f"{_LOCAL_SCHEME}{stored_name}"


def save_figure_image(image_bytes: bytes, paper_id: str, figure_index: int) -> str:
    """Figure 이미지를 저장하고 URI를 반환한다.

    포맷 방침 (M2 Step 3에서 사용자 결정): PNG @200dpi 그대로 저장 (무손실 —
    논문 Figure는 선화/플롯 위주라 JPEG 이득이 적고, M4 Vision 입력 품질 우선).
    경로: figures/<paper_id>/figure_<index>.png — 논문 단위로 묶어 정리/삭제 용이.
    """
    if settings.storage_backend != "local":
        raise NotImplementedError(f"지원하지 않는 스토리지 백엔드: {settings.storage_backend}")
    rel_path = Path("figures") / str(paper_id) / f"figure_{figure_index}.png"
    abs_path = Path(settings.storage_local_path) / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(image_bytes)
    return f"{_LOCAL_SCHEME}{rel_path}"


def get_file_path(storage_uri: str) -> Path:
    """local:// URI를 로컬 파일시스템 경로로 변환한다 (PDF·이미지 공용)."""
    if not storage_uri.startswith(_LOCAL_SCHEME):
        raise ValueError(f"로컬 스토리지 URI가 아닙니다: {storage_uri}")
    return Path(settings.storage_local_path) / storage_uri.removeprefix(_LOCAL_SCHEME)


def get_pdf_path(storage_uri: str) -> Path:
    """저장된 PDF의 로컬 파일시스템 경로를 반환한다 (document_parser 입력용)."""
    return get_file_path(storage_uri)
