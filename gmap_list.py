"""
Google Maps 業種リスト収集ツール (Places API New / v1)
-------------------------------
旧 API (textsearch/json) deprecated のため v1 に移行。

必要環境:
  - Python 3.9+
  - requests (pip install requests)
  - Google Places API (New) キー

使い方:
  1. API キーを設定
     - 環境変数: export GOOGLE_PLACES_API_KEY=***
     - または同フォルダの config.py: API_KEY="***"
  2. python gmap_list.py --region "東京都渋谷区" --keyword "カフェ"
  3. 出力: gmap_results_{keyword}_{region}_{YYYYMMDD}.csv

出力カラム:
  name, address, phone, website, place_id, rating, user_ratings_total
"""

import argparse
import csv
import os
import sys
import time
import urllib.parse
from datetime import datetime

try:
    import requests
except ImportError:
    sys.exit("ERROR: requests が必要です。pip install requests でインストールしてください。")

# 設定: 環境変数 or config.py
def _load_api_key() -> str:
    key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if key:
        return key
    try:
        import config as _cfg
        key = getattr(_cfg, "API_KEY", "").strip()
        if key:
            return key
    except Exception:
        pass
    return ""


API_KEY = _load_api_key()
if not API_KEY and os.path.exists("config.py"):
    import config
    API_KEY = getattr(config, "API_KEY", "")

# Places API (New) v1
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAIL_URL = "https://places.googleapis.com/v1/places"
REQUEST_DELAY_SEC = 0.2


def search_places(region: str, keyword: str, max_results: int = 20) -> list:
    query = f"{keyword} {region}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount",
    }
    body = {
        "textQuery": query,
        "languageCode": "ja",
        "regionCode": "jp",
        "maxResultCount": int(max_results),
    }
    print(f"[INFO] searching: '{query}' ...")
    resp = requests.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("places", [])[:max_results]


def get_place_details(place_id: str) -> dict:
    # v1 では fieldmask で欲しいフィールドを指定
    fieldmask = "displayName,formattedAddress,nationalPhoneNumber,websiteUri,rating,userRatingCount"
    url = f"{PLACES_DETAIL_URL}/{urllib.parse.quote(place_id, safe='')}"
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": fieldmask,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def build_csv_path(keyword: str, region: str) -> str:
    k = urllib.parse.quote_plus(keyword)
    r = urllib.parse.quote_plus(region)
    return f"gmap_results_{k}_{r}_{datetime.now().strftime('%Y%m%d')}.csv"


def save_csv(rows: list, path: str):
    fields = ["name", "address", "phone", "website", "place_id", "rating", "user_ratings_total"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"[DONE] CSV saved: {path}  ({len(rows)} records)")


def main():
    ap = argparse.ArgumentParser(description="Google Maps 業種リスト収集 (Places API New)")
    ap.add_argument("--region", required=True, help="地域 (例: '東京都渋谷区')")
    ap.add_argument("--keyword", required=True, help="業種キーワード (例: 'カフェ')")
    ap.add_argument("--max-results", type=int, default=20, help="最大取得件数 (default 20, max 60)")
    args = ap.parse_args()

    if not API_KEY:
        sys.exit(
            "ERROR: API key not set.\n"
            "  export GOOGLE_PLACES_API_KEY=***\n"
            "  or run with: python gmap_list.py --config config_your_key.py"
        )

    max_r = min(args.max_results, 60)
    try:
        items = search_places(args.region, args.keyword, max_r)
    except Exception as e:
        print(f"[ERROR] search failed: {e}")
        sys.exit(1)

    if not items:
        print("[INFO] no results found.")
        sys.exit(0)

    print(f"[INFO] {len(items)} hits -> fetching details ...")
    rows = []
    for i, it in enumerate(items, 1):
        pid = it.get("id", "")
        name = it.get("displayName", {}).get("text") if isinstance(it.get("displayName"), dict) else it.get("displayName", "")
        if not name:
            name = it.get("name", "")
        print(f"  [{i}/{len(items)}] {name}")
        try:
            time.sleep(REQUEST_DELAY_SEC)
            detail = get_place_details(pid) if pid else {}
        except Exception as e:
            print(f"       detail failed: {e}")
            detail = {}

        def _get(field, default=""):
            v = detail.get(field, default)
            if isinstance(v, dict):
                return v.get("text", default) or v.get("value", default)
            return v or default

        rows.append({
            "name": _get("displayName") or name,
            "address": _get("formattedAddress") or "",
            "phone": _get("nationalPhoneNumber") or "",
            "website": (_get("websiteUri") or "").strip(),
            "place_id": pid or "",
            "rating": _get("rating", ""),
            "user_ratings_total": _get("userRatingCount", ""),
        })

    save_csv(rows, build_csv_path(args.keyword, args.region))


if __name__ == "__main__":
    main()
