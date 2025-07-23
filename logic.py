"""
logic.py — Data + DB utilities for FB Ads Explorer (SQLite Teams).
"""

from __future__ import annotations

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import quote_plus
from typing import Any

import streamlit as st
import pandas as pd


# =============================================================================
# CONSTANTS / MAPPINGS
# =============================================================================
CATEGORY_LABEL_TO_ADTYPE = {
    "All ads": "all",
    "Issues, elections or politics": "issues_elections_politics",
    "Properties": "housing",  # closest FB param
    "Employment": "employment",
    "Financial products and services": "credit",  # closest FB param
}

ACTIVE_STATUS_LABEL_TO_PARAM = {
    "Active ads": "active",
    "Inactive ads": "inactive",
    "All ads": "all",
}

SEARCH_MODE_LABEL_TO_PARAM = {
    "Broad (any words)": "keyword_unordered",
    "Exact phrase": "keyword_exact",
}

COMMON_COUNTRIES: list[tuple[str, str]] = [
    ("United States", "US"),
    ("India", "IN"),
    ("United Kingdom", "GB"),
    ("Canada", "CA"),
    ("Australia", "AU"),
    ("Germany", "DE"),
    ("France", "FR"),
    ("Brazil", "BR"),
    ("Singapore", "SG"),
]

TEAM_TABLES = ["team1", "team2", "team3"]

# SQLite path (same folder as this file)
DB_PATH = Path(__file__).with_name("ads.db")


# =============================================================================
# APIFY IMPORT (lazy)
# =============================================================================
@lru_cache(maxsize=1)
def _import_apify_client():
    try:
        from apify_client import ApifyClient  # type: ignore
        return ApifyClient, None
    except Exception as e:  # noqa: BLE001
        return None, e


# =============================================================================
# TOKEN HANDLING
# =============================================================================
def safe_get_streamlit_secret(key: str) -> str | None:
    try:
        return st.secrets[key]  # type: ignore[index]
    except Exception:  # noqa: BLE001
        return None


def resolve_apify_token(sidebar_value: str | None = None) -> str:
    if sidebar_value and sidebar_value.strip():
        return sidebar_value.strip()
    tok = safe_get_streamlit_secret("APIFY_TOKEN")
    if tok:
        return tok
    env_tok = os.getenv("APIFY_TOKEN")
    if env_tok:
        return env_tok
    return ""


# =============================================================================
# URL BUILDER
# =============================================================================
def build_fb_ads_library_url(*, country: str, keyword: str, ad_type: str, active_status: str, search_mode: str) -> str:
    country = country.strip().upper()
    q = quote_plus(keyword.strip())
    url = (
        "https://www.facebook.com/ads/library/?"
        f"active_status={active_status}&"
        f"ad_type={ad_type}&"
        f"country={country}&"
        "is_targeted_country=false&"
        "media_type=all&"
        f"q={q}&"
        f"search_type={search_mode}"
    )
    return url


# =============================================================================
# APIFY SCRAPE (cached)
# =============================================================================
@st.cache_data(show_spinner=False)
def run_apify_scrape(token: str, url: str, count: int, active_status: str) -> list[dict]:
    ApifyClient, import_err = _import_apify_client()
    if import_err or ApifyClient is None:
        raise RuntimeError("apify-client not installed. Run: `pip install apify-client`.")
    if not token:
        raise ValueError("Missing Apify API token.")

    client = ApifyClient(token)
    run_input = {
        "urls": [{"url": url}],
        "count": int(count),
        "scrapePageAds.activeStatus": active_status,
        "period": "",
    }
    run = client.actor("curious_coder/facebook-ads-library-scraper").call(run_input=run_input)
    ds_id = run.get("defaultDatasetId")
    if not ds_id:
        return []
    items = list(client.dataset(ds_id).iterate_items())
    return items


# =============================================================================
# DATE HELPERS
# =============================================================================
def parse_date_maybe(s: Any):
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(str(s), fmt)
        except Exception:  # noqa: BLE001
            continue
    try:  # epoch?
        if str(s).isdigit():
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    return None


def compute_running_days(item: dict) -> int | None:
    start = item.get("startDate") or item.get("start_date")
    start_dt = parse_date_maybe(start)
    if not start_dt:
        return None
    now = datetime.now(timezone.utc)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    delta = now - start_dt
    return max(delta.days, 0)


