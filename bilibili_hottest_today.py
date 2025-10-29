#!/usr/bin/env python3
"""
Fetch the hottest Bilibili video for today.

By default, uses Bilibili's ranking API for day=1 (today) and falls back to the
popular feed if ranking is unavailable. Outputs a concise summary and can also
emit JSON.

Usage examples:
  python bilibili_hottest_today.py
  python bilibili_hottest_today.py --source ranking
  python bilibili_hottest_today.py --source popular --json out.json

Notes:
- This script makes HTTP requests to Bilibili public web endpoints.
- No API key required. Network access is required when running it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


RANKING_URL = "https://api.bilibili.com/x/web-interface/ranking/v2"
POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular"
REQUEST_TIMEOUT = 15
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}


@dataclass
class Video:
    title: str
    bvid: str
    aid: Optional[int]
    author: str
    author_mid: Optional[int]
    view: Optional[int]
    like: Optional[int]
    coin: Optional[int]
    favorite: Optional[int]
    share: Optional[int]
    danmaku: Optional[int]
    duration: Optional[int]
    url: str


def _ensure_requests():
    if requests is None:
        print(
            "Error: The 'requests' package is required. Install with: pip install requests",
            file=sys.stderr,
        )
        sys.exit(2)


def _fetch_json(
    session: requests.Session,
    url: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Perform a GET request and return the decoded JSON payload."""
    resp = session.get(
        url,
        params=params,
        headers=DEFAULT_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _first_dict(items: Iterable[Any]) -> Optional[Dict[str, Any]]:
    """Return the first mapping in an iterable, or None if absent."""
    for item in items:
        if isinstance(item, dict):
            return item
        break
    return None


def _video_from_payload(item: Dict[str, Any]) -> Video:
    stat = item.get("stat") or {}
    owner = item.get("owner") or {}
    bvid = item.get("bvid") or ""
    url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
    return Video(
        title=item.get("title", ""),
        bvid=bvid,
        aid=item.get("aid"),
        author=owner.get("name", ""),
        author_mid=owner.get("mid"),
        view=stat.get("view"),
        like=stat.get("like"),
        coin=stat.get("coin"),
        favorite=stat.get("favorite"),
        share=stat.get("share"),
        danmaku=stat.get("danmaku"),
        duration=item.get("duration"),
        url=url,
    )


def get_top_from_ranking(session: requests.Session) -> Optional[Video]:
    # rid=0 (all), type=all, day=1 (today)
    params = {"rid": 0, "type": "all", "day": 1}
    data = _fetch_json(session, RANKING_URL, params)
    nested = data.get("data", {}).get("list", {}).get("list")
    if not isinstance(nested, list):
        return None
    item = _first_dict(nested)
    if item is None:
        return None
    return _video_from_payload(item)


def get_top_from_popular(session: requests.Session) -> Optional[Video]:
    # popular feed defaults to hot videos now
    params = {"ps": 20, "pn": 1}
    data = _fetch_json(session, POPULAR_URL, params)
    lst = data.get("data", {}).get("list")
    if not isinstance(lst, list):
        return None
    item = _first_dict(lst)
    if item is None:
        return None
    return _video_from_payload(item)


def pick_source(session: requests.Session, source: str) -> Optional[Video]:
    source = source.lower()
    if source == "ranking":
        return get_top_from_ranking(session)
    if source == "popular":
        return get_top_from_popular(session)
    # auto: try ranking then popular
    try:
        v = get_top_from_ranking(session)
        if v:
            return v
    except requests.RequestException as exc:
        print(f"Ranking source failed ({exc}); falling back to popular.", file=sys.stderr)
    return get_top_from_popular(session)


def human_number(n: Optional[int]) -> str:
    if n is None:
        return "-"
    num = float(n)
    for unit in ("", "K", "M", "B"):
        if abs(num) < 1000:
            break
        num /= 1000
    else:
        unit = "T"
    formatted = f"{num:.1f}".rstrip("0").rstrip(".")
    return f"{formatted}{unit}"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch hottest Bilibili video today")
    parser.add_argument(
        "--source",
        choices=["auto", "ranking", "popular"],
        default="auto",
        help="Data source: 'ranking' (day=1), 'popular', or 'auto'",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="Also write full JSON result to the given path",
    )
    args = parser.parse_args(argv)

    _ensure_requests()
    try:
        with requests.Session() as session:
            video = pick_source(session, args.source)
    except requests.RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # unexpected
        print(f"Failed to fetch data: {e}", file=sys.stderr)
        return 1

    if not video:
        print("No video found.")
        return 1

    # Human-readable summary
    print("Hottest video today")
    print(f"- Title:  {video.title}")
    print(f"- Author: {video.author}")
    print(f"- URL:    {video.url}")
    print(
        "- Stats: ",
        f"views {human_number(video.view)},",
        f"likes {human_number(video.like)},",
        f"coins {human_number(video.coin)},",
        f"favorites {human_number(video.favorite)},",
        f"shares {human_number(video.share)}",
    )

    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump(asdict(video), f, ensure_ascii=False, indent=2)
            print(f"Saved JSON to {args.json}")
        except OSError as e:
            print(f"Failed to write JSON: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
