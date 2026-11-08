"""The two collections: successfully guessed songs and successfully guessed artists."""

from __future__ import annotations

import flet as ft


def _wiki_button(page: ft.Page, url: str | None) -> ft.Control | None:
    if not url:
        return None
    return ft.IconButton(ft.Icons.MENU_BOOK, tooltip="Open Wikipedia", on_click=lambda e: page.launch_url(url))


def _header(title: str, count: int) -> ft.Control:
    return ft.Row([ft.Text(title, size=26, weight=ft.FontWeight.BOLD), ft.Text(f"{count}", size=18, opacity=0.6)],
                  alignment=ft.MainAxisAlignment.SPACE_BETWEEN)


def _search_list(header: ft.Control, tiles: list[tuple[str, ft.Control]]) -> ft.Control:
    lv = ft.ListView(expand=True, spacing=2, controls=[t for _, t in tiles])

    def on_search(e):
        q = e.control.value.lower().strip()
        lv.controls = [t for key, t in tiles if q in key]
        lv.update()

    empty = ft.Text("Nothing guessed yet – go play a round!", italic=True, opacity=0.6)
    return ft.Column(expand=True, controls=[
        header,
        ft.TextField(hint_text="Search", prefix_icon=ft.Icons.SEARCH, dense=True, on_change=on_search),
        lv if tiles else empty,
    ])


def SongsView(page: ft.Page, state) -> ft.Control:  # noqa: N802
    songs = state.storage.guessed_songs()
    tiles = []
    for s in songs:
        leading = ft.Image(src=s["image_url"], width=48, height=48, border_radius=6) if s["image_url"] \
            else ft.Icon(ft.Icons.ALBUM)
        year = f" · {s['year']}" if s["year"] else ""
        tile = ft.ListTile(
            leading=leading,
            title=ft.Text(s["title"]),
            subtitle=ft.Text(f"{s['artists']}{year}  ·  guessed {s['times_guessed']}×"),
            trailing=_wiki_button(page, s["wiki_url"]),
        )
        tiles.append((f"{s['title']} {s['artists']}".lower(), tile))
    return _search_list(_header("Guessed songs", len(songs)), tiles)


def ArtistsView(page: ft.Page, state) -> ft.Control:  # noqa: N802
    artists = state.storage.guessed_artists()
    tiles = []
    for a in artists:
        tile = ft.ListTile(
            leading=ft.CircleAvatar(content=ft.Text(a["name"][:1].upper())),
            title=ft.Text(a["name"]),
            subtitle=ft.Text(f"guessed {a['times_guessed']}×"),
            trailing=_wiki_button(page, a["wiki_url"]),
        )
        tiles.append((a["name"].lower(), tile))
    return _search_list(_header("Guessed artists", len(artists)), tiles)