def detect_status(item: dict) -> str:
    for k in ("activeStatus", "status", "adStatus", "active_status"):
        v = item.get(k)
        if v is not None:
            return str(v).capitalize()
    if item.get("is_active") is False:
        return "Inactive"
    end = item.get("endDate") or item.get("end_date")
    end_dt = parse_date_maybe(end)
    if end_dt and end_dt < datetime.now(timezone.utc):
        return "Inactive"
    return "Active"


# =============================================================================
# SNAPSHOT / MEDIA HELPERS
# =============================================================================
def _get_snapshot_dict(item: dict) -> dict:
    snap = item.get("snapshot")
    if isinstance(snap, str):
        try:
            snap = json.loads(snap)
        except Exception:  # noqa: BLE001
            snap = {}
    if not isinstance(snap, dict):
        snap = {}
    return snap


def get_original_image_url(item: dict) -> str | None:
    snap = _get_snapshot_dict(item)
    imgs = snap.get("images")
    if isinstance(imgs, dict):
        imgs = [imgs]
    elif not isinstance(imgs, (list, tuple)):
        imgs = []
    for im in imgs:
        if not isinstance(im, dict):
            continue
        for k in ("original_image_url", "original_picture_url", "original_picture", "url", "src"):
            v = im.get(k)
            if v:
                return v
    return None


def extract_primary_media(item: dict):
    oi = get_original_image_url(item)
    if oi:
        return "image", oi
    img_keys = ["imageUrl", "image_url", "thumbnailUrl", "thumbnail_url", "image"]
    vid_keys = ["videoUrl", "video_url", "video"]
    for k in img_keys:
        if item.get(k):
            return "image", item[k]
    for k in vid_keys:
        if item.get(k):
            return "video", item[k]
    creatives = item.get("creatives") or item.get("media") or []
    if isinstance(creatives, dict):
        creatives = [creatives]
    if isinstance(creatives, (list, tuple)):
        for c in creatives:
            if not isinstance(c, dict):
                continue
            for k in img_keys:
                if c.get(k):
                    return "image", c[k]
            for k in vid_keys:
                if c.get(k):
                    return "video", c[k]
    media_urls = item.get("mediaUrls") or item.get("media_urls")
    if isinstance(media_urls, (list, tuple)) and media_urls:
        return "image", media_urls[0]
    return None, None


# =============================================================================
# TEXT UTIL
# =============================================================================
def summarize_text(txt: str, length: int = 160) -> str:
    if not txt:
        return ""
    txt = str(txt).strip().replace("\n", " ")
    return (txt[: length - 1] + "…") if len(txt) > length else txt


# =============================================================================
# DB SCHEMA
# =============================================================================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS {table_name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_archive_id TEXT,
    categories TEXT,
    collation_count TEXT,
    collation_id TEXT,
    start_date TEXT,
    end_date TEXT,
    entity_type TEXT,
    is_active INTEGER,
    page_id TEXT,
    page_name TEXT,
    cta_text TEXT,
    cta_type TEXT,
    link_url TEXT,
    page_entity_type TEXT,
    page_profile_picture_url TEXT,
    page_profile_uri TEXT,
    state_media_run_label TEXT,
    total_active_time INTEGER,
    original_image_url TEXT,
    raw_json TEXT,
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        for t in TEAM_TABLES:
            cur.execute(SCHEMA_SQL.format(table_name=t))
        conn.commit()
    finally:
        conn.close()


def db_insert_team(table: str, ad_fields: dict, raw_item: dict | None = None) -> None:
    if table not in TEAM_TABLES:
        raise ValueError(f"Invalid team table: {table}")
    cols = [
        "ad_archive_id", "categories", "collation_count", "collation_id",
        "start_date", "end_date", "entity_type", "is_active",
        "page_id", "page_name", "cta_text", "cta_type",
        "link_url", "page_entity_type", "page_profile_picture_url",
        "page_profile_uri", "state_media_run_label", "total_active_time",
        "original_image_url", "raw_json",
    ]
    vals = [
        ad_fields.get("ad_archive_id"),
        ad_fields.get("categories"),
        ad_fields.get("collation_count"),
        ad_fields.get("collation_id"),
        ad_fields.get("start_date"),
        ad_fields.get("end_date"),
        ad_fields.get("entity_type"),
        int(bool(ad_fields.get("is_active"))) if ad_fields.get("is_active") is not None else None,
        ad_fields.get("page_id"),
        ad_fields.get("page_name"),
        ad_fields.get("cta_text"),
        ad_fields.get("cta_type"),
        ad_fields.get("link_url"),
        ad_fields.get("page_entity_type"),
        ad_fields.get("page_profile_picture_url"),
        ad_fields.get("page_profile_uri"),
        ad_fields.get("state_media_run_label"),
        ad_fields.get("total_active_time"),
        ad_fields.get("original_image_url"),
        json.dumps(raw_item, ensure_ascii=False) if raw_item is not None else None,
    ]
    ph = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph})"
    conn = _connect()
    try:
        conn.execute(sql, vals)
        conn.commit()
    finally:
        conn.close()


