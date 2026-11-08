"""Game screen: pick a playlist, listen, guess artist / title / year, see the answer."""

from __future__ import annotations

import flet as ft

from ..game import GameSession
from ..http import HTTPError


def PlayView(page: ft.Page, state, on_round_finished) -> ft.Control:  # noqa: N802
    root = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=14)

    def snack(msg: str):
        page.open(ft.SnackBar(ft.Text(msg)))

    if state.spotify is None:
        root.controls = [ft.Text("Music Guessr", size=28, weight=ft.FontWeight.BOLD),
                         ft.Text("Set SPOTIFY_CLIENT_ID first (see README.md).")]
        return root

    if not state.auth.logged_in:
        def login(e):
            def run():
                try:
                    state.auth.login_with_loopback(page.launch_url)
                    root.controls = PlayView(page, state, on_round_finished).controls
                    page.update()
                except Exception as exc:
                    snack(f"Login failed: {exc}")
            page.run_thread(run)

        root.controls = [
            ft.Text("Music Guessr", size=28, weight=ft.FontWeight.BOLD),
            ft.Text("Guess artist, title and year of songs from your own playlists."),
            ft.FilledButton("Log in with Spotify", icon=ft.Icons.LOGIN, on_click=login),
        ]
        return root

    session: dict = {"game": None, "playlist_id": None}

    playlist_dd = ft.Dropdown(label="Playlist", expand=True)
    try:
        playlist_dd.options = [ft.dropdown.Option(key=p["id"], text=p["name"]) for p in state.spotify.playlists()]
    except (HTTPError, OSError) as exc:
        snack(f"Could not load playlists: {exc}")

    status = ft.Text(opacity=0.7)
    artist_tf = ft.TextField(label="Artist", prefix_icon=ft.Icons.PERSON)
    title_tf = ft.TextField(label="Title", prefix_icon=ft.Icons.MUSIC_NOTE)
    year_tf = ft.TextField(label="Year", prefix_icon=ft.Icons.CALENDAR_MONTH, keyboard_type=ft.KeyboardType.NUMBER,
                           max_length=4)
    reveal = ft.Container()
    guess_area = ft.Column(visible=False, spacing=10)

    def play_current(e=None):
        game, track = session["game"], session["game"].current
        try:
            state.spotify.play(track.uri, game.snippet_start_ms(track))
        except HTTPError as exc:
            snack("Open Spotify on a device first (Premium required)." if exc.status == 404 else str(exc))

    def next_round(e=None):
        game = session["game"]
        track = game.next_track()
        if track is None:
            status.value = f"Playlist finished! Score: {game.score} points in {game.rounds} rounds."
            guess_area.visible = False
            page.update()
            return
        for tf in (artist_tf, title_tf, year_tf):
            tf.value = ""
        reveal.content = None
        submit_btn.visible, next_btn.visible = True, False
        status.value = f"Round {game.rounds + 1} · {game.remaining} songs left · score {game.score}"
        guess_area.visible = True
        page.update()
        play_current()

    def mark(ok: bool, label: str, value: str) -> ft.Control:
        icon = ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.CANCEL, color=ft.Colors.GREEN if ok else ft.Colors.RED)
        return ft.Row([icon, ft.Text(f"{label}: ", weight=ft.FontWeight.BOLD), ft.Text(value, expand=True)])

    def submit(e):
        game = session["game"]
        track = game.current
        result = game.submit(artist_tf.value, title_tf.value, year_tf.value)
        state.storage.record_round(track, result, session["playlist_id"])
        state.spotify.pause()
        year_ok = result.year_diff is not None and result.year_diff <= 2
        year_txt = f"{track.year}" + ("" if result.year_diff in (None, 0) else f" (off by {result.year_diff})")
        reveal.content = ft.Card(ft.Container(padding=14, content=ft.Row([
            ft.Image(src=track.image_url, width=96, height=96, border_radius=8) if track.image_url else ft.Icon(ft.Icons.ALBUM, size=96),
            ft.Column(expand=True, controls=[
                mark(result.artist_ok, "Artist", track.artist_names),
                mark(result.title_ok, "Title", track.title),
                mark(year_ok, "Year", year_txt),
                ft.Text(f"+{result.points} points", size=18, weight=ft.FontWeight.BOLD),
            ]),
        ])))
        submit_btn.visible, next_btn.visible = False, True
        status.value = f"Round {game.rounds} · {game.remaining} songs left · score {game.score}"
        page.update()
        if result.artist_ok or result.title_ok:
            on_round_finished()

    def start(e):
        if not playlist_dd.value:
            snack("Choose a playlist first")
            return
        try:
            tracks = state.spotify.playlist_tracks(playlist_dd.value)
        except (HTTPError, OSError) as exc:
            snack(f"Could not load tracks: {exc}")
            return
        if not tracks:
            snack("This playlist has no playable tracks")
            return
        session["playlist_id"] = playlist_dd.value
        session["game"] = GameSession(tracks, skip_ids=state.storage.guessed_track_ids())
        next_round()

    submit_btn = ft.FilledButton("Guess!", icon=ft.Icons.CHECK, on_click=submit)
    next_btn = ft.FilledTonalButton("Next song", icon=ft.Icons.SKIP_NEXT, on_click=next_round, visible=False)
    guess_area.controls = [
        status,
        ft.OutlinedButton("Replay snippet", icon=ft.Icons.REPLAY, on_click=play_current),
        artist_tf, title_tf, year_tf,
        ft.Row([submit_btn, next_btn]),
        reveal,
    ]
    root.controls = [
        ft.Text("Music Guessr", size=28, weight=ft.FontWeight.BOLD),
        ft.Row([playlist_dd, ft.FilledButton("Start", icon=ft.Icons.PLAY_ARROW, on_click=start)]),
        guess_area,
    ]
    return root
