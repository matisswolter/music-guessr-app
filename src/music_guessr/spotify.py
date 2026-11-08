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
import random
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
    "user-library-read",  # Liked Songs
])
LIKED_SONGS = "liked"  # pseudo playlist id for the user's Liked Songs


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
    def missing_scopes(self) -> set[str]:
        """Permissions requested by this version but not granted to the stored login."""
        if not self.token:
            return set(SCOPES.split())
        return set(SCOPES.split()) - set(self.token.get("scope", "").split())

    @property
    def logged_in(self) -> bool:
        # A login from an older app version lacking new permissions counts as logged out.
        return bool(self.token) and not self.missing_scopes

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

    def wait_for_redirect(self, timeout: float = 300) -> None:
        """Listen on the loopback redirect URI (127.0.0.1) until Spotify sends the code, then exchange it.

        Call authorize_url() first and open that URL in a browser.
        """
        parsed = urllib.parse.urlparse(self.redirect_uri)
        result: dict = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                url = urllib.parse.urlparse(self.path)
                if url.path != parsed.path:  # e.g. /favicon.ico
                    self.send_response(404)
                    self.end_headers()
                    return
                result.update({k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()})
                ok = "code" in result
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                msg = "Logged in &ndash; you can close this tab and return to Music Guessr." if ok \
                    else f"Login failed: {result.get('error', 'unknown error')}"
                self.wfile.write(f"<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
                                 f"<h2>{msg}</h2></body>".encode())

            def log_message(self, *args):
                pass

        http.server.HTTPServer.allow_reuse_address = True
        server = http.server.HTTPServer((parsed.hostname, parsed.port or 80), Handler)
        server.timeout = 1
        deadline = time.time() + timeout
        try:
            while not result and time.time() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        if "code" not in result:
            raise RuntimeError(result.get("error", "Login timed out"))
        self.exchange_code(result["code"], result.get("state", ""))

    def login_with_loopback(self, open_url: Callable[[str], None], timeout: float = 300) -> None:
        """Desktop dev flow: open the browser and catch the redirect on 127.0.0.1."""
        url = self.authorize_url()
        threading.Timer(0.3, open_url, args=(url,)).start()
        self.wait_for_redirect(timeout)


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
        for attempt in range(3):
            headers = {"Authorization": f"Bearer {self.auth.access_token()}"}
            try:
                return request(method, url, headers=headers, **kw)
            except HTTPError as e:
                if e.status == 401 and attempt == 0:
                    self.auth.refresh()
                elif e.status == 429 and attempt < 2:
                    # Development Mode apps have a low rate limit; wait as Spotify asks (capped).
                    time.sleep(min(float(e.retry_after or 2), 15))
                else:
                    raise

    def _paged(self, path: str, params: dict | None = None):
        page = self._call("GET", path, params=params)
        while page:
            yield from page.get("items", [])
            page = self._call("GET", page["next"]) if page.get("next") else None

    def me(self) -> dict:
        return self._call("GET", "/me")

    def playlists(self) -> list[dict]:
        return [p for p in self._paged("/me/playlists", {"limit": 50}) if p]

    def can_read_playlist(self, playlist_id: str) -> bool:
        try:
            self._call("GET", f"/playlists/{playlist_id}/items", params={"limit": 1})
            return True
        except HTTPError as e:
            if e.status in (403, 404):
                return False
            raise

    def readable_playlists(self, cache_file: Path | None = None) -> tuple[list[dict], int]:
        """Playlists whose songs this app may read, plus the number of hidden ones.

        Apps in Spotify Development Mode may only read the contents of playlists the
        user owns or collaborates on; merely followed playlists answer 403. Own playlists
        are trusted, the others are probed once (sequentially, to respect the rate limit)
        and the result is cached per playlist version (snapshot_id).
        """
        cache: dict = {}
        if cache_file and cache_file.exists():
            try:
                cache = json.loads(cache_file.read_text())
            except ValueError:
                cache = {}
        me = self.me()["id"]
        playlists = self.playlists()
        readable = []
        for p in playlists:
            if (p.get("owner") or {}).get("id") == me or p.get("collaborative"):
                readable.append(p)
                continue
            key = f"{p['id']}:{p.get('snapshot_id', '')}"
            if key not in cache:
                cache[key] = self.can_read_playlist(p["id"])
            if cache[key]:
                readable.append(p)
        if cache_file:
            cache_file.write_text(json.dumps(cache))
        return readable, len(playlists) - len(readable)

    @staticmethod
    def playlist_size(playlist: dict) -> int | None:
        return (playlist.get("items") or playlist.get("tracks") or {}).get("total")

    def liked_songs_count(self) -> int:
        return self._call("GET", "/me/tracks", params={"limit": 1}).get("total", 0)

    def liked_tracks(self, max_tracks: int = 500, rng: random.Random | None = None) -> list[Track]:
        """Liked Songs; for big libraries a random sample of whole pages keeps loading fast."""
        page_size = 50
        total = self.liked_songs_count()
        offsets = list(range(0, total, page_size))
        if total > max_tracks:
            offsets = sorted((rng or random).sample(offsets, max_tracks // page_size))
        entries = []
        for offset in offsets:
            entries += self._call("GET", "/me/tracks", params={"limit": page_size, "offset": offset}).get("items", [])
        tracks = [_track_from_json(e.get("item") or e.get("track")) for e in entries]
        return [t for t in tracks if t]

    def playlist_tracks(self, playlist_id: str) -> list[Track]:
        if playlist_id == LIKED_SONGS:
            return self.liked_tracks()
        try:
            entries = list(self._paged(f"/playlists/{playlist_id}/items", {"limit": 50}))
        except HTTPError as e:
            if e.status == 403:
                raise PermissionError("Spotify only lets this app read playlists you own or collaborate on. "
                                      "Copy the songs into a playlist of your own to play them.") from None
            raise
        tracks = [_track_from_json(e.get("item") or e.get("track")) for e in entries]
        return [t for t in tracks if t]

    def artist_image(self, artist_id: str) -> str | None:
        if len(artist_id) != 22 or not artist_id.isalnum():  # not a real Spotify ID
            return None
        images = self._call("GET", f"/artists/{artist_id}").get("images") or []
        # images are sorted largest first; pick a mid-size one for list avatars
        return (images[1] if len(images) > 1 else images[0])["url"] if images else None

    # --- playback (Premium + an active Spotify device required) ---------------
    def devices(self) -> list[dict]:
        return self._call("GET", "/me/player/devices").get("devices", [])

    def play(self, uri: str, position_ms: int = 0, device_id: str | None = None) -> None:
        """Play on the active device; if none is active, wake up the first available one."""
        body = {"uris": [uri], "position_ms": position_ms}
        try:
            self._call("PUT", "/me/player/play", params={"device_id": device_id} if device_id else None, json_body=body)
        except HTTPError as e:
            devices = self.devices() if e.status == 404 and not device_id else []
            if not devices:
                raise
            self._call("PUT", "/me/player/play", params={"device_id": devices[0]["id"]}, json_body=body)

    def pause(self) -> None:
        try:
            self._call("PUT", "/me/player/pause")
        except HTTPError as e:
            if e.status not in (403, 404):  # already paused / no device
                raise