def db_fetch_team(table: str) -> list[dict]:
    if table not in TEAM_TABLES:
        raise ValueError(f"Invalid team table: {table}")
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table} ORDER BY saved_at DESC")
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
    finally:
        conn.close()
    results: list[dict] = []
    for r in rows:
        d = dict(zip(cols, r))
        raw = d.get("raw_json")
        if raw:
            try:
                d["raw_json"] = json.loads(raw)
            except Exception:  # noqa: BLE001
                pass
        results.append(d)
    return results


# =============================================================================
# EXPORT DF (curated)
# =============================================================================
def ads_to_dataframe(items: list[dict]) -> pd.DataFrame:
    rows = [extract_selected_fields(it) for it in items]
    return pd.DataFrame(rows)


# =============================================================================
# CURATED FIELD EXTRACTION
# =============================================================================
def extract_selected_fields(item: dict) -> dict:
    """
    Extract curated fields safely (handles lists / strings / missing / snapshot JSON).
    """
    snap = _get_snapshot_dict(item)

    # cards
    card0 = None
    cards = snap.get("cards")
    if isinstance(cards, list) and cards:
        if isinstance(cards[0], dict):
            card0 = cards[0]
    elif isinstance(cards, dict):
        card0 = cards

    # page_categories
    pgcat0 = None
    page_categories = snap.get("page_categories")
    if isinstance(page_categories, list) and page_categories:
        if isinstance(page_categories[0], dict):
            pgcat0 = page_categories[0]
    elif isinstance(page_categories, dict):
        pgcat0 = page_categories

    # link_url
    link_url = snap.get("link_url")
    if not link_url and isinstance(card0, dict):
        link_url = card0.get("link_url")

    # coerce date (epoch OK)
    def _coerce_epoch_or_date(val):
        if val in (None, "", 0, "0"):
            return None
        try:
            if isinstance(val, (int, float)) or str(val).isdigit():
                dt = datetime.fromtimestamp(int(val), tz=timezone.utc)
                return dt.date().isoformat()
        except Exception:  # noqa: BLE001
            pass
        dt = parse_date_maybe(val)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.date().isoformat()
        return None

    start_date = _coerce_epoch_or_date(item.get("start_date") or item.get("startDate"))
    end_date = _coerce_epoch_or_date(item.get("end_date") or item.get("endDate"))

    # categories display
    categories = item.get("categories")
    if isinstance(categories, (list, tuple)):
        categories_disp = ", ".join(str(c) for c in categories)
    else:
        categories_disp = categories

    return {
        "ad_archive_id": item.get("ad_archive_id") or item.get("adId"),
        "categories": categories_disp,
        "collation_count": item.get("collation_count"),
        "collation_id": item.get("collation_id"),
        "start_date": start_date,
        "end_date": end_date,
        "entity_type": item.get("entity_type"),
        "is_active": item.get("is_active"),
        "page_id": item.get("page_id") or item.get("pageId"),
        "page_name": item.get("page_name") or item.get("pageName"),
        "cta_text": (card0.get("cta_text") if isinstance(card0, dict) else None) or snap.get("cta_text"),
        "cta_type": (card0.get("cta_type") if isinstance(card0, dict) else None) or snap.get("cta_type"),
        "link_url": link_url,
        "page_entity_type": (pgcat0.get("page_entity_type") if isinstance(pgcat0, dict) else None) or item.get("page_entity_type"),
        "page_profile_picture_url": item.get("page_profile_picture_url") or snap.get("page_profile_picture_url"),
        "page_profile_uri": item.get("page_profile_uri") or snap.get("page_profile_uri"),
        "state_media_run_label": item.get("state_media_run_label"),
        "total_active_time": item.get("total_active_time"),
        "original_image_url": get_original_image_url(item),
        "original_picture_url": get_original_image_url(item),  # backward compat
    }
