import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

DEFAULT_SOURCE_TYPE = "automatic"


class LawCache(Base):
    """Cache de documentos legais extraídos por URL."""

    __tablename__ = "law_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artigo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Origem do registo: "automatic" (busca/extração) ou "seed" (curada manualmente)
    source_type: Mapped[str] = mapped_column(
        String(32), default=DEFAULT_SOURCE_TYPE, nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sources: Mapped[list["Source"]] = relationship(
        back_populates="law_cache", cascade="all, delete-orphan"
    )