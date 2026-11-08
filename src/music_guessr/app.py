"""Flet app shell: shared state and bottom navigation."""

from __future__ import annotations

import flet as ft

from . import config, images, wikipedia
from .spotify import SpotifyAuth, SpotifyClient
from .storage import Storage
from .views.lists import ArtistsView, SongsView
from .views.play import PlayView
from .views.stats import StatsView

ACCENT = "#1DB954"


class AppState:
    def __init__(self):
        data = config.data_dir()
        self.storage = Storage(data / "music_guessr.sqlite3")
        self.auth = SpotifyAuth(config.SPOTIFY_CLIENT_ID, config.SPOTIFY_REDIRECT_URI, data / "spotify_token.json") \
            if config.SPOTIFY_CLIENT_ID else None
        self.spotify = SpotifyClient(self.auth) if self.auth else None
        self.login_waiting = False
        self.login_url = ""


def main(page: ft.Page):
    page.title = "Music Guessr"
    page.theme = ft.Theme(color_scheme_seed=ACCENT)
    page.dark_theme = ft.Theme(color_scheme_seed=ACCENT)
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.padding = 16

    state = AppState()
    body = ft.Container(expand=True)

    def on_round_finished():
        # Fetch Wikipedia links for newly guessed entries in the background.
        page.run_thread(_fill_links)

    def _fill_links():
        try:
            changed = wikipedia.fill_missing_links(state.storage)
            spotify = state.spotify if state.auth and state.auth.logged_in else None
            changed += images.fill_artist_images(state.storage, spotify)
            if changed:
                refresh_current()
        except Exception as exc:  # network trouble shouldn't break the game
            print("Background lookup failed:", exc)

    views = [
        lambda: PlayView(page, state, on_round_finished),
        lambda: SongsView(page, state),
        lambda: ArtistsView(page, state),
        lambda: StatsView(page, state),
    ]

    def show(index: int):
        body.content = views[index]()
        page.update()

    def refresh_current():
        if page.navigation_bar.selected_index != 0:  # don't reset a running round
            show(page.navigation_bar.selected_index)

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        on_change=lambda e: show(e.control.selected_index),
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.MUSIC_NOTE_OUTLINED, selected_icon=ft.Icons.MUSIC_NOTE, label="Play"),
            ft.NavigationBarDestination(icon=ft.Icons.QUEUE_MUSIC_OUTLINED, selected_icon=ft.Icons.QUEUE_MUSIC, label="Songs"),
            ft.NavigationBarDestination(icon=ft.Icons.PERSON_OUTLINE, selected_icon=ft.Icons.PERSON, label="Artists"),
            ft.NavigationBarDestination(icon=ft.Icons.INSIGHTS_OUTLINED, selected_icon=ft.Icons.INSIGHTS, label="Stats"),
        ],
    )
    page.add(ft.SafeArea(body, expand=True))
    show(0)
    page.run_thread(_fill_links)
