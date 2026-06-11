"""
Google Maps Maps List + 認証版 Webアプリ
-----------------------------------------
機能:
  - ユーザー登録 / ログイン
  - 一般ユーザー: 業種検索 + CSV ダウンロード
  - 管理者: ユーザー一覧, 活動ログ, 解析, データ一括ダウンロード

起動:
  streamlit run app.py
"""

import csv
import hashlib
import io
import json
import os
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ------------------------------------------------------------------
# 定数
# ------------------------------------------------------------------
USER_DB_PATH = "users.json"
ACTIVITY_LOG_PATH = "activity_log.json"
USER_DATA_DIR = "user_data"
COOKIE_NAME = "googlemapslist_session"
COOKIE_KEY = "replace_with_strong_secret_key_change_me"
COOKIE_EXPIRY_DAYS = 30
DEFAULT_ADMIN_PASSWORD = "admin123"

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAIL_URL = "https://places.googleapis.com/v1/places"


# ------------------------------------------------------------------
# ストレージ
# ------------------------------------------------------------------
def _init_files():
    Path(USER_DATA_DIR).mkdir(exist_ok=True)
    if not os.path.exists(USER_DB_PATH):
        _save_users({
            "admin": {
                "name": "管理者",
                "email": "admin@example.com",
                "password": _hash(DEFAULT_ADMIN_PASSWORD),
                "role": "admin",
                "created_at": datetime.now().isoformat(),
            }
        })
    if not os.path.exists(ACTIVITY_LOG_PATH):
        _save_activity_log([])


