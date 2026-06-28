from __future__ import annotations

import sqlite3
from html import escape
from typing import Optional
from urllib.parse import quote

import streamlit as st

from spaced_core import FlashcardRepository


st.set_page_config(
    page_title="Spaced Retention",
    page_icon="SR",
    layout="centered",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_repository() -> FlashcardRepository:
    return FlashcardRepository()


def ensure_state() -> None:
    st.session_state.setdefault("selected_deck_id", None)
    st.session_state.setdefault("answer_visible", False)


def clear_query_flag(name: str) -> None:
    try:
        del st.query_params[name]
    except KeyError:
        pass


def select_deck(deck_id: Optional[int]) -> None:
    st.session_state.selected_deck_id = deck_id
    st.session_state.answer_visible = False
    st.query_params["topic"] = "all" if deck_id is None else str(deck_id)
    clear_query_flag("create_topic")


def sync_topic_from_query(decks: list) -> None:
    topic = st.query_params.get("topic")
    if topic is None:
        return

    if topic == "all":
        st.session_state.selected_deck_id = None
        return

    try:
        topic_id = int(topic)
    except ValueError:
        return

    if any(deck.id == topic_id for deck in decks):
        st.session_state.selected_deck_id = topic_id
    else:
        st.session_state.selected_deck_id = None


def grade_card(card_id: int, grade: int) -> None:
    get_repository().update_card_review(card_id, grade)
    st.session_state.answer_visible = False
    st.rerun()


def deck_name(deck_id: Optional[int], decks: list) -> str:
    if deck_id is None:
        return "All decks"
    selected = next((deck for deck in decks if deck.id == deck_id), None)
    return selected.name if selected else "All decks"


def topic_link(deck_id: Optional[int]) -> str:
    topic_value = "all" if deck_id is None else str(deck_id)
    return f"?topic={quote(topic_value)}"


def render_topic_tabs(repo: FlashcardRepository, decks: list) -> None:
    selected_deck_id = st.session_state.selected_deck_id
    all_active = selected_deck_id is None

    topic_tabs = [
        (
            "All Decks",
            topic_link(None),
            all_active,
            sum(deck.due_cards for deck in decks),
            sum(deck.total_cards for deck in decks),
        )
    ]
    topic_tabs.extend(
        (
            deck.name,
            topic_link(deck.id),
            selected_deck_id == deck.id,
            deck.due_cards,
            deck.total_cards,
        )
        for deck in decks
    )

    tab_html = "\n".join(
        f"""
        <a class="topic-tab {'active' if is_active else ''}" href="{href}" title="{escape(name)}">
            <span class="topic-label">{escape(name)}</span>
            <span class="topic-count">{due}/{total}</span>
            <span class="topic-caret"></span>
        </a>
        """
        for name, href, is_active, due, total in topic_tabs
    )

    st.markdown(
        f"""
        <div class="topic-tabbar">
            <a class="topic-icon" href="?create_topic=1" title="Create topic">+</a>
            <span class="topic-icon topic-menu" title="Topics menu">
                <span></span><span></span><span></span>
            </span>
            <div class="topic-tabs">{tab_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.query_params.get("create_topic") != "1":
        return

    with st.form("create_topic_tab", clear_on_submit=True):
        name = st.text_input("Topic name", placeholder="Python, OOPs, Biology...")
        submitted = st.form_submit_button("Create Topic", use_container_width=True)

    if not submitted:
        return

    try:
        repo.create_deck(name)
        created = next(
            (deck for deck in repo.list_decks() if deck.name.lower() == name.strip().lower()),
            None,
        )
        select_deck(created.id if created else None)
        st.success("Topic created.")
        st.rerun()
    except sqlite3.IntegrityError:
        st.error("A topic with that name already exists.")
    except ValueError as error:
        st.error(str(error))


def render_sidebar(repo: FlashcardRepository) -> list:
    decks = repo.list_decks()
    total_due = sum(deck.due_cards for deck in decks)

    st.sidebar.title("Spaced Retention")
    st.sidebar.caption(f"{total_due} due today")

    if st.sidebar.button("All Decks", use_container_width=True):
        select_deck(None)
        st.rerun()

    st.sidebar.subheader("Decks")
    if not decks:
        st.sidebar.info("Create your first deck below.")

    for deck in decks:
        label = f"{deck.name}  ({deck.due_cards}/{deck.total_cards})"
        if st.sidebar.button(label, key=f"deck-{deck.id}", use_container_width=True):
            select_deck(deck.id)
            st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("Create Deck")
    with st.sidebar.form("create_deck", clear_on_submit=True):
        name = st.text_input("Deck name", placeholder="Biology, Python, Exams...")
        submitted = st.form_submit_button("Create", use_container_width=True)
        if submitted:
            try:
                repo.create_deck(name)
                st.success("Deck created.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("A deck with that name already exists.")
            except ValueError as error:
                st.error(str(error))

    return decks


def render_review(repo: FlashcardRepository, selected_deck_id: Optional[int]) -> None:
    card = repo.get_next_due_card(selected_deck_id)
    due_count = repo.due_count(selected_deck_id)

    st.subheader(f"{due_count} due")

    if card is None:
        st.info("No cards are due right now.")
        return

    st.markdown(
        f"""
        <div class="flashcard front">
            <div class="label">Front</div>
            <div class="card-text">{card.front}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.answer_visible:
        if st.button("Show Answer", type="primary", use_container_width=True):
            st.session_state.answer_visible = True
            st.rerun()
        return

    st.markdown(
        f"""
        <div class="flashcard back">
            <div class="label">Back</div>
            <div class="card-text">{card.back}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    grades = [("Again", 1), ("Hard", 3), ("Good", 4), ("Easy", 5)]
    for column, (label, grade) in zip(cols, grades):
        if column.button(label, key=f"grade-{grade}", use_container_width=True):
            grade_card(card.id, grade)


def render_add_card(repo: FlashcardRepository, selected_deck_id: Optional[int], decks: list) -> None:
    st.subheader("Add Card")

    if not decks:
        st.warning("Create a deck before adding cards.")
        return

    selected = selected_deck_id
    if selected is None:
        selected = decks[0].id

    deck_options = {deck.name: deck.id for deck in decks}
    current_name = deck_name(selected, decks)
    names = list(deck_options.keys())
    default_index = names.index(current_name) if current_name in names else 0

    with st.form("add_card", clear_on_submit=True):
        chosen_name = st.selectbox("Deck", names, index=default_index)
        front = st.text_area("Front", height=120, placeholder="Question, prompt, or term")
        back = st.text_area("Back", height=160, placeholder="Answer, explanation, or definition")
        submitted = st.form_submit_button("Add Card", use_container_width=True)

    if submitted:
        try:
            repo.add_card(deck_options[chosen_name], front, back)
            select_deck(deck_options[chosen_name])
            st.success("Card added and ready for review.")
            st.rerun()
        except ValueError as error:
            st.error(str(error))


def main() -> None:
    ensure_state()
    repo = get_repository()
    decks = render_sidebar(repo)
    sync_topic_from_query(decks)

    selected_deck_id = st.session_state.selected_deck_id

    st.markdown(
        """
        <style>
            .block-container { padding-top: 1.6rem; max-width: 820px; }
            .topic-tabbar {
                align-items: stretch;
                background: #f4f5f8;
                border-bottom: 1px solid #c9cbd1;
                border-top: 1px solid #d9dbe0;
                display: flex;
                gap: 0;
                margin: -0.35rem 0 1.35rem;
                min-height: 34px;
                overflow-x: auto;
                white-space: nowrap;
            }
            .topic-icon {
                align-items: center;
                border-right: 1px solid #d8dae0;
                color: #344054;
                display: inline-flex;
                flex: 0 0 36px;
                font-size: 16px;
                font-weight: 700;
                justify-content: center;
                line-height: 1;
                text-decoration: none;
            }
            .topic-menu {
                flex-direction: column;
                gap: 3px;
            }
            .topic-menu span {
                background: #4b5563;
                border-radius: 999px;
                display: block;
                height: 1px;
                width: 12px;
            }
            .topic-tabs {
                align-items: stretch;
                display: flex;
                min-width: 0;
            }
            .topic-tab {
                align-items: center;
                background: #eceef2;
                border-right: 1px solid #d2d5db;
                color: #111827;
                display: inline-flex;
                gap: 7px;
                max-width: 170px;
                min-width: 92px;
                padding: 0 12px;
                text-decoration: none;
            }
            .topic-tab.active {
                background: #dceeff;
                color: #005fb8;
                font-weight: 700;
            }
            .topic-label {
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .topic-count {
                color: #667085;
                font-size: 0.72rem;
                font-weight: 600;
            }
            .topic-caret {
                border-left: 3.5px solid transparent;
                border-right: 3.5px solid transparent;
                border-top: 4px solid currentColor;
                display: inline-block;
                height: 0;
                opacity: 0.72;
                width: 0;
            }
            .flashcard {
                border: 1px solid rgba(128, 128, 128, 0.28);
                border-radius: 8px;
                padding: 1rem;
                margin: 0.8rem 0 1rem;
                background: rgba(128, 128, 128, 0.08);
            }
            .label {
                color: #6b7280;
                font-size: 0.82rem;
                font-weight: 700;
                text-transform: uppercase;
                margin-bottom: 0.45rem;
            }
            .card-text {
                font-size: 1.2rem;
                line-height: 1.55;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
            }
            .front .card-text {
                font-size: 1.45rem;
                font-weight: 700;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    render_topic_tabs(repo, decks)

    st.title("Spaced Retention")
    st.caption(deck_name(selected_deck_id, decks))

    review_tab, add_tab = st.tabs(["Review", "Add Cards"])
    with review_tab:
        render_review(repo, selected_deck_id)
    with add_tab:
        render_add_card(repo, selected_deck_id, decks)


if __name__ == "__main__":
    main()
