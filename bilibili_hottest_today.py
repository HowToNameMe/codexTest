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
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


RANKING_URL = "https://api.bilibili.com/x/web-interface/ranking/v2"
POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular"


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


def get_top_from_ranking(session: requests.Session) -> Optional[Video]:
    # rid=0 (all), type=all, day=1 (today)
    params = {"rid": 0, "type": "all", "day": 1}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    resp = session.get(RANKING_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    lst = (
        data.get("data", {})
        .get("list", {})
        .get("list", [])
    )
    if not lst:
        return None
    item = lst[0]
    stat = item.get("stat", {})
    owner = item.get("owner", {})
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


def get_top_from_popular(session: requests.Session) -> Optional[Video]:
    # popular feed defaults to hot videos now
    params = {"ps": 20, "pn": 1}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    resp = session.get(POPULAR_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    lst = data.get("data", {}).get("list", [])
    if not lst:
        return None
    # Choose the first item; alternatively, pick by max views if present
    first = lst[0]
    # Some fields differ slightly from ranking structure
    stat = first.get("stat", {})
    owner = first.get("owner", {})
    bvid = first.get("bvid") or ""
    url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
    return Video(
        title=first.get("title", ""),
        bvid=bvid,
        aid=first.get("aid"),
        author=owner.get("name", ""),
        author_mid=owner.get("mid"),
        view=stat.get("view"),
        like=stat.get("like"),
        coin=stat.get("coin"),
        favorite=stat.get("favorite"),
        share=stat.get("share"),
        danmaku=stat.get("danmaku"),
        duration=first.get("duration"),
        url=url,
    )


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
    except Exception:
        pass
    return get_top_from_popular(session)


def human_number(n: Optional[int]) -> str:
    if n is None:
        return "-"
    for unit in ["", "K", "M", "B"]:
        if abs(n) < 1000:
            return f"{n}{unit}"
        n //= 1000
    return f"{n}T"


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
    session = requests.Session()
    try:
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
    print("- Title: ", video.title)
    print("- Author:", video.author)
    print("- URL:   ", video.url)
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

