#!/usr/bin/env python3
"""Rotate through tracked brands and update the public Google Trends snapshot."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRACKED = [
    ("medicube", "medicube", "US", "미국"),
    ("aprilskin", "APRILSKIN", "US", "미국"),
    ("ager", "Medicube AGE-R", "US", "미국"),
    ("cosrx", "COSRX", "US", "미국"),
    ("laneige", "LANEIGE", "US", "미국"),
    ("roundlab", "ROUND LAB skincare", "US", "미국"),
    ("anua", "ANUA skincare", "US", "미국"),
    ("anuaheart", "ANUA heartleaf", "US", "미국"),
    ("melona", "Melona ice cream", "US", "미국"),
    ("buldakcarbonara", "Buldak Carbonara", "US", "미국"),
    ("shin", "Shin Ramyun", "US", "미국"),
    ("turtlechips", "Turtle Chips", "US", "미국"),
    ("bibigomandu", "bibigo dumplings", "US", "미국"),
    ("tirtircushion", "TIRTIR cushion", "US", "미국"),
    ("tirtir", "TIRTIR", "JP", "일본"),
    ("innisfree", "Innisfree", "JP", "일본"),
    ("vt", "VT Reedle Shot", "JP", "일본"),
    ("dalba", "d'Alba skincare", "JP", "일본"),
    ("jsm", "JUNG SAEM MOOL", "JP", "일본"),
    ("hetbahn", "Hetbahn", "JP", "일본"),
    ("homerunball", "Home Run Ball snack", "JP", "일본"),
    ("banana", "Binggrae banana milk", "VN", "베트남"),
    ("jinramen", "Jin Ramen", "VN", "베트남"),
    ("chocopie", "Orion Choco Pie", "VN", "베트남"),
    ("sulwhasoo", "Sulwhasoo", "CN", "중국"),
    ("jungkwanjang", "CheongKwanJang", "CN", "중국"),
    ("milkis", "Milkis", "RU", "러시아"),
    ("maxim", "Maxim Mocha Gold", "", "몽골·글로벌 대용"),
    ("buldak", "Buldak", "", "유럽·글로벌 대용"),
    ("boj", "Beauty of Joseon", "", "유럽·글로벌 대용"),
    ("skin1004", "SKIN1004", "", "유럽·글로벌 대용"),
    ("reliefsun", "Beauty of Joseon Relief Sun", "", "유럽·글로벌 대용"),
    ("chapagetti", "Chapagetti", "", "유럽·글로벌 대용"),
    ("bibigokimchi", "bibigo kimchi", "", "유럽·글로벌 대용"),
    ("jongga", "Jongga kimchi", "", "유럽·글로벌 대용"),
    ("pepero", "Pepero", "", "동남아·글로벌 대용"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/data/trends.json")
    parser.add_argument("--batches", type=int, default=2)
    parser.add_argument("--global-items", type=int, default=2)
    parser.add_argument("--pause-seconds", type=int, default=45)
    return parser.parse_args()


def build_batches() -> list[list[tuple[str, str, str, str]]]:
    by_geo: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for item in TRACKED:
        by_geo[item[2]].append(item)
    batches = []
    for geo_items in by_geo.values():
        batches.extend(geo_items[i : i + 5] for i in range(0, len(geo_items), 5))
    return batches


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def clean_points(points: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
    cleaned = []
    for point in points:
        if point.get("is_partial"):
            continue
        try:
            cleaned.append((parse_date(str(point["date"])), float(point["value"])))
        except (KeyError, TypeError, ValueError):
            continue
    cleaned.sort(key=lambda row: row[0])
    return cleaned


def weekly_values(points: list[tuple[datetime, float]]) -> list[int]:
    if len(points) < 2:
        return []
    gaps = [(points[i][0] - points[i - 1][0]).days for i in range(1, len(points))]
    if statistics.median(gaps) >= 5:
        values = [value for _, value in points]
    else:
        weeks: dict[tuple[int, int], list[float]] = defaultdict(list)
        for date, value in points:
            iso = date.isocalendar()
            weeks[(iso.year, iso.week)].append(value)
        values = [statistics.mean(values) for values in weeks.values()]
    rounded = [max(0, min(100, round(value))) for value in values[-12:]]
    if not rounded:
        return []
    return [rounded[0]] * (12 - len(rounded)) + rounded


def moving_base(values: list[int]) -> list[int]:
    base = []
    for index in range(len(values)):
        window = values[max(0, index - 3) : index + 1]
        base.append(round(statistics.mean(window)))
    return base


def percent_change(points: list[tuple[datetime, float]]) -> int:
    if len(points) < 2:
        return 0
    gaps = [(points[i][0] - points[i - 1][0]).days for i in range(1, len(points))]
    if statistics.median(gaps) <= 2 and len(points) >= 14:
        recent = statistics.mean(value for _, value in points[-7:])
        prior = statistics.mean(value for _, value in points[-14:-7])
    else:
        recent = statistics.mean(value for _, value in points[-2:])
        prior_slice = points[-4:-2] or points[-2:-1]
        prior = statistics.mean(value for _, value in prior_slice)
    if prior <= 0:
        return 100 if recent > 0 else 0
    return max(-100, min(300, round((recent / prior - 1) * 100)))


def trend_points(values: list[int], delta: int) -> int:
    if len(values) < 4:
        return 0
    recent = statistics.mean(values[-4:])
    prior = statistics.mean(values[-8:-4] or values[:4])
    slope_pct = 0 if prior <= 0 else (recent / prior - 1) * 100
    raw = 17.5 + 0.22 * delta + 0.28 * slope_pct
    return max(0, min(35, round(raw)))


def json_series(points: list[tuple[datetime, float]]) -> list[dict[str, Any]]:
    return [
        {
            "date": date.isoformat().replace("+00:00", "Z"),
            "value": max(0, min(100, round(value))),
        }
        for date, value in points
    ]


def monthly_series(points: list[tuple[datetime, float]]) -> list[dict[str, Any]]:
    months: dict[str, list[float]] = defaultdict(list)
    for date, value in points:
        months[date.strftime("%Y-%m")].append(value)
    return [
        {"date": f"{month}-01T00:00:00Z", "value": round(statistics.mean(values))}
        for month, values in sorted(months.items())[-60:]
    ]


def change_between(values: list[float], span: int, offset: int = 0) -> int | None:
    end = len(values) - offset
    current = values[max(0, end - span) : end]
    prior = values[max(0, end - span * 2) : max(0, end - span)]
    if len(current) < span or len(prior) < span:
        return None
    current_mean = statistics.mean(current)
    prior_mean = statistics.mean(prior)
    if prior_mean <= 0:
        return 100 if current_mean > 0 else 0
    return max(-100, min(300, round((current_mean / prior_mean - 1) * 100)))


def yearly_change(values: list[float]) -> int | None:
    if len(values) < 15:
        return None
    current = statistics.mean(values[-3:])
    prior = statistics.mean(values[-15:-12])
    if prior <= 0:
        return 100 if current > 0 else 0
    return max(-100, min(300, round((current / prior - 1) * 100)))


def fetch_global_item(
    item: tuple[str, str, str, str], pause_seconds: int
) -> dict[str, Any]:
    from trendspyg import (
        download_google_trends_explore,
        download_google_trends_interest_over_time,
    )

    item_id, query, _, _ = item
    common = {
        "geo": "",
        "cache": "disk",
        "archive": True,
        "db_path": "runtime/trendspyg.sqlite3",
        "cookies": "disk",
    }
    year = download_google_trends_explore(query, timeframe="today 12-m", **common)
    if pause_seconds:
        time.sleep(pause_seconds)
    five_year_raw = download_google_trends_interest_over_time(
        query, timeframe="today 5-y", **common
    )

    year_points = clean_points(year.get("interest_over_time", []))
    five_year_points = clean_points(five_year_raw)
    if len(year_points) < 8 or not any(value for _, value in year_points):
        raise ValueError(f"{item_id}: usable global trend points not returned")

    regions = []
    for row in year.get("interest_by_region", []):
        try:
            value = int(row.get("value", 0))
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        regions.append(
            {
                "code": str(row.get("geo_code", ""))[:12],
                "name": str(row.get("geo_name", ""))[:80],
                "value": max(0, min(100, value)),
            }
        )
    regions.sort(key=lambda row: row["value"], reverse=True)
    regions = regions[:25]

    series_12m = json_series(year_points[-60:])
    series_5y = monthly_series(five_year_points)
    weekly_values_full = [float(row["value"]) for row in series_12m]
    monthly_values = [float(row["value"]) for row in series_5y]
    current = round(statistics.mean(weekly_values_full[-4:]))
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "query": query,
        "updated_at": now,
        "series_12m": series_12m,
        "series_5y": series_5y,
        "regions": regions,
        "summary": {
            "current_index": current,
            "change_4w_pct": change_between(weekly_values_full, 4),
            "change_12w_pct": change_between(weekly_values_full, 4, 8),
            "yoy_pct": yearly_change(monthly_values),
            "peak_index_12m": round(max(weekly_values_full)),
            "region_count": len(regions),
            "top_region": regions[0]["name"] if regions else None,
        },
    }


def fetch_batch(
    batch: list[tuple[str, str, str, str]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    from trendspyg import (
        download_google_trends_comparison,
        download_google_trends_interest_over_time,
    )

    queries = [row[1] for row in batch]
    geo = batch[0][2]
    common = {
        "geo": geo,
        "timeframe": "today 3-m",
        "cache": "disk",
        "archive": True,
        "db_path": "runtime/trendspyg.sqlite3",
        "cookies": "disk",
    }
    if len(queries) == 1:
        raw = download_google_trends_interest_over_time(queries[0], **common)
        series_by_query = {queries[0]: raw}
    else:
        envelope = download_google_trends_comparison(queries, **common)
        series_by_query = {
            query: [
                {
                    "date": point.get("date"),
                    "value": point.get("values", {}).get(query, 0),
                    "is_partial": point.get("is_partial", False),
                }
                for point in envelope.get("interest_over_time", [])
            ]
            for query in queries
        }

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    output = {}
    skipped = []
    for item_id, query, item_geo, geo_label in batch:
        points = clean_points(series_by_query.get(query, []))
        trend = weekly_values(points)
        if len(trend) != 12 or not any(trend):
            skipped.append(f"{item_id}: usable trend points not returned")
            continue
        delta = percent_change(points)
        output[item_id] = {
            "query": query,
            "geo": item_geo or "WORLD",
            "geo_label": geo_label,
            "updated_at": now,
            "delta": delta,
            "trend": trend,
            "base": moving_base(trend),
            "trend_points": trend_points(trend, delta),
        }
    if not output:
        raise ValueError("no usable trend points returned for this batch")
    return output, skipped


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    state = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
    state.setdefault("items", {})
    batches = build_batches()
    start = int(state.get("next_batch", 0)) % len(batches)
    count = max(1, min(args.batches, len(batches)))
    chosen = [batches[(start + offset) % len(batches)] for offset in range(count)]
    updated_ids: list[str] = []
    global_updated_ids: list[str] = []
    errors: list[str] = []

    Path("runtime").mkdir(exist_ok=True)
    os.environ.setdefault("TRENDSPYG_COOKIES", str(Path("runtime/google-cookies.json").resolve()))

    for index, batch in enumerate(chosen):
        try:
            updates, skipped = fetch_batch(batch)
            state["items"].update(updates)
            updated_ids.extend(updates)
            errors.extend(f"batch {start + index}: {message}" for message in skipped)
            print(f"updated: {', '.join(updates)}", flush=True)
        except Exception as exc:  # Upstream browser and rate-limit errors are preserved in run metadata.
            message = f"batch {start + index}: {type(exc).__name__}: {exc}"
            errors.append(message)
            print(message, file=sys.stderr, flush=True)
            if "RateLimit" in type(exc).__name__ or "429" in str(exc):
                break
        if index < len(chosen) - 1:
            time.sleep(max(0, args.pause_seconds))

    global_count = max(0, min(args.global_items, len(TRACKED)))
    global_start = int(state.get("next_global_item", 0)) % len(TRACKED)
    global_items = [TRACKED[(global_start + offset) % len(TRACKED)] for offset in range(global_count)]
    if global_items and chosen:
        time.sleep(max(0, args.pause_seconds))
    for index, item in enumerate(global_items):
        item_id, query, item_geo, geo_label = item
        try:
            detail = fetch_global_item(item, max(0, args.pause_seconds))
            row = state["items"].setdefault(item_id, {})
            row.setdefault("query", query)
            row.setdefault("geo", item_geo or "WORLD")
            row.setdefault("geo_label", geo_label)
            row["global"] = detail
            global_updated_ids.append(item_id)
            print(f"updated global: {item_id}", flush=True)
        except Exception as exc:
            message = f"global {item_id}: {type(exc).__name__}: {exc}"
            errors.append(message)
            print(message, file=sys.stderr, flush=True)
            if "RateLimit" in type(exc).__name__ or "429" in str(exc):
                break
        if index < len(global_items) - 1:
            time.sleep(max(0, args.pause_seconds))

    if not updated_ids and not global_updated_ids:
        print("No collection succeeded; keeping the previous public snapshot.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state.update(
        {
            "schema_version": 2,
            "source": "Google Trends Explore",
            "method": "trendspyg browser collector",
            "updated_at": now,
            "next_batch": (start + len(chosen)) % len(batches),
            "next_global_item": (global_start + len(global_items)) % len(TRACKED),
            "last_run": {
                "status": "partial" if errors else "success",
                "updated_ids": updated_ids,
                "global_updated_ids": global_updated_ids,
                "errors": errors,
                "total_batches": len(batches),
            },
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {output_path} ({len(updated_ids)} signals, "
        f"{len(global_updated_ids)} global profiles, {len(errors)} errors)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
