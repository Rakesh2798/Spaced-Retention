from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from spaced_core import Card, Deck, FlashcardRepository


class SpacedRetentionRoot(BoxLayout):
    def __init__(self, repository: FlashcardRepository, **kwargs) -> None:
        super().__init__(orientation="vertical", padding=dp(14), spacing=dp(10), **kwargs)
        self.repository = repository
        self.decks: list[Deck] = []
        self.selected_deck_id: Optional[int] = None
        self.current_card: Optional[Card] = None
        self.answer_visible = False

        self.add_widget(self._header())
        self.add_widget(self._deck_picker())
        self.add_widget(self._review_area())
        self.add_widget(self._grade_buttons())
        self.add_widget(self._management_area())
        self.refresh_all()

    def _header(self) -> BoxLayout:
        header = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(62))
        title = Label(
            text="Spaced Retention",
            bold=True,
            font_size=dp(24),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(34),
        )
        title.bind(size=title.setter("text_size"))
        self.status_label = Label(
            text="",
            color=(0.62, 0.68, 0.76, 1),
            font_size=dp(14),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(24),
        )
        self.status_label.bind(size=self.status_label.setter("text_size"))
        header.add_widget(title)
        header.add_widget(self.status_label)
        return header

    def _deck_picker(self) -> BoxLayout:
        row = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint_y=None, height=dp(48))
        self.deck_spinner = Spinner(
            text="All Decks",
            values=["All Decks"],
            size_hint_x=1,
            font_size=dp(16),
        )
        self.deck_spinner.bind(text=self.on_deck_selected)
        refresh_button = Button(text="Refresh", size_hint_x=None, width=dp(96))
        refresh_button.bind(on_release=lambda _: self.refresh_all())
        row.add_widget(self.deck_spinner)
        row.add_widget(refresh_button)
        return row

    def _review_area(self) -> BoxLayout:
        wrapper = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=0.48)

        self.front_label = Label(
            text="",
            bold=True,
            font_size=dp(22),
            halign="left",
            valign="top",
            color=(1, 1, 1, 1),
            padding=(dp(8), dp(8)),
        )
        self.front_label.bind(size=self.front_label.setter("text_size"))
        front_scroll = ScrollView()
        front_scroll.add_widget(self.front_label)

        self.back_label = Label(
            text="",
            font_size=dp(18),
            halign="left",
            valign="top",
            color=(0.9, 0.94, 1, 1),
            padding=(dp(8), dp(8)),
        )
        self.back_label.bind(size=self.back_label.setter("text_size"))
        back_scroll = ScrollView()
        back_scroll.add_widget(self.back_label)

        self.show_answer_button = Button(text="Show Answer", size_hint_y=None, height=dp(48))
        self.show_answer_button.bind(on_release=lambda _: self.show_answer())

        wrapper.add_widget(front_scroll)
        wrapper.add_widget(back_scroll)
        wrapper.add_widget(self.show_answer_button)
        return wrapper

    def _grade_buttons(self) -> BoxLayout:
        row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint_y=None, height=dp(46))
        self.grade_buttons: list[Button] = []
        for label, grade in [("Again", 1), ("Hard", 3), ("Good", 4), ("Easy", 5)]:
            button = Button(text=label)
            button.bind(on_release=lambda _, selected_grade=grade: self.grade_card(selected_grade))
            self.grade_buttons.append(button)
            row.add_widget(button)
        return row

    def _management_area(self) -> BoxLayout:
        panel = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=0.42)

        self.new_deck_input = TextInput(
            hint_text="New deck name",
            multiline=False,
            size_hint_y=None,
            height=dp(46),
        )
        create_button = Button(text="Create Deck", size_hint_y=None, height=dp(44))
        create_button.bind(on_release=lambda _: self.create_deck())

        self.front_input = TextInput(hint_text="Card front", multiline=True, size_hint_y=0.42)
        self.back_input = TextInput(hint_text="Card back", multiline=True, size_hint_y=0.42)
        add_button = Button(text="Add Card to Selected Deck", size_hint_y=None, height=dp(46))
        add_button.bind(on_release=lambda _: self.add_card())

        panel.add_widget(self.new_deck_input)
        panel.add_widget(create_button)
        panel.add_widget(self.front_input)
        panel.add_widget(self.back_input)
        panel.add_widget(add_button)
        return panel

    def refresh_all(self) -> None:
        self.refresh_decks()
        self.load_next_card()

    def refresh_decks(self) -> None:
        self.decks = self.repository.list_decks()
        names = ["All Decks"] + [deck.name for deck in self.decks]
        self.deck_spinner.values = names

        if self.selected_deck_id is None:
            self.deck_spinner.text = "All Decks"
        else:
            selected = self.selected_deck()
            self.deck_spinner.text = selected.name if selected else "All Decks"
            if selected is None:
                self.selected_deck_id = None

        total_due = sum(deck.due_cards for deck in self.decks)
        total_cards = sum(deck.total_cards for deck in self.decks)
        self.status_label.text = f"{total_due} due today - {total_cards} total cards"

    def on_deck_selected(self, _: Spinner, text: str) -> None:
        if text == "All Decks":
            self.selected_deck_id = None
        else:
            deck = next((item for item in self.decks if item.name == text), None)
            self.selected_deck_id = deck.id if deck else None
        self.answer_visible = False
        self.load_next_card()

    def selected_deck(self) -> Optional[Deck]:
        return next((deck for deck in self.decks if deck.id == self.selected_deck_id), None)

    def create_deck(self) -> None:
        try:
            self.repository.create_deck(self.new_deck_input.text)
        except sqlite3.IntegrityError:
            self.show_popup("Deck exists", "A deck with that name already exists.")
            return
        except ValueError as error:
            self.show_popup("Missing name", str(error))
            return

        self.new_deck_input.text = ""
        self.refresh_all()

    def add_card(self) -> None:
        if self.selected_deck_id is None:
            if not self.decks:
                self.show_popup("Create a deck", "Create a deck before adding cards.")
                return
            self.selected_deck_id = self.decks[0].id

        try:
            self.repository.add_card(
                self.selected_deck_id,
                self.front_input.text,
                self.back_input.text,
            )
        except ValueError as error:
            self.show_popup("Incomplete card", str(error))
            return

        self.front_input.text = ""
        self.back_input.text = ""
        self.answer_visible = False
        self.refresh_all()

    def load_next_card(self) -> None:
        self.current_card = self.repository.get_next_due_card(self.selected_deck_id)
        due_count = self.repository.due_count(self.selected_deck_id)

        if self.current_card is None:
            self.front_label.text = "No cards are due right now."
            self.back_label.text = "Add new cards below, or come back when your next review is due."
            self.show_answer_button.disabled = True
            self.set_grade_buttons_disabled(True)
            self.status_label.text = f"{due_count} due in selected queue"
            return

        self.front_label.text = self.current_card.front
        self.back_label.text = ""
        self.show_answer_button.disabled = False
        self.set_grade_buttons_disabled(True)
        self.status_label.text = f"{due_count} due in selected queue"

    def show_answer(self) -> None:
        if self.current_card is None:
            return
        self.answer_visible = True
        self.back_label.text = self.current_card.back
        self.show_answer_button.disabled = True
        self.set_grade_buttons_disabled(False)

    def grade_card(self, grade: int) -> None:
        if self.current_card is None:
            return
        self.repository.update_card_review(self.current_card.id, grade)
        self.answer_visible = False
        self.refresh_all()

    def set_grade_buttons_disabled(self, disabled: bool) -> None:
        for button in self.grade_buttons:
            button.disabled = disabled

    @staticmethod
    def show_popup(title: str, message: str) -> None:
        Popup(
            title=title,
            content=Label(text=message),
            size_hint=(0.82, 0.34),
        ).open()


class SpacedRetentionAndroidApp(App):
    def build(self) -> SpacedRetentionRoot:
        Window.clearcolor = (0.07, 0.08, 0.1, 1)
        db_path = Path(self.user_data_dir) / "flashcards.db"
        self.repository = FlashcardRepository(db_path)
        return SpacedRetentionRoot(self.repository)

    def on_stop(self) -> None:
        self.repository.close()


if __name__ == "__main__":
    SpacedRetentionAndroidApp().run()
