#!/usr/bin/env python3
"""Build a private TRASS snapshot with monthly history and geography.

The output is intentionally written under private-data/, which is gitignored.
It contains trade observations only; credentials and cookies are never serialized.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EPIC_PATHS = [
    Path.home() / ".claude" / "epicfinance",
    Path.home() / ".Codex" / "epicfinance",
]
for candidate in EPIC_PATHS:
    if (candidate / "epic_client.py").exists():
        sys.path.insert(0, str(candidate))
        break

from epic_client import AuthError, EpicError, build  # noqa: E402

MUSD = 1_000_000.0

GROUPS = {
    "라면": "음식료",
    "건기식": "건강식품",
    "기초화장품": "뷰티",
    "색조화장품": "뷰티",
    "메이크업용 제품(쿠션 등)": "뷰티",
    "마스크팩": "뷰티",
    "화장품 전체": "뷰티",
    "미용기기(전체)": "뷰티기기",
    "미용기기_RF/HIFU": "뷰티기기",
    "가정용 미용기기": "뷰티기기",
    "필러": "에스테틱",
}

PRODUCTS = [
    ("cosmetics", "화장품 전체", "5", "1"),
    ("skincare", "기초화장품", "5", "2"),
    ("color_cosmetics", "색조화장품", "5", "3"),
    ("mask_pack", "마스크팩", "5", "11"),
    ("ramen", "라면", "4", "8"),
    ("snacks", "과자", "4", "9"),
    ("icecream", "아이스크림·빙과", "4", "15"),
    ("home_beauty", "가정용 미용기기", "11", "19"),
    ("aesthetic_device", "레이저 미용기기", "11", "18"),
    ("supplements", "건강보조식품", "11", "20"),
]

CONTINENT = {
    "US": "북미", "CA": "북미", "MX": "북미",
    "BR": "중남미", "AR": "중남미", "CL": "중남미", "CO": "중남미", "PE": "중남미",
    "CN": "중화권", "HK": "중화권", "TW": "중화권",
    "JP": "일본",
    "VN": "동남아", "MY": "동남아", "TH": "동남아", "ID": "동남아", "SG": "동남아", "PH": "동남아",
    "GB": "유럽", "FR": "유럽", "DE": "유럽", "ES": "유럽", "IT": "유럽", "BE": "유럽",
    "NO": "유럽", "GR": "유럽", "NL": "유럽", "PL": "유럽", "RU": "유럽",
    "AE": "중동", "SA": "중동", "IQ": "중동", "IR": "중동", "TR": "중동",
    "IN": "서남아", "PK": "서남아", "BD": "서남아",
    "ZA": "아프리카", "EG": "아프리카",
    "AU": "오세아니아", "NZ": "오세아니아",
}


def pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current / previous - 1) * 100, 2)


def monthly_series(client, industry: str, product: str, country: str | None = None):
    params = {"countryCode": country} if country else None
    rows = client.get(
        f"/launch-data/trade/industries/{industry}/{product}/confirm/export/chart",
        params,
    ) or []
    result = []
    for row in rows:
        period = str(row[0])[:6]
        if len(period) != 6 or row[1] is None:
            continue
        result.append({"period": f"{period[:4]}-{period[4:]}", "amount_musd": round(row[1] / MUSD, 3)})
    return result


def metrics(series):
    by_period = {row["period"]: row["amount_musd"] for row in series}
    latest_period = series[-1]["period"]
    year, month = map(int, latest_period.split("-"))
    previous_year = f"{year - 1:04d}-{month:02d}"

    quarters = defaultdict(list)
    years = defaultdict(list)
    months = defaultdict(list)
    for row in series:
        y, m = map(int, row["period"].split("-"))
        quarters[(y, (m - 1) // 3 + 1)].append(row["amount_musd"])
        years[y].append(row["amount_musd"])
        months[m].append(row["amount_musd"])

    complete_quarters = sorted((key, sum(values)) for key, values in quarters.items() if len(values) == 3)
    qoq = pct(complete_quarters[-1][1], complete_quarters[-2][1]) if len(complete_quarters) >= 2 else None
    latest_quarter = f"{complete_quarters[-1][0][0]} Q{complete_quarters[-1][0][1]}" if complete_quarters else "-"
    values = [row["amount_musd"] for row in series]
    ttm = round(sum(values[-12:]), 3) if len(values) >= 12 else None
    ttm_previous = sum(values[-24:-12]) if len(values) >= 24 else None
    global_average = sum(values) / len(values) if values else 0
    seasonal = (sum(months[month]) / len(months[month]) / global_average) if global_average and months[month] else None

    annual = []
    for y in sorted(years):
        vals = years[y]
        if len(vals) < 12 and y != year:
            continue
        annual.append({"year": y, "amount_musd": round(sum(vals), 3), "months": len(vals), "ytd": y == year and len(vals) < 12})

    return {
        "latest_period": latest_period,
        "latest_musd": values[-1],
        "latest_yoy_pct": pct(values[-1], by_period.get(previous_year)),
        "latest_complete_quarter": latest_quarter,
        "qoq_pct": qoq,
        "ttm_musd": ttm,
        "ttm_yoy_pct": pct(ttm, ttm_previous),
        "seasonal_index": round(seasonal, 3) if seasonal is not None else None,
        "annual": annual[-6:],
    }


def custom_snapshot(client):
    data = client.get("/launch-data/trade/custom/groups")
    rows = {row["groupName"]: row["values"] for row in data.get("values") or []}
    items = []
    for group, category in GROUPS.items():
        values = rows.get(group)
        if not values or len(values) < 10:
            continue
        items.append({
            "group": group,
            "category": category,
            "amount_current_musd": round(values[0] / MUSD, 3),
            "amount_prior_year_musd": round(values[1] / MUSD, 3),
            "amount_yoy_pct": round(values[2] * 100, 2),
            "unit_price_current_usd_kg": round(values[5], 4),
            "unit_price_yoy_pct": round(values[7] * 100, 2),
        })
    latest = str(data.get("latestTradeDate") or "")
    if len(latest) == 8:
        latest = f"{latest[:4]}-{latest[4:6]}-{latest[6:]}"
    return latest, items


def geography(client, industry, product, latest_period, total_latest, country_limit):
    countries = client.get(
        f"/launch-data/trade/industries/{industry}/{product}/confirm/countries"
    ) or []
    latest_year, latest_month = map(int, latest_period.split("-"))
    prior_period = f"{latest_year - 1:04d}-{latest_month:02d}"
    output = []
    for country in countries[:country_limit]:
        code = country["countryCode"]
        series = monthly_series(client, industry, product, code)
        values = {row["period"]: row["amount_musd"] for row in series}
        current = values.get(latest_period)
        if current is None:
            continue
        previous = values.get(prior_period)
        output.append({
            "code": code,
            "name": country.get("countryNameKor") or country.get("countryNameEng") or code,
            "continent": CONTINENT.get(code, "기타"),
            "latest_musd": current,
            "prior_year_musd": previous,
            "yoy_pct": pct(current, previous),
        })

    grouped = defaultdict(lambda: {"latest": 0.0, "prior": 0.0, "countries": 0})
    for row in output:
        bucket = grouped[row["continent"]]
        bucket["latest"] += row["latest_musd"]
        bucket["prior"] += row["prior_year_musd"] or 0
        bucket["countries"] += 1
    continents = []
    tracked_total = sum(row["latest_musd"] for row in output)
    for name, values in grouped.items():
        continents.append({
            "name": name,
            "latest_musd": round(values["latest"], 3),
            "yoy_pct": pct(values["latest"], values["prior"]),
            "share_pct": round(values["latest"] / tracked_total * 100, 2) if tracked_total else None,
            "country_count": values["countries"],
        })
    continents.sort(key=lambda row: row["latest_musd"], reverse=True)
    output.sort(key=lambda row: row["latest_musd"], reverse=True)
    return {
        "coverage_pct": round(tracked_total / total_latest * 100, 2) if total_latest else None,
        "country_limit": country_limit,
        "continents": continents,
        "countries": output,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="private-data/trade.json")
    parser.add_argument("--months", type=int, default=60)
    parser.add_argument("--countries", type=int, default=12)
    args = parser.parse_args()
    client = build()
    latest_trade_date, snapshot = custom_snapshot(client)
    history = []
    for product_id, name, industry, product in PRODUCTS:
        series = monthly_series(client, industry, product)[-max(24, args.months):]
        if not series:
            print(f"건너뜀: {name} 시계열 없음", file=sys.stderr)
            continue
        calculated = metrics(series)
        geo = geography(
            client, industry, product, calculated["latest_period"],
            calculated["latest_musd"], args.countries,
        )
        history.append({
            "id": product_id,
            "name": name,
            "industry_code": industry,
            "product_code": product,
            "series": series,
            "metrics": calculated,
            "geography": geo,
        })
        print(f"수집: {name} · {len(series)}개월 · {len(geo['countries'])}개국")

    payload = {
        "schema_version": 2,
        "source": "epic Finance TRASS-BF · 관세청 통관자료",
        "latest_trade_date": latest_trade_date,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "items": snapshot,
        "history": history,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"완료: {output} · 스냅샷 {len(snapshot)}개 · 시계열 {len(history)}개")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AuthError, EpicError) as error:
        print(f"TRASS 수집 실패: {error}", file=sys.stderr)
        raise SystemExit(2)