def _load_users() -> dict:
    with open(USER_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: dict):
    with open(USER_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _load_activity_log() -> list:
    with open(ACTIVITY_LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_activity_log(log: list):
    with open(ACTIVITY_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def _log_activity(username: str, action: str, details: str):
    log = _load_activity_log()
    log.append(
        {
            "user": username,
            "action": action,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }
    )
    _save_activity_log(log)


def _user_data_path(username: str) -> Path:
    return Path(USER_DATA_DIR) / username


_init_files()


# ------------------------------------------------------------------
# 認証
# ------------------------------------------------------------------
def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _authenticate(username: str, password: str) -> bool:
    users = _load_users()
    user = users.get(username)
    return bool(user and user.get("password") == _hash(password))


def _register_user(name: str, email: str, username: str, password: str, role: str = "user") -> bool:
    users = _load_users()
    if username in users:
        return False
    users[username] = {
        "name": name,
        "email": email,
        "password": _hash(password),
        "role": role,
        "created_at": datetime.now().isoformat(),
    }
    _save_users(users)
    return True


# ------------------------------------------------------------------
# Streamlit 状態管理
# ------------------------------------------------------------------
def _init_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "role" not in st.session_state:
        st.session_state.role = None
    if "page" not in st.session_state:
        st.session_state.page = "search"


def _login_screen():
    st.title("🗺 Google Maps 業種リスト収集 - ログイン")
    mode = st.radio("モード", ["ログイン", "新規登録"], horizontal=True)

    if mode == "ログイン":
        with st.form("login_form"):
            username = st.text_input("ユーザー名")
            password = st.text_input("パスワード", type="password")
            submitted = st.form_submit_button("ログイン", use_container_width=True, type="primary")
            if submitted:
                if _authenticate(username, password):
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    role = _load_users()[username].get("role", "user")
                    st.session_state.role = role
                    st.session_state.page = "admin" if role == "admin" else "search"
                    _log_activity(username, "login", "ログイン成功")
                    st.rerun()
                else:
                    st.error("ユーザー名またはパスワードが正しくありません。")
    else:
        with st.form("register_form"):
            name = st.text_input("名前")
            email = st.text_input("メールアドレス")
            username = st.text_input("ユーザー名（ログイン用）")
            password = st.text_input("パスワード", type="password")
            password2 = st.text_input("パスワード（確認）", type="password")
            submitted = st.form_submit_button("登録", use_container_width=True, type="primary")
            if submitted:
                if password != password2:
                    st.error("パスワードが一致しません。")
                elif not username or not password:
                    st.error("ユーザー名とパスワードは必須です。")
                else:
                    ok = _register_user(name, email, username, password)
                    if ok:
                        st.success("登録完了。ログインしてください。")
                        _log_activity(username, "register", "新規ユーザー登録")
                    else:
                        st.error("このユーザー名は既に使用されています。")


def _logout():
    _log_activity(st.session_state.username, "logout", "ログアウト")
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.page = "search"
    st.rerun()


# ------------------------------------------------------------------
# 管理者サイドバー
# ------------------------------------------------------------------
def _admin_sidebar():
    users = _load_users()
    user = users.get(st.session_state.username, {})
    st.sidebar.title("👤 管理者メニュー")
    st.sidebar.write(f"**{user.get('name', st.session_state.username)}**")
    st.sidebar.caption(f"権限: {st.session_state.role}")

    choice = st.sidebar.radio(
        "移動",
        ["🔍 検索", "📊 ダッシュボード", "👥 ユーザー管理", "📋 活動ログ", "💾 データ管理", "📝 ログアウト"],
        label_visibility="collapsed",
    )
    st.sidebar.divider()
    st.sidebar.caption("管理者モード")

    if choice == "📝 ログアウト":
        _logout()
    elif choice == "🔍 検索":
        st.session_state.page = "search"
    elif choice == "📊 ダッシュボード":
        st.session_state.page = "admin_dashboard"
    elif choice == "👥 ユーザー管理":
        st.session_state.page = "admin_users"
    elif choice == "📋 活動ログ":
        st.session_state.page = "admin_logs"
    elif choice == "💾 データ管理":
        st.session_state.page = "admin_data"


def _user_sidebar():
    st.sidebar.title("👤 ユーザー")
    users = _load_users()
    user = users.get(st.session_state.username, {})
    st.sidebar.write(f"**{user.get('name', st.session_state.username)}**")
    st.sidebar.caption(f"権限: {st.session_state.role}")
    if st.sidebar.button("ログアウト", use_container_width=True):
        _logout()


# ------------------------------------------------------------------
# 管理者: ダッシュボード
# ------------------------------------------------------------------
def _admin_dashboard():
    st.title("📊 管理者ダッシュボード")
    log = _load_activity_log()

    if not log:
        st.info("まだ活動データがありません。")
        return

    df = pd.DataFrame(log)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("総ユーザー数", len(_load_users()))
    col2.metric("総検索回数", len(df))
    col3.metric("ログイン回数", len(df[df["action"] == "login"]))
    col4.metric("登録ユーザー数", len(df[df["action"] == "register"]))

    st.subheader("日別検索数")
    daily = df.groupby("date").size().reset_index(name="件数")
    fig = px.bar(daily, x="date", y="件数", title="日別アクティビティ")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("アクション別内訳")
    action_counts = df.groupby("action").size().reset_index(name="件数")
    fig2 = px.pie(action_counts, names="action", values="件数", title="アクション分布")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("ユーザー別検索回数 TOP10")
    top_users = df.groupby("user").size().reset_index(name="件数").sort_values("件数", ascending=False).head(10)
    st.dataframe(top_users, use_container_width=True)


# ------------------------------------------------------------------
# 管理者: ユーザー管理
# ------------------------------------------------------------------
def _admin_users():
    st.title("👥 ユーザー管理")
    users = _load_users()
    rows = []
    for uname, udata in users.items():
        rows.append(
            {
                "username": uname,
                "name": udata.get("name"),
                "email": udata.get("email"),
                "role": udata.get("role"),
                "created_at": udata.get("created_at"),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    with st.expander("⚠ 重要: 削除操作"):
        target = st.selectbox("削除するユーザー", [u for u in users.keys() if u != st.session_state.username])
        if st.button("選択したユーザーを削除", type="secondary"):
            users.pop(target, None)
            _save_users(users)
            _log_activity(st.session_state.username, "delete_user", f"Deleted {target}")
            st.success(f"{target} を削除しました。")
            st.rerun()


# ------------------------------------------------------------------
# 管理者: 活動ログ
# ------------------------------------------------------------------
def _admin_logs():
    st.title("📋 活動ログ")
    log = _load_activity_log()
    if not log:
        st.info("ログがありません。")
        return
    df = pd.DataFrame(log)
    df = df.sort_values("timestamp", ascending=False)
    st.dataframe(df, use_container_width=True, height=600)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("ログを CSV ダウンロード", data=csv, file_name="activity_log.csv", mime="text/csv")


# ------------------------------------------------------------------
# 管理者: データ管理 (全ユーザーのCSV一覧 + ダウンロード)
# ------------------------------------------------------------------
def _admin_data():
    st.title("💾 データ管理")
    base = Path(USER_DATA_DIR)
    if not base.exists():
        st.info("保存データがありません。")
        return

    rows = []
    for user_dir in sorted(base.iterdir()):
        if user_dir.is_dir():
            for f in sorted(user_dir.glob("*.csv")):
                rows.append(
                    {
                        "user": user_dir.name,
                        "file": f.name,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                        "updated": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    }
                )

    if not rows:
        st.info("CSV がありません。")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    selected_user = st.selectbox("ユーザーで絞り込み", ["(すべて)"] + sorted({r["user"] for r in rows}))
    if selected_user != "(すべて)":
        df = df[df["user"] == selected_user]

    for _, row in df.iterrows():
        fpath = base / row["user"] / row["file"]
        data = fpath.read_text(encoding="utf-8-sig")
        st.download_button(
            f"⬇ {row['user']} / {row['file']}",
            data=data,
            file_name=row["file"],
            mime="text/csv",
            key=f"dl_{row['user']}_{row['file']}",
        )


# ------------------------------------------------------------------
# 共通: 検索 + CSV 生成
# ------------------------------------------------------------------
def _build_csv(items: list, api_key: str) -> str:
    fields = ["name", "address", "phone", "website", "place_id", "rating", "user_ratings_total"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()

    prog = st.progress(0.0, text="Places APIから詳細を取得中...")
    total = len(items)
    for i, it in enumerate(items, start=1):
        time.sleep(0.2)
        pid = it.get("id", "")
        name = it.get("displayName", {}).get("text") if isinstance(it.get("displayName"), dict) else it.get("displayName", "")
        detail = _get_place_details(pid, api_key) if pid else {}

        def _get(obj, field, default=""):
            v = obj.get(field, default)
            if isinstance(v, dict):
                return v.get("text", default) or v.get("value", default)
            return v or default

        row = {
            "name": _get(detail, "displayName") or name,
            "address": _get(detail, "formattedAddress") or "",
            "phone": _get(detail, "nationalPhoneNumber") or "",
            "website": (_get(detail, "websiteUri") or "").strip(),
            "place_id": pid or "",
            "rating": _get(detail, "rating", ""),
            "user_ratings_total": _get(detail, "userRatingCount", ""),
        }
        w.writerow(row)
        prog.progress(i / total, text=f"詳細取得中... ({i}/{total})")

    prog.empty()
    return buf.getvalue()


def _search_places(api_key: str, region: str, keyword: str, max_results: int):
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


def _get_place_details(place_id: str, api_key: str) -> dict:
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


def _save_user_csv(username: str, csv_text: str, keyword: str, region: str):
    user_dir = _user_data_path(username)
    user_dir.mkdir(parents=True, exist_ok=True)
    filename = f"gmap_results_{urllib.parse.quote_plus(keyword)}_{urllib.parse.quote_plus(region)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path = user_dir / filename
    path.write_text(csv_text, encoding="utf-8-sig")
    _log_activity(username, "search", f"region={region} keyword={keyword} -> {filename}")


# ------------------------------------------------------------------
# メイン
# ------------------------------------------------------------------
def main():
    _init_session()

    # ログイン前
    if not st.session_state.authenticated:
        _login_screen()
        return

    role = st.session_state.role

    # 管理者サイドバー / ユーザーサイドバー
    if role == "admin":
        _admin_sidebar()
    else:
        _user_sidebar()

    # ページ分岐
    page = st.session_state.page
    users = _load_users()
    current_user = users.get(st.session_state.username, {})

    # API キー入力 (サイドバー固定でも可)
    api_key_input = st.sidebar.text_input("Google Places API キー", type="password", key="api_key_input")
    api_key = api_key_input.strip()

    if role == "admin":
        if page == "search" or page == "admin_dashboard" or page == "admin_users" or page == "admin_logs" or page == "admin_data":
            if page in ("search", "admin_dashboard"):
                _admin_dashboard() if page == "admin_dashboard" else None
                _search_interface(api_key)
            elif page == "admin_users":
                _admin_users()
            elif page == "admin_logs":
                _admin_logs()
            elif page == "admin_data":
                _admin_data()
    else:
        _search_interface(api_key)


def _search_interface(api_key: str):
    if not api_key:
        st.info("サイドバーから **Google Places API キー** を入力してください。")
        return

    st.title("🗺 Google Maps 業種リスト収集")
    col1, col2 = st.columns(2)
    with col1:
        region = st.text_input("地域", value="", placeholder="例: 東京都渋谷区")
    with col2:
        keyword = st.text_input("業種キーワード", value="", placeholder="例: カフェ")

    max_results = st.number_input("最大取得件数", min_value=1, max_value=60, value=20)
    run = st.button("検索して CSV を生成", type="primary", disabled=not bool(api_key and region and keyword))

    if not run:
        return

    try:
        items = _search_places(api_key, region, keyword, int(max_results))
    except Exception as e:
        st.error(f"検索に失敗しました: {e}")
        return

    if not items:
        st.warning("結果が見つかりませんでした。")
        return

    st.success(f"{len(items)} 件の候補を取得しました。")

    try:
        csv_text = _build_csv(items, api_key)
    except Exception as e:
        st.error(f"CSV 生成に失敗しました: {e}")
        return

    # 保存
    _save_user_csv(st.session_state.username, csv_text, keyword, region)

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
    try:
        df = pd.read_csv(io.StringIO(csv_text))
        st.dataframe(df.head(20))
    except Exception:
        st.code(csv_text[:3000] + ("..." if len(csv_text) > 3000 else ""))


if __name__ == "__main__":
    main()
