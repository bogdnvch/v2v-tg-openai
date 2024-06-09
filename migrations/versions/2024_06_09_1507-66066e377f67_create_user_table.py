"""create user table

Revision ID: 66066e377f67
Revises: 
Create Date: 2024-06-09 15:07:46.672461

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "66066e377f67"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "user",
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("values", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index(
        op.f("ix_user_telegram_id"), "user", ["telegram_id"], unique=True
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_user_telegram_id"), table_name="user")
    op.drop_table("user")
    # ### end Alembic commands ###