import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Source(Base):
    """Ligação entre uma resposta (message) e uma fonte citada (law_cache)."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    law_cache_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("law_cache.id", ondelete="SET NULL"), nullable=True
    )
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    message: Mapped["Message"] = relationship(back_populates="sources")
    law_cache: Mapped["LawCache | None"] = relationship(back_populates="sources")

    __table_args__ = {"comment": "Fontes citadas numa resposta gerada pelo agente."}