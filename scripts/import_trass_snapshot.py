#!/usr/bin/env python3
"""Convert an epic-trass custom-group CSV snapshot into dashboard JSON."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


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


def number(value: str) -> float | None:
    value = value.strip()
    return round(float(value), 4) if value else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--output", default="private-data/trade.json")
    args = parser.parse_args()

    with open(args.csv_path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        headers = next(reader)
        rows = {row[0]: row for row in reader if row and row[0] in GROUPS}

    missing = sorted(set(GROUPS) - set(rows))
    if missing:
        raise SystemExit(f"필수 그룹 누락: {', '.join(missing)}")

    items = []
    for group, category in GROUPS.items():
        row = rows[group]
        items.append(
            {
                "group": group,
                "category": category,
                "amount_current_musd": number(row[1]),
                "amount_prior_year_musd": number(row[2]),
                "amount_yoy_pct": number(row[3]),
                "amount_prior_month_end_musd": number(row[4]),
                "amount_previous_month_musd": number(row[5]),
                "unit_price_current_usd_kg": number(row[6]),
                "unit_price_prior_year_usd_kg": number(row[7]),
                "unit_price_yoy_pct": number(row[8]),
                "unit_price_prior_month_end_usd_kg": number(row[9]),
                "unit_price_previous_month_usd_kg": number(row[10]),
            }
        )

    payload = {
        "schema_version": 1,
        "source": "epic Finance TRASS-BF · 관세청 통관자료",
        "data_type": "estimate_custom_groups",
        "latest_trade_date": headers[1].replace(".", "-"),
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "units": {"amount": "million_usd", "unit_price": "usd_per_kg"},
        "items": items,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output} ({len(items)} groups)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
