from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from tkinter import messagebox


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


def from_iso(value: str) -> datetime:
    return datetime.strptime(value, ISO_FORMAT)


def calculate_sm2(
    repetition: int,
    interval: int,
    easiness: float,
    grade: int,
    now: Optional[datetime] = None,
) -> tuple[int, int, float, datetime]:
    """Return updated SM-2 stats for a 1-5 quality grade.

    The UI exposes four grades:
    Again=1, Hard=3, Good=4, Easy=5.
    Any grade below 3 resets the learning streak.
    """
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

    next_review = now + timedelta(days=interval)
    return repetition, interval, easiness, next_review


class FlashcardRepository:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.connection = sqlite3.connect(self.db_path)
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


class FlashcardApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.repository = FlashcardRepository()
        self.selected_deck_id: Optional[int] = None
        self.current_card: Optional[Card] = None
        self.deck_buttons: dict[int, ctk.CTkButton] = {}

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("Spaced Retention")
        self.geometry("1120x720")
        self.minsize(980, 640)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)

        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        self.build_sidebar()
        self.build_dashboard()
        self.refresh_decks()

    def build_sidebar(self) -> None:
        title = ctk.CTkLabel(
            self.sidebar,
            text="Spaced Retention",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, padx=22, pady=(24, 8), sticky="w")

        self.due_summary = ctk.CTkLabel(
            self.sidebar,
            text="0 due today",
            text_color=("gray35", "gray72"),
        )
        self.due_summary.grid(row=1, column=0, padx=22, pady=(0, 18), sticky="w")

        self.all_decks_button = ctk.CTkButton(
            self.sidebar,
            text="All Decks",
            command=lambda: self.select_deck(None),
            height=38,
        )
        self.all_decks_button.grid(row=2, column=0, padx=16, pady=(0, 10), sticky="ew")

        self.deck_list = ctk.CTkScrollableFrame(
            self.sidebar,
            label_text="Decks",
            height=300,
        )
        self.deck_list.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")
        self.deck_list.grid_columnconfigure(0, weight=1)

        self.new_deck_entry = ctk.CTkEntry(
            self.sidebar,
            placeholder_text="New deck name",
            height=38,
        )
        self.new_deck_entry.grid(row=4, column=0, padx=16, pady=(0, 10), sticky="ew")
        self.new_deck_entry.bind("<Return>", lambda _: self.create_deck())

        create_deck_button = ctk.CTkButton(
            self.sidebar,
            text="Create Deck",
            command=self.create_deck,
            height=38,
        )
        create_deck_button.grid(row=5, column=0, padx=16, pady=(0, 18), sticky="new")

    def build_dashboard(self) -> None:
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, padx=28, pady=(24, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        self.page_title = ctk.CTkLabel(
            header,
            text="Review Queue",
            font=ctk.CTkFont(size=28, weight="bold"),
        )
        self.page_title.grid(row=0, column=0, sticky="w")

        self.scope_label = ctk.CTkLabel(
            header,
            text="All decks",
            text_color=("gray35", "gray72"),
        )
        self.scope_label.grid(row=1, column=0, pady=(3, 0), sticky="w")

        refresh_button = ctk.CTkButton(
            header,
            text="Refresh",
            width=110,
            command=self.refresh_all,
        )
        refresh_button.grid(row=0, column=1, rowspan=2, sticky="e")

        content = ctk.CTkFrame(self.main, fg_color="transparent")
        content.grid(row=1, column=0, padx=28, pady=(8, 24), sticky="nsew")
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        self.review_frame = ctk.CTkFrame(content, corner_radius=8)
        self.review_frame.grid(row=0, column=0, padx=(0, 14), sticky="nsew")
        self.review_frame.grid_columnconfigure(0, weight=1)
        self.review_frame.grid_rowconfigure(2, weight=1)

        self.review_status = ctk.CTkLabel(
            self.review_frame,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.review_status.grid(row=0, column=0, padx=24, pady=(22, 8), sticky="w")

        self.front_label = ctk.CTkTextbox(
            self.review_frame,
            height=180,
            wrap="word",
            font=ctk.CTkFont(size=24, weight="bold"),
            activate_scrollbars=True,
        )
        self.front_label.grid(row=1, column=0, padx=24, pady=(0, 14), sticky="ew")
        self.front_label.configure(state="disabled")

        self.back_label = ctk.CTkTextbox(
            self.review_frame,
            wrap="word",
            font=ctk.CTkFont(size=18),
            activate_scrollbars=True,
        )
        self.back_label.grid(row=2, column=0, padx=24, pady=(0, 14), sticky="nsew")
        self.back_label.configure(state="disabled")

        self.show_answer_button = ctk.CTkButton(
            self.review_frame,
            text="Show Answer",
            command=self.show_answer,
            height=44,
        )
        self.show_answer_button.grid(row=3, column=0, padx=24, pady=(0, 14), sticky="ew")

        self.grade_frame = ctk.CTkFrame(self.review_frame, fg_color="transparent")
        self.grade_frame.grid(row=4, column=0, padx=24, pady=(0, 24), sticky="ew")
        for column in range(4):
            self.grade_frame.grid_columnconfigure(column, weight=1)

        self.grade_buttons: list[ctk.CTkButton] = []
        for column, (label, grade) in enumerate(
            [("Again", 1), ("Hard", 3), ("Good", 4), ("Easy", 5)]
        ):
            button = ctk.CTkButton(
                self.grade_frame,
                text=label,
                command=lambda selected_grade=grade: self.grade_current_card(selected_grade),
                height=42,
            )
            button.grid(row=0, column=column, padx=5, sticky="ew")
            self.grade_buttons.append(button)

        self.card_form = ctk.CTkFrame(content, corner_radius=8)
        self.card_form.grid(row=0, column=1, padx=(14, 0), sticky="nsew")
        self.card_form.grid_columnconfigure(0, weight=1)
        self.card_form.grid_rowconfigure(4, weight=1)

        form_title = ctk.CTkLabel(
            self.card_form,
            text="Add Card",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        form_title.grid(row=0, column=0, padx=22, pady=(22, 6), sticky="w")

        self.form_deck_label = ctk.CTkLabel(
            self.card_form,
            text="Choose a deck from the sidebar",
            text_color=("gray35", "gray72"),
        )
        self.form_deck_label.grid(row=1, column=0, padx=22, pady=(0, 16), sticky="w")

        self.front_entry = ctk.CTkTextbox(
            self.card_form,
            height=130,
            wrap="word",
            font=ctk.CTkFont(size=15),
        )
        self.front_entry.grid(row=2, column=0, padx=22, pady=(0, 12), sticky="ew")
        self.front_entry.insert("1.0", "Front")
        self.front_entry.bind("<FocusIn>", lambda _: self.clear_placeholder(self.front_entry, "Front"))

        self.back_entry = ctk.CTkTextbox(
            self.card_form,
            wrap="word",
            font=ctk.CTkFont(size=15),
        )
        self.back_entry.grid(row=3, column=0, padx=22, pady=(0, 14), sticky="nsew")
        self.back_entry.insert("1.0", "Back")
        self.back_entry.bind("<FocusIn>", lambda _: self.clear_placeholder(self.back_entry, "Back"))

        self.add_card_button = ctk.CTkButton(
            self.card_form,
            text="Add Card to Selected Deck",
            command=self.add_card,
            height=44,
            state="disabled",
        )
        self.add_card_button.grid(row=5, column=0, padx=22, pady=(0, 22), sticky="ew")

    def refresh_all(self) -> None:
        self.refresh_decks()
        self.load_next_due_card()

    def refresh_decks(self) -> None:
        for button in self.deck_buttons.values():
            button.destroy()
        self.deck_buttons.clear()

        decks = self.repository.list_decks()
        total_due = sum(deck.due_cards for deck in decks)
        self.due_summary.configure(text=f"{total_due} due today")

        for row, deck in enumerate(decks):
            label = f"{deck.name}  ({deck.due_cards}/{deck.total_cards})"
            button = ctk.CTkButton(
                self.deck_list,
                text=label,
                anchor="w",
                command=lambda deck_id=deck.id: self.select_deck(deck_id),
                height=34,
            )
            button.grid(row=row, column=0, pady=4, sticky="ew")
            self.deck_buttons[deck.id] = button

        self.update_selected_deck_text(decks)

    def select_deck(self, deck_id: Optional[int]) -> None:
        self.selected_deck_id = deck_id
        self.refresh_decks()
        self.load_next_due_card()

    def update_selected_deck_text(self, decks: list[Deck]) -> None:
        if self.selected_deck_id is None:
            self.scope_label.configure(text="All decks")
            self.form_deck_label.configure(text="Select a deck to add cards")
            self.add_card_button.configure(state="disabled")
            return

        selected = next((deck for deck in decks if deck.id == self.selected_deck_id), None)
        if selected is None:
            self.selected_deck_id = None
            self.scope_label.configure(text="All decks")
            self.form_deck_label.configure(text="Select a deck to add cards")
            self.add_card_button.configure(state="disabled")
            return

        self.scope_label.configure(
            text=f"{selected.name} - {selected.due_cards} due, {selected.total_cards} total"
        )
        self.form_deck_label.configure(text=f"Adding to: {selected.name}")
        self.add_card_button.configure(state="normal")

    def create_deck(self) -> None:
        try:
            self.repository.create_deck(self.new_deck_entry.get())
        except sqlite3.IntegrityError:
            messagebox.showerror("Deck exists", "A deck with that name already exists.")
            return
        except ValueError as error:
            messagebox.showerror("Missing name", str(error))
            return

        self.new_deck_entry.delete(0, "end")
        self.refresh_decks()

    def add_card(self) -> None:
        if self.selected_deck_id is None:
            messagebox.showinfo("Select a deck", "Choose a deck before adding a card.")
            return

        front = self.front_entry.get("1.0", "end").strip()
        back = self.back_entry.get("1.0", "end").strip()
        try:
            self.repository.add_card(self.selected_deck_id, front, back)
        except ValueError as error:
            messagebox.showerror("Incomplete card", str(error))
            return

        self.reset_textbox(self.front_entry, "Front")
        self.reset_textbox(self.back_entry, "Back")
        self.refresh_all()

    def load_next_due_card(self) -> None:
        self.current_card = self.repository.get_next_due_card(self.selected_deck_id)
        if self.current_card is None:
            self.review_status.configure(text="Review complete")
            self.set_textbox(self.front_label, "No cards are due right now.")
            self.set_textbox(
                self.back_label,
                "Create a deck, add cards, or come back when your next review is due.",
            )
            self.show_answer_button.configure(state="disabled")
            self.set_grade_buttons_state("disabled")
            return

        due_count = self.repository.due_count(self.selected_deck_id)
        self.review_status.configure(text=f"{due_count} card{'s' if due_count != 1 else ''} due")
        self.set_textbox(self.front_label, self.current_card.front)
        self.set_textbox(self.back_label, "")
        self.show_answer_button.configure(state="normal")
        self.set_grade_buttons_state("disabled")

    def show_answer(self) -> None:
        if self.current_card is None:
            return
        self.set_textbox(self.back_label, self.current_card.back)
        self.show_answer_button.configure(state="disabled")
        self.set_grade_buttons_state("normal")

    def grade_current_card(self, grade: int) -> None:
        if self.current_card is None:
            return
        self.repository.update_card_review(self.current_card.id, grade)
        self.refresh_all()

    def set_grade_buttons_state(self, state: str) -> None:
        for button in self.grade_buttons:
            button.configure(state=state)

    @staticmethod
    def clear_placeholder(textbox: ctk.CTkTextbox, placeholder: str) -> None:
        if textbox.get("1.0", "end").strip() == placeholder:
            textbox.delete("1.0", "end")

    @staticmethod
    def reset_textbox(textbox: ctk.CTkTextbox, placeholder: str) -> None:
        textbox.delete("1.0", "end")
        textbox.insert("1.0", placeholder)

    @staticmethod
    def set_textbox(textbox: ctk.CTkTextbox, text: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    def on_close(self) -> None:
        self.repository.close()
        self.destroy()


if __name__ == "__main__":
    app = FlashcardApp()
    app.load_next_due_card()
    app.mainloop()
