import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal


def _split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for char in sql_text:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _run_sql_file(db: Session, path: Path) -> None:
    sql_text = path.read_text(encoding="utf-8")
    for statement in _split_sql_statements(sql_text):
        db.execute(text(statement))


def maybe_seed_database() -> None:
    if os.getenv("AUTO_SEED", "false").lower() != "true":
        return

    root = Path(__file__).resolve().parent.parent
    schema = root / "sql" / "schema.sql"
    seed = root / "sql" / "seed.sql"

    db = SessionLocal()
    try:
        _run_sql_file(db, schema)
        _run_sql_file(db, seed)
        db.commit()
    finally:
        db.close()
