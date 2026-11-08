"""Game screen: import playlists, listen to a Deezer preview, guess artist / title / year."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import flet as ft

from .. import config, deezer, importer
from ..game import GameSession
from ..models import Track

EXPORTIFY_URL = "https://exportify.net"
SPOTIFY_DATA_URL = "https://www.spotify.com/account/privacy/"


def _settings_file() -> Path:
    return config.data_dir() / "settings.json"


def _load_settings() -> dict:
    try:
        return json.loads(_settings_file().read_text())
    except (OSError, ValueError):
        return {}


def _save_setting(key: str, value) -> None:
    settings = _load_settings()
    settings[key] = value
    _settings_file().write_text(json.dumps(settings))


def resolve(state, track: Track) -> tuple[Track, dict] | None:
    """Find (or reuse the cached) Deezer match; returns the track enriched with cover/year, or None."""
    cached = state.storage.deezer_match(track.id)
    if cached is None:
        state.storage.set_deezer_match(track.id, deezer.find(track))
        cached = state.storage.deezer_match(track.id)
    if not cached["deezer_id"]:
        return None
    year = track.year
    if year is None and (cached["release_date"] or "")[:4].isdigit():
        year = int(cached["release_date"][:4])
    return dataclasses.replace(track, image_url=cached["cover_url"], year=year), cached


def PlayView(page: ft.Page, state, on_round_finished) -> ft.Control:  # noqa: N802
    root = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=14)
    session: dict = {"game": None, "playlist_id": None, "match": None, "skipped": 0}

    def snack(msg: str):
        page.open(ft.SnackBar(ft.Text(msg)))

    # --- audio (one player, created on first use) ---------------------------------
    player: dict = {"audio": None}

    def play_url(url: str):
        if player["audio"] is None:
            player["audio"] = ft.Audio(src=url, autoplay=True)
            page.overlay.append(player["audio"])
            page.update()
        else:
            player["audio"].src = url
            player["audio"].autoplay = True
            player["audio"].update()

    def stop_audio():
        if player["audio"] is not None:
            player["audio"].pause()

    # --- playlist import ---------------------------------------------------------------
    playlist_dd = ft.Dropdown(label="Playlist", expand=True,
                              on_change=lambda e: _save_setting("last_playlist", e.control.value))
    busy = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)

    def refresh_playlists(select: str | None = None):
        pls = state.storage.playlists()
        playlist_dd.options = [ft.dropdown.Option(key=p["id"], text=f"{p['name']} ({p['size']})") for p in pls]
        keys = {p["id"] for p in pls}
        wanted = select or playlist_dd.value or _load_settings().get("last_playlist")
        playlist_dd.value = wanted if wanted in keys else None
        empty_hint.visible = not pls

    def import_content(file_name: str, content: bytes):
        try:
            imported = importer.parse_file(file_name, content)
        except importer.ImportError_ as exc:
            snack(f"{file_name}: {exc}")
            return
        last = None
        for pl in imported:
            last = state.storage.save_playlist(pl.name, pl.tracks, pl.source)
        names = ", ".join(f"{p.name} ({len(p.tracks)})" for p in imported[:3])
        more = f" and {len(imported) - 3} more" if len(imported) > 3 else ""
        snack(f"Imported {names}{more}")
        refresh_playlists(select=last if len(imported) == 1 else None)
        if last and len(imported) == 1:
            _save_setting("last_playlist", last)
        page.update()

    upload_dir = config.upload_dir()

    def on_pick(e: ft.FilePickerResultEvent):
        if not e.files:
            return
        to_upload = []
        for f in e.files:
            if f.path:  # desktop / mobile: we can read the file directly
                import_content(f.name, Path(f.path).read_bytes())
            else:  # web: the browser uploads the file to our upload_dir first
                to_upload.append(ft.FilePickerUploadFile(f.name, upload_url=page.get_upload_url(f.name, 600)))
        if to_upload:
            picker.upload(to_upload)

    def on_upload(e: ft.FilePickerUploadEvent):
        if e.error:
            snack(f"Upload failed: {e.error}")
        elif e.progress == 1.0:
            path = upload_dir / e.file_name
            try:
                import_content(e.file_name, path.read_bytes())
            finally:
                path.unlink(missing_ok=True)

    picker = ft.FilePicker(on_result=on_pick, on_upload=on_upload)
    page.overlay.append(picker)

    def pick(e):
        picker.pick_files(dialog_title="Import playlist", allow_multiple=True,
                          file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["csv", "json"])

    def delete_playlist(e):
        if not playlist_dd.value:
            return
        name = next((o.text for o in playlist_dd.options if o.key == playlist_dd.value), "")
        state.storage.delete_playlist(playlist_dd.value)
        playlist_dd.value = None
        refresh_playlists()
        snack(f"Removed {name}")
        page.update()

    empty_hint = ft.Container(
        padding=12, border_radius=10, bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        content=ft.Column(spacing=6, controls=[
            ft.Text("How to get your playlists in", weight=ft.FontWeight.BOLD),
            ft.Text("1. Open exportify.net, log in with Spotify and export a playlist as CSV, "
                    "or request \"Account data\" in Spotify's privacy settings (Playlist1.json, YourLibrary.json)."),
            ft.Text("2. Tap Import and choose the file(s)."),
            ft.Row(wrap=True, controls=[
                ft.TextButton("exportify.net", icon=ft.Icons.OPEN_IN_NEW, url=EXPORTIFY_URL),
                ft.TextButton("Spotify data export", icon=ft.Icons.OPEN_IN_NEW, url=SPOTIFY_DATA_URL),
            ]),
        ]),
    )

    # --- game -----------------------------------------------------------------------------
    status = ft.Text(opacity=0.7)
    artist_tf = ft.TextField(label="Artist", prefix_icon=ft.Icons.PERSON)
    title_tf = ft.TextField(label="Title", prefix_icon=ft.Icons.MUSIC_NOTE)
    year_tf = ft.TextField(label="Year", prefix_icon=ft.Icons.CALENDAR_MONTH, keyboard_type=ft.KeyboardType.NUMBER,
                           max_length=4)
    reveal = ft.Container()
    guess_area = ft.Column(visible=False, spacing=10)

    def replay(e=None):
        match = session["match"]
        url = deezer.preview_url(match["deezer_id"]) if match else None
        if url:
            play_url(url)
        else:
            snack("Preview not available right now")

    def prefetch_next():
        game = session["game"]
        nxt = game.peek_next() if game else None
        if nxt is not None and state.storage.deezer_match(nxt.id) is None:
            try:
                resolve(state, nxt)
            except OSError:
                pass

    def status_line(game: GameSession, done: int) -> str:
        skipped = f" · {session['skipped']} without preview" if session["skipped"] else ""
        return f"Round {done} · {game.remaining} songs left · score {game.score}{skipped}"

    def next_round(e=None):
        game = session["game"]
        stop_audio()
        busy.visible = True
        status.value = "Finding the next preview…"
        page.update()
        while True:
            track = game.next_track()
            if track is None:
                busy.visible = False
                status.value = f"Playlist finished! Score: {game.score} points in {game.rounds} rounds."
                guess_area.visible = True
                submit_btn.visible = next_btn.visible = False
                page.update()
                return
            try:
                found = resolve(state, track)
                url = deezer.preview_url(found[1]["deezer_id"]) if found else None
            except OSError:
                found, url = None, None
            if found and url:
                break
            session["skipped"] += 1
        game.current, session["match"] = found
        for tf in (artist_tf, title_tf, year_tf):
            tf.value = ""
        reveal.content = None
        submit_btn.visible, next_btn.visible = True, False
        busy.visible = False
        status.value = status_line(game, game.rounds + 1)
        guess_area.visible = True
        page.update()
        play_url(url)
        page.run_thread(prefetch_next)

    def mark(ok: bool, label: str, value: str) -> ft.Control:
        icon = ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.CANCEL, color=ft.Colors.GREEN if ok else ft.Colors.RED)
        return ft.Row([icon, ft.Text(f"{label}: ", weight=ft.FontWeight.BOLD), ft.Text(value, expand=True)])

    def submit(e):
        game = session["game"]
        track = game.current
        result = game.submit(artist_tf.value, title_tf.value, year_tf.value)
        state.storage.record_round(track, result, session["playlist_id"])
        stop_audio()
        year_ok = result.year_diff is not None and result.year_diff <= 2
        year_txt = f"{track.year}" if track.year else "unknown"
        if result.year_diff not in (None, 0):
            year_txt += f" (off by {result.year_diff})"
        reveal.content = ft.Card(ft.Container(padding=14, content=ft.Column(spacing=8, controls=[
            ft.Row(vertical_alignment=ft.CrossAxisAlignment.START, controls=[
                ft.Image(src=track.image_url, width=120, height=120, border_radius=8, fit=ft.ImageFit.COVER)
                if track.image_url else ft.Icon(ft.Icons.ALBUM, size=120),
                ft.Column(expand=True, controls=[
                    mark(result.artist_ok, "Artist", track.artist_names),
                    mark(result.title_ok, "Title", track.title),
                    mark(year_ok, "Year", year_txt),
                    ft.Text(f"+{result.points} points", size=18, weight=ft.FontWeight.BOLD),
                ]),
            ]),
            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                ft.Text("Preview by Deezer", size=12, opacity=0.6),
                ft.TextButton("Open in Deezer", icon=ft.Icons.OPEN_IN_NEW, url=session["match"]["link"]),
            ]),
        ])))
        submit_btn.visible, next_btn.visible = False, True
        status.value = status_line(game, game.rounds)
        page.update()
        if result.artist_ok or result.title_ok:
            on_round_finished()

    def start(e):
        if not playlist_dd.value:
            snack("Import and choose a playlist first")
            return
        tracks = state.storage.playlist_tracks(playlist_dd.value)
        if not tracks:
            snack("This playlist is empty")
            return
        _save_setting("last_playlist", playlist_dd.value)
        session.update(playlist_id=playlist_dd.value, skipped=0,
                       game=GameSession(tracks, skip_ids=state.storage.guessed_track_ids()))
        next_round()

    submit_btn = ft.FilledButton("Guess!", icon=ft.Icons.CHECK, on_click=submit)
    next_btn = ft.FilledTonalButton("Next song", icon=ft.Icons.SKIP_NEXT, on_click=next_round, visible=False)
    guess_area.controls = [
        status,
        ft.OutlinedButton("Replay snippet", icon=ft.Icons.REPLAY, on_click=replay),
        artist_tf, title_tf, year_tf,
        ft.Row([submit_btn, next_btn]),
        reveal,
    ]
    root.controls = [
        ft.Row([ft.Text("Music Guessr", size=28, weight=ft.FontWeight.BOLD),
                ft.Row(spacing=0, controls=[
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove selected playlist", on_click=delete_playlist),
                    ft.FilledTonalButton("Import", icon=ft.Icons.FILE_UPLOAD, on_click=pick),
                ])],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Row([playlist_dd, busy, ft.FilledButton("Start", icon=ft.Icons.PLAY_ARROW, on_click=start)]),
        empty_hint,
        guess_area,
    ]
    refresh_playlists()
    return root
