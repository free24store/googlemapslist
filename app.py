"""
地域・業種キーワードを指定して Google Maps の候補を CSV で取得する Webアプリです。
やること:
  - Streamlit でブラウザ UI を表示
  - 検索 -> 詳細取得 -> 結果プレビュー -> CSV ダウンロード
起動:
  streamlit run app.py
ブラウザのアドレスバーに自動で Opens されます。
"""

from pathlib import Path
import csv
import io
import os
import sys
import time
import urllib.parse
from datetime import datetime

import requests
import streamlit as st

try:
    import pandas as pd
except ImportError:  # optional
    pd = None

# --------------------------------------------------------------------------- #
# 設定
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Google Maps 業種リスト収集", page_icon="🗺", layout="wide")
st.title("🗺 Google Maps 業種リスト収集")

with st.sidebar:
    st.header("設定")
    api_key = st.text_input("Google Places API キー", type="password")
    region_default = st.text_input("デフォルト地域", value="")
    keyword_default = st.text_input("デフォルト業種キーワード", value="")
    max_default = st.number_input("最大取得件数 (1-60)", min_value=1, max_value=60, value=20)
    st.caption(
        "キーはこの画面内でのみ使用されます。"
        "『Places API』が有効な Google Cloud プロジェクトのキーを入力してください。"
    )

# --------------------------------------------------------------------------- #
# 入力
# --------------------------------------------------------------------------- #
col1, col2 = st.columns(2)
with col1:
    region = st.text_input("地域", value=region_default, placeholder="例: 東京都渋谷区")
with col2:
    keyword = st.text_input("業種キーワード", value=keyword_default, placeholder="例: カフェ")

max_results = st.number_input("最大取得件数", min_value=1, max_value=60, value=int(max_default))
run = st.button("検索して CSV を生成", type="primary", disabled=not bool(api_key and region and keyword))

# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAIL_URL = "https://places.googleapis.com/v1/places"


def search_places(region: str, keyword: str, max_results: int):
    q = f"{keyword} {region}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount",
    }
    body = {
        "textQuery": q,
        "languageCode": "ja",
        "regionCode": "jp",
        "maxResultCount": int(max_results),
    }
    with st.spinner(f"Google Maps を検索中: {q}"):
        res = requests.post(PLACES_SEARCH_URL, headers=headers, json=body, timeout=30)
        res.raise_for_status()
        data = res.json()
    return data.get("places", [])[:max_results]


def get_place_details(place_id: str) -> dict:
    fieldmask = "displayName,formattedAddress,nationalPhoneNumber,websiteUri,rating,userRatingCount"
    url = f"{PLACES_DETAIL_URL}/{urllib.parse.quote(place_id, safe='')}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": fieldmask,
    }
    res = requests.get(url, headers=headers, timeout=30)
    res.raise_for_status()
    data = res.json()
    return data if isinstance(data, dict) else {}


def _get(obj: dict, field: str, default=""):
    v = obj.get(field, default)
    if isinstance(v, dict):
        return v.get("text", default) or v.get("value", default)
    return v or default


# --------------------------------------------------------------------------- #
# CSV 構築
# --------------------------------------------------------------------------- #
def build_csv(items: list) -> str:
    fields = [
        "name",
        "address",
        "phone",
        "website",
        "place_id",
        "rating",
        "user_ratings_total",
    ]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()

    prog = st.progress(0.0, text="詳細情報を取得中...")
    count = len(items)
    for i, it in enumerate(items, start=1):
        time.sleep(REQUEST_DELAY_SEC)
        pid = it.get("id", "")
        name = _get(it, "displayName") or it.get("name", "")
        detail = get_place_details(pid) if pid else {}

        rows.append({
            "name": _get(detail, "displayName") or name,
            "address": _get(detail, "formattedAddress") or "",
            "phone": _get(detail, "nationalPhoneNumber") or "",
            "website": (_get(detail, "websiteUri") or "").strip(),
            "place_id": pid or "",
            "rating": _get(detail, "rating", ""),
            "user_ratings_total": _get(detail, "userRatingCount", ""),
        })
        writer.writerow(rows[-1])
        prog.progress(i / count, text=f"詳細取得中... ({i}/{count})")

    prog.empty()
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# 実行
# --------------------------------------------------------------------------- #
if run:
    try:
        items = search_places(region, keyword, int(max_results))
    except Exception as e:
        st.error(f"検索に失敗しました: {e}")
        st.stop()

    if not items:
        st.warning("結果が見つかりませんでした。条件を緩めてください。")
        st.stop()

    st.success(f"{len(items)} 件の候補を取得しました。")

    try:
        csv_text = build_csv(items)
    except Exception as e:
        st.error(f"CSV 生成に失敗しました: {e}")
        st.stop()

    k = urllib.parse.quote_plus(keyword)
    r = urllib.parse.quote_plus(region)
    filename = f"gmap_results_{k}_{r}_{datetime.now().strftime('%Y%m%d')}.csv"

    st.download_button(
        "⬇ CSV をダウンロード",
        data=csv_text,
        file_name=filename,
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )

    st.subheader("プレビュー")
    if pd is not None:
        df = pd.read_csv(io.StringIO(csv_text))
        st.dataframe(df.head(20))
    else:
        st.code(csv_text[:3000] + ("..." if len(csv_text) > 3000 else ""), language="text")
