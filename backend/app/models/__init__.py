"""ORM 모델 패키지. 여기서 전부 import해 Base.metadata에 자동 등록되게 한다
(app/core/db.py docstring의 규약 — Base.metadata.create_all과 alembic autogenerate가
모든 테이블을 인식하려면 모델 모듈이 import되어 있어야 함)."""
from app.models.explanation import FigureExplanation  # noqa: F401
from app.models.figure import Figure  # noqa: F401
from app.models.match import FigureTextMatch  # noqa: F401
from app.models.paper import Paper, Paragraph, Section  # noqa: F401
