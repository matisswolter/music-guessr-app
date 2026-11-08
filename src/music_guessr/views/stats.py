"""The statistics page: KPI tiles, accuracy rings, progress line, decade bars, top artists."""

from __future__ import annotations

import flet as ft

from .. import stats as stats_mod

C_ARTIST, C_TITLE, C_YEAR = "#1DB954", "#3B82F6", "#F59E0B"


def _tile(label: str, value: str, icon: str) -> ft.Control:
    return ft.Card(ft.Container(padding=14, width=160, content=ft.Column(spacing=2, controls=[
        ft.Icon(icon, opacity=0.7),
        ft.Text(value, size=28, weight=ft.FontWeight.BOLD),
        ft.Text(label, size=12, opacity=0.7),
    ])))


def _ring(label: str, rate: float, color: str) -> ft.Control:
    return ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[
        ft.Stack(width=84, height=84, controls=[
            ft.ProgressRing(value=rate, width=84, height=84, stroke_width=9, color=color,
                            bgcolor=ft.Colors.with_opacity(0.15, color)),
            ft.Container(ft.Text(f"{rate:.0%}", size=18, weight=ft.FontWeight.BOLD),
                         alignment=ft.alignment.center, width=84, height=84),
        ]),
        ft.Text(label, size=12),
    ])


def _section(title: str, content: ft.Control) -> ft.Control:
    return ft.Card(ft.Container(padding=16, content=ft.Column([
        ft.Text(title, size=16, weight=ft.FontWeight.BOLD), content])))


def StatsView(page: ft.Page, state) -> ft.Control:  # noqa: N802
    s = stats_mod.compute(state.storage.rounds())
    songs, artists = len(state.storage.guessed_songs()), len(state.storage.guessed_artists())
    if s.rounds == 0:
        return ft.Column([ft.Text("Stats", size=26, weight=ft.FontWeight.BOLD),
                          ft.Text("Play a few rounds to see your stats here.", italic=True, opacity=0.6)])

    progress = ft.LineChart(
        height=200, min_y=0, expand=True,
        data_series=[ft.LineChartData(
            data_points=[ft.LineChartDataPoint(x, y) for x, y in s.cumulative_points],
            curved=True, stroke_width=3, color=C_ARTIST,
            below_line_bgcolor=ft.Colors.with_opacity(0.15, C_ARTIST),
        )],
        left_axis=ft.ChartAxis(labels_size=36),
        bottom_axis=ft.ChartAxis(title=ft.Text("round", size=11), labels_size=24),
        horizontal_grid_lines=ft.ChartGridLines(color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE), width=1),
        tooltip_bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.SURFACE),
    )

    decades = ft.BarChart(
        height=200, max_y=100, expand=True,
        bar_groups=[ft.BarChartGroup(x=i, bar_rods=[ft.BarChartRod(
            from_y=0, to_y=rate * 100, width=22, color=C_TITLE, border_radius=4,
            tooltip=f"{label}: {rate:.0%} of {n} songs")]) for i, (label, rate, n) in enumerate(s.decade_accuracy)],
        bottom_axis=ft.ChartAxis(labels_size=28, labels=[
            ft.ChartAxisLabel(value=i, label=ft.Text(label, size=11)) for i, (label, _, _) in enumerate(s.decade_accuracy)]),
        left_axis=ft.ChartAxis(labels_size=36),
        horizontal_grid_lines=ft.ChartGridLines(color=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE), width=1),
    )

    top = ft.Column(spacing=6, controls=[
        ft.Row([ft.Text(name, expand=True),
                ft.ProgressBar(value=count / s.top_artists[0][1], width=140, color=C_ARTIST),
                ft.Text(str(count), width=30, text_align=ft.TextAlign.RIGHT)])
        for name, count in s.top_artists
    ] or [ft.Text("No artists guessed yet", italic=True)])

    avg_err = f"{s.avg_year_error:.1f} yrs" if s.avg_year_error is not None else "–"
    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12, controls=[
        ft.Text("Stats", size=26, weight=ft.FontWeight.BOLD),
        ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[
            _tile("points", str(s.points), ft.Icons.EMOJI_EVENTS),
            _tile("rounds played", str(s.rounds), ft.Icons.REPLAY),
            _tile("songs collected", str(songs), ft.Icons.QUEUE_MUSIC),
            _tile("artists collected", str(artists), ft.Icons.PERSON),
            _tile("best streak", str(s.best_streak), ft.Icons.LOCAL_FIRE_DEPARTMENT),
            _tile("perfect rounds", str(s.perfect_rounds), ft.Icons.STAR),
        ]),
        _section("Accuracy", ft.Row(alignment=ft.MainAxisAlignment.SPACE_AROUND, wrap=True, controls=[
            _ring("Artist", s.artist_rate, C_ARTIST),
            _ring("Title", s.title_rate, C_TITLE),
            _ring("Year ±2", s.year_close_rate, C_YEAR),
        ])),
        ft.Text(f"Exact year {s.year_exact_rate:.0%} · average year error {avg_err} · current streak {s.current_streak}",
                size=12, opacity=0.7),
        _section("Progress (total points)", progress),
        _section("Title accuracy by decade", decades if s.decade_accuracy else ft.Text("–")),
        _section("Most guessed artists", top),
    ])
