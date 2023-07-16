"""Convert a YouTube playlist to a Spotify playlist.

The script will require the following environment variables to be set:

- YOUTUBE_TOKEN: A YouTube API token.
- SPOTIFY_TOKEN: A Spotify API token.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from typing import Callable
    from typing import Generator
    from typing import Sequence
    from typing import TypeVar

    T = TypeVar("T")


YOUTUBE_URL = "https://www.googleapis.com/youtube/v3"
SPOTIFY_URL = "https://api.spotify.com/v1"


def _log(level: str, color: str, message: str) -> None:
    sys.stdout.write(f"[{color}{level}\033[m] {message}\n")


def _debug(message: str) -> None:
    _log("DEBUG", "\033[35;1m", message)


def _info(message: str) -> None:
    _log("INFO", "\033[34;1m", message)


def _error(message: str) -> None:
    _log("ERROR", "\033[31;1m", message)


def _url_open(url: str, **kwargs: Any) -> dict[str, Any]:
    resp = urllib.request.urlopen(urllib.request.Request(url, **kwargs))
    return json.load(resp)


def _get_token(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        _error(f"Missing environment variable: {name!r}")
        raise SystemExit(1)
    return value


def _crop(s: str, length: int) -> str:
    if len(s) > length:
        return s[: length - 3] + "..."
    return s


def _progress_bar(
    sequence: Sequence[T],
    get_message: Callable[[T], str],
) -> Generator[T, None, None]:
    total = len(sequence)
    progress_columns = 40
    size = os.get_terminal_size()

    for i, item in enumerate(sequence, 1):
        yield item

        base = "\r    "
        base += "\033[32;1m"
        base += "━" * int((i / total) * progress_columns)
        base += "\033[37;2m"
        base += "━" * (progress_columns - int((i / total) * progress_columns))
        base += "\033[m  "
        msg = base + _crop(get_message(item), 40)
        sys.stdout.write("\r" + " " * size.columns)
        sys.stdout.write(msg)

    msg = base
    sys.stdout.write("\r" + " " * size.columns)
    sys.stdout.write(msg + "\n")


def _youtube_get_playlist_id(s: str) -> str:
    if s.startswith("https://www.youtube.com/playlist"):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(s).query)
        ret = query["list"][0]
    else:
        ret = s
    return ret


def _youtube_get_playlist_name(token: str, playlist_id: str) -> str:
    url = (
        f"{YOUTUBE_URL}/playlists?"
        f"&part=snippet"
        f"&id={playlist_id}"
        f"&key={token}"
    )
    ret = _url_open(url)
    return ret["items"][0]["snippet"]["title"]


def _youtube_get_tracks(token: str, playlist_id: str) -> list[dict[str, Any]]:
    base_url = (
        f"{YOUTUBE_URL}/playlistItems?"
        f"&part=snippet"
        f"&maxResults=50"
        f"&playlistId={playlist_id}"
        f"&key={token}"
    )
    ret = _url_open(base_url)
    tracks = ret["items"]

    while ret.get("nextPageToken"):
        url = f"{base_url}&pageToken={ret['nextPageToken']}"
        ret = _url_open(url)
        tracks.extend(ret["items"])

    return tracks


def _spotify_search_track(token: str, track: str) -> str:
    url = (
        f"{SPOTIFY_URL}/search?"
        f"&q={urllib.parse.quote_plus(track)}"
        f"&type=track"
        f"&limit=1"
    )
    ret = _url_open(url, headers={"Authorization": f"Bearer {token}"})
    return ret["tracks"]["items"][0]["uri"]


def _spotify_create_playlist(token: str, name: str) -> str:
    user = _url_open(
        f"{SPOTIFY_URL}/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    url = f"{SPOTIFY_URL}/users/{user['id']}/playlists"
    ret = _url_open(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        data=json.dumps({"name": name}).encode(),
    )
    return ret["id"]


def _spotify_add_to_playlist(
    token: str,
    playlist: str,
    tracks: Sequence[str],
) -> None:
    url = f"{SPOTIFY_URL}/playlists/{playlist}/tracks"
    _url_open(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        data=json.dumps({"uris": tracks}).encode(),
    )


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("youtube_playlist")
    parser.add_argument("-n", "--name")
    args = parser.parse_args(argv)

    yt_token = _get_token("YOUTUBE_TOKEN")
    sp_token = _get_token("SPOTIFY_TOKEN")
    _debug("Tokens found")

    youtube_playlist = _youtube_get_playlist_id(args.youtube_playlist)
    name = _youtube_get_playlist_name(yt_token, youtube_playlist)
    _debug(f"Youtube playlist found: {name!r}")

    tracks = _youtube_get_tracks(yt_token, youtube_playlist)
    _info(f"Found {len(tracks)} tracks in the playlist")

    _info("Searching for tracks on Spotify...")
    uris = []
    for track in _progress_bar(tracks, lambda x: x["snippet"]["title"]):
        uri = _spotify_search_track(sp_token, track["snippet"]["title"])
        uris.append(uri)

    spotify_playlist = _spotify_create_playlist(sp_token, args.name or name)
    _info("Spotify playlist created")

    for start in range(0, len(uris), 100):
        end = start + 100
        if end > len(uris):
            end = len(uris)
        _spotify_add_to_playlist(sp_token, spotify_playlist, uris[start:end])
    _info("Tracks added to playlist")

    _info("Done")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
