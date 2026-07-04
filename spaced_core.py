from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "flashcards.db"
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


@dataclass(frozen=True)
class Deck:
    id: int
    name: str
    total_cards: int = 0
    due_cards: int = 0


@dataclass(frozen=True)
class Card:
    id: int
    deck_id: int
    front: str
    back: str
    repetition: int
    interval: int
    easiness: float
    next_review: str


def utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def to_iso(value: datetime) -> str:
    return value.replace(microsecond=0).strftime(ISO_FORMAT)


def calculate_sm2(
    repetition: int,
    interval: int,
    easiness: float,
    grade: int,
    now: Optional[datetime] = None,
) -> tuple[int, int, float, datetime]:
    if grade < 1 or grade > 5:
        raise ValueError("grade must be between 1 and 5")

    now = now or utc_now()
    easiness = max(
        1.3,
        easiness + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)),
    )

    if grade < 3:
        repetition = 0
        interval = 1
    else:
        repetition += 1
        if repetition == 1:
            interval = 1
        elif repetition == 2:
            interval = 6
        else:
            interval = max(1, round(interval * easiness))

    return repetition, interval, easiness, now + timedelta(days=interval)


class FlashcardRepository:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        with self.connection:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS decks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deck_id INTEGER NOT NULL,
                    front TEXT NOT NULL,
                    back TEXT NOT NULL,
                    repetition INTEGER NOT NULL DEFAULT 0,
                    interval INTEGER NOT NULL DEFAULT 0,
                    easiness REAL NOT NULL DEFAULT 2.5,
                    next_review TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(deck_id) REFERENCES decks(id) ON DELETE CASCADE
                )
                """
            )
            self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_cards_next_review ON cards(next_review)"
            )
            self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_cards_deck_id ON cards(deck_id)"
            )

    def close(self) -> None:
        self.connection.close()

    def create_deck(self, name: str) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Deck name is required.")
        with self.connection:
            self.connection.execute(
                "INSERT INTO decks (name, created_at) VALUES (?, ?)",
                (clean_name, to_iso(utc_now())),
            )

    def list_decks(self) -> list[Deck]:
        now_iso = to_iso(utc_now())
        rows = self.connection.execute(
            """
            SELECT
                d.id,
                d.name,
                COUNT(c.id) AS total_cards,
                SUM(CASE WHEN c.next_review <= ? THEN 1 ELSE 0 END) AS due_cards
            FROM decks d
            LEFT JOIN cards c ON c.deck_id = d.id
            GROUP BY d.id
            ORDER BY LOWER(d.name)
            """,
            (now_iso,),
        ).fetchall()
        return [
            Deck(
                id=row["id"],
                name=row["name"],
                total_cards=row["total_cards"] or 0,
                due_cards=row["due_cards"] or 0,
            )
            for row in rows
        ]

    def add_card(self, deck_id: int, front: str, back: str) -> None:
        clean_front = front.strip()
        clean_back = back.strip()
        if not clean_front or not clean_back:
            raise ValueError("Both front and back are required.")
        now_iso = to_iso(utc_now())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO cards (
                    deck_id, front, back, repetition, interval, easiness,
                    next_review, created_at
                )
                VALUES (?, ?, ?, 0, 0, 2.5, ?, ?)
                """,
                (deck_id, clean_front, clean_back, now_iso, now_iso),
            )

    def get_next_due_card(self, deck_id: Optional[int] = None) -> Optional[Card]:
        now_iso = to_iso(utc_now())
        params: list[object] = [now_iso]
        deck_filter = ""
        if deck_id is not None:
            deck_filter = "AND deck_id = ?"
            params.append(deck_id)

        row = self.connection.execute(
            f"""
            SELECT *
            FROM cards
            WHERE next_review <= ?
            {deck_filter}
            ORDER BY next_review ASC, id ASC
            LIMIT 1
            """,
            params,
        ).fetchone()
        return self._row_to_card(row) if row else None

    def update_card_review(self, card_id: int, grade: int) -> None:
        row = self.connection.execute(
            "SELECT repetition, interval, easiness FROM cards WHERE id = ?",
            (card_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Card was not found.")

        repetition, interval, easiness, next_review = calculate_sm2(
            repetition=row["repetition"],
            interval=row["interval"],
            easiness=row["easiness"],
            grade=grade,
        )
        with self.connection:
            self.connection.execute(
                """
                UPDATE cards
                SET repetition = ?, interval = ?, easiness = ?, next_review = ?
                WHERE id = ?
                """,
                (repetition, interval, easiness, to_iso(next_review), card_id),
            )

    def due_count(self, deck_id: Optional[int] = None) -> int:
        now_iso = to_iso(utc_now())
        if deck_id is None:
            row = self.connection.execute(
                "SELECT COUNT(*) AS count FROM cards WHERE next_review <= ?",
                (now_iso,),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM cards
                WHERE next_review <= ? AND deck_id = ?
                """,
                (now_iso, deck_id),
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> Card:
        return Card(
            id=row["id"],
            deck_id=row["deck_id"],
            front=row["front"],
            back=row["back"],
            repetition=row["repetition"],
            interval=row["interval"],
            easiness=row["easiness"],
            next_review=row["next_review"],
        )
