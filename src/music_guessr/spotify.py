"""Spotify Web API: OAuth (Authorization Code + PKCE), playlists and playback control.

Playback goes through the Web API "remote control" endpoints, i.e. the user's own
Spotify app (phone, desktop, speaker) plays the song. This requires Spotify Premium
and an active device, but works from pure Python on every platform.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Callable

from .http import HTTPError, request
from .models import Artist, Track

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = " ".join([
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-playback-state",
    "user-modify-playback-state",
])


class SpotifyAuth:
    def __init__(self, client_id: str, redirect_uri: str, token_file: Path):
        if not client_id:
            raise ValueError("SPOTIFY_CLIENT_ID is not set – see README.md")
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.token_file = token_file
        self._verifier = ""
        self._state = ""
        self.token: dict | None = json.loads(token_file.read_text()) if token_file.exists() else None

    @property
    def logged_in(self) -> bool:
        return bool(self.token)

    def authorize_url(self) -> str:
        self._verifier = secrets.token_urlsafe(64)[:128]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self._verifier.encode()).digest()).rstrip(b"=").decode()
        self._state = secrets.token_urlsafe(16)
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "scope": SCOPES,
            "state": self._state,
        })

    def exchange_code(self, code: str, state: str) -> None:
        if state != self._state:
            raise ValueError("OAuth state mismatch")
        self._save(request("POST", TOKEN_URL, form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": self._verifier,
        }))

    def access_token(self) -> str:
        if not self.token:
            raise RuntimeError("Not logged in")
        if time.time() > self.token["expires_at"] - 60:
            self.refresh()
        return self.token["access_token"]

    def refresh(self) -> None:
        data = request("POST", TOKEN_URL, form={
            "grant_type": "refresh_token",
            "refresh_token": self.token["refresh_token"],
            "client_id": self.client_id,
        })
        data.setdefault("refresh_token", self.token["refresh_token"])
        self._save(data)

    def logout(self) -> None:
        self.token = None
        self.token_file.unlink(missing_ok=True)

    def _save(self, data: dict) -> None:
        data["expires_at"] = time.time() + data.get("expires_in", 3600)
        self.token = data
        self.token_file.write_text(json.dumps(data))

    def login_with_loopback(self, open_url: Callable[[str], None], timeout: float = 300) -> None:
        """Desktop dev flow: open the browser and catch the redirect on 127.0.0.1."""
        parsed = urllib.parse.urlparse(self.redirect_uri)
        result: dict = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result.update({k: v[0] for k, v in qs.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h2>Logged in – you can return to Music Guessr.</h2>".encode())

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer((parsed.hostname, parsed.port or 80), Handler)
        server.timeout = timeout
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        open_url(self.authorize_url())
        thread.join(timeout)
        server.server_close()
        if "code" not in result:
            raise RuntimeError(result.get("error", "Login timed out"))
        self.exchange_code(result["code"], result.get("state", ""))


def _track_from_json(t: dict) -> Track | None:
    if not t or t.get("type", "track") != "track" or t.get("is_local") or not t.get("id"):
        return None
    album = t.get("album") or {}
    date = album.get("release_date") or ""
    images = album.get("images") or []
    return Track(
        id=t["id"],
        title=t["name"],
        artists=tuple(Artist(a.get("id") or a["name"], a["name"]) for a in t.get("artists", [])),
        year=int(date[:4]) if date[:4].isdigit() else None,
        uri=t["uri"],
        album=album.get("name", ""),
        image_url=images[0]["url"] if images else None,
        duration_ms=t.get("duration_ms", 0),
    )


class SpotifyClient:
    def __init__(self, auth: SpotifyAuth):
        self.auth = auth

    def _call(self, method: str, path: str, **kw):
        url = path if path.startswith("http") else API + path
        headers = {"Authorization": f"Bearer {self.auth.access_token()}"}
        try:
            return request(method, url, headers=headers, **kw)
        except HTTPError as e:
            if e.status != 401:
                raise
            self.auth.refresh()
            headers = {"Authorization": f"Bearer {self.auth.access_token()}"}
            return request(method, url, headers=headers, **kw)

    def _paged(self, path: str, params: dict | None = None):
        page = self._call("GET", path, params=params)
        while page:
            yield from page.get("items", [])
            page = self._call("GET", page["next"]) if page.get("next") else None

    def me(self) -> dict:
        return self._call("GET", "/me")

    def playlists(self) -> list[dict]:
        return [p for p in self._paged("/me/playlists", {"limit": 50}) if p]

    def playlist_tracks(self, playlist_id: str) -> list[Track]:
        # Spotify renamed /tracks -> /items (and item["track"] -> item["item"]); support both.
        try:
            entries = list(self._paged(f"/playlists/{playlist_id}/items", {"limit": 50}))
        except HTTPError as e:
            if e.status != 404:
                raise
            entries = list(self._paged(f"/playlists/{playlist_id}/tracks", {"limit": 100}))
        tracks = [_track_from_json(e.get("item") or e.get("track")) for e in entries]
        return [t for t in tracks if t]

    # --- playback (Premium + an active Spotify device required) ---------------
    def devices(self) -> list[dict]:
        return self._call("GET", "/me/player/devices").get("devices", [])

    def play(self, uri: str, position_ms: int = 0, device_id: str | None = None) -> None:
        params = {"device_id": device_id} if device_id else None
        self._call("PUT", "/me/player/play", params=params, json_body={"uris": [uri], "position_ms": position_ms})

    def pause(self) -> None:
        try:
            self._call("PUT", "/me/player/pause")
        except HTTPError as e:
            if e.status not in (403, 404):  # already paused / no device
                raise
