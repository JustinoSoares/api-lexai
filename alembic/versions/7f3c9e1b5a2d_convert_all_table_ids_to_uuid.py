"""convert all table ids to UUID

Revision ID: 7f3c9e1b5a2d
Revises: 721fda587a8c
Create Date: 2026-08-04 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "7f3c9e1b5a2d"
down_revision: Union[str, Sequence[str], None] = "721fda587a8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fks() -> None:
    for fk, table in (
        ("messages_conversation_id_fkey", "messages"),
        ("sources_message_id_fkey", "sources"),
        ("sources_law_cache_id_fkey", "sources"),
    ):
        op.drop_constraint(fk, table, type_="foreignkey")


def _add_new_id(table: str) -> None:
    """Adiciona `new_id` UUID (mantendo o `id` inteiro para mapear FKs)."""
    op.add_column(
        table,
        sa.Column(
            "new_id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.execute(f"UPDATE {table} SET new_id = gen_random_uuid()")


def _add_new_fk(child: str, col: str, ref: str, nullable: bool) -> None:
    """Adiciona `new_<col>` UUID com backfill usando o id inteiro do ref ainda presente."""
    op.add_column(
        child, sa.Column(f"new_{col}", UUID(as_uuid=True), nullable=True)
    )
    op.execute(
        f"UPDATE {child} SET new_{col} = r.new_id FROM {ref} r WHERE r.id = {child}.{col}"
    )
    if not nullable:
        op.alter_column(child, f"new_{col}", nullable=False)


def _finalize_id(table: str) -> None:
    """Remove o `id` inteiro e promove `new_id` a `id`."""
    op.drop_constraint(f"{table}_pkey", table, type_="primary")
    op.drop_column(table, "id")
    op.alter_column(table, "new_id", new_column_name="id")
    op.create_primary_key(f"{table}_pkey", table, ["id"])


def _finalize_fk(child: str, col: str) -> None:
    op.drop_column(child, col)
    op.alter_column(child, f"new_{col}", new_column_name=col)


def upgrade() -> None:
    """Upgrade schema: converte todos os ids inteiros para UUID."""
    _drop_fks()

    # 1) Novos UUIDs para todos os ids (os inteiros ficam até mapear as FKs)
    for table in ("conversations", "law_cache", "messages", "sources"):
        _add_new_id(table)

    # 2) FKs: backfill de UUID a partir do id inteiro ainda presente nas mães
    _add_new_fk("messages", "conversation_id", "conversations", nullable=False)
    _add_new_fk("sources", "message_id", "messages", nullable=False)
    _add_new_fk("sources", "law_cache_id", "law_cache", nullable=True)

    # 3) Promove os UUIDs a colunas finais
    _finalize_id("conversations")
    _finalize_id("law_cache")
    _finalize_id("messages")
    _finalize_id("sources")

    _finalize_fk("messages", "conversation_id")
    _finalize_fk("sources", "message_id")
    _finalize_fk("sources", "law_cache_id")

    # 4) Recria FKs
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "sources_message_id_fkey",
        "sources",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "sources_law_cache_id_fkey",
        "sources",
        "law_cache",
        ["law_cache_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 5) Recria índices das FKs
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_sources_message_id", "sources", ["message_id"])


def downgrade() -> None:
    """Downgrade schema: reverte ids UUID para inteiros (sem garantir ordem)."""
    raise NotImplementedError("Downgrade int->uuid não implementado.")
