"""
ui.py — Streamlit UI components for FB Ads Explorer (with SQLite Teams).

Functions:
  inject_global_css()
  render_sidebar_search()  -> filters, token, fetch_clicked
  render_sidebar_saved_mode() -> team
  render_main_search_page()   -> cards + detail
  render_saved_ads_page()     -> cards + detail (from DB)
"""

from __future__ import annotations

import json
import streamlit as st

import logic  # local module


# =============================================================================
# GLOBAL CSS
# =============================================================================
CUSTOM_CSS = """
<style>
/************** Top Filter Bar **************/
.fb-filter-bar {width:100%;display:flex;flex-wrap:wrap;gap:0.5rem;align-items:center;margin-bottom:1rem;}
.fb-filter-pill {display:inline-flex;align-items:center;gap:0.25rem;padding:0.35rem 0.75rem;border:1px solid var(--secondary-border,#e0e0e0);border-radius:999px;background:var(--secondary-bg,#f7f7f7);font-size:0.85rem;cursor:default;}
.fb-filter-pill strong{font-weight:600;}

/************** Card Grid **************/
.fb-card-wrapper{position:relative;width:100%;}
.fb-card{width:100%;border:1px solid #e0e0e0;border-radius:8px;background:#ffffff;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,0.08);transition:box-shadow 0.1s ease-in-out, transform 0.1s ease-in-out;cursor:pointer;}
.fb-card:hover{box-shadow:0 4px 16px rgba(0,0,0,0.15);transform:translateY(-2px);}
.fb-card-header{padding:0.5rem 0.75rem;display:flex;flex-direction:column;gap:0.25rem;}
.fb-card-brand{font-weight:600;font-size:0.95rem;line-height:1.2;}
.fb-card-sub{font-size:0.75rem;color:#666;}
.fb-card-body{padding:0.5rem 0.75rem;font-size:0.85rem;color:#111;}
.fb-card-media img{width:100%;height:auto;display:block;}
.fb-card-media video{width:100%;display:block;}
.fb-card-badges{position:absolute;top:8px;left:8px;display:flex;gap:4px;}
.fb-card-badge{padding:2px 6px;font-size:0.7rem;border-radius:4px;background:#e8f7ed;color:#0a7c2f;font-weight:600;}
.fb-card-badge-secondary{background:#eef0f3;color:#333;}

/************** Detail Panel **************/
.fb-detail-table{width:100%;border-collapse:collapse;font-size:0.88rem;}
.fb-detail-table td{padding:4px 8px;border-bottom:1px solid #eee;vertical-align:top;}
.fb-detail-table td:first-child{font-weight:600;width:35%;color:#555;}
</style>
"""


def inject_global_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =============================================================================
# SIDEBAR: SEARCH MODE
# =============================================================================
def render_sidebar_search():
    st.sidebar.header("Query Parameters")

    # Country select
    country_labels = [n for n, _ in logic.COMMON_COUNTRIES] + ["Custom…"]
    country_label_sel = st.sidebar.selectbox("Country", options=country_labels, index=0, key="search_country_sel")
    if country_label_sel == "Custom…":
        country_code = st.sidebar.text_input("ISO country code", value="", key="search_country_custom").strip().upper() or "US"
        country_label = country_code
    else:
        country_code = dict(logic.COMMON_COUNTRIES)[country_label_sel]
        country_label = country_label_sel

    # Keyword input
    keyword_input = st.sidebar.text_input("Keyword", value="", key="search_keyword")

    # Ad Category radio
    ad_category_label = st.sidebar.radio(
        "Ad category", options=list(logic.CATEGORY_LABEL_TO_ADTYPE.keys()), index=0, key="search_category"
    )
    ad_type_param = logic.CATEGORY_LABEL_TO_ADTYPE[ad_category_label]

    # Active status radio
    active_status_label = st.sidebar.radio(
        "Active status", options=list(logic.ACTIVE_STATUS_LABEL_TO_PARAM.keys()), index=0, key="search_status"
    )
    active_status_param = logic.ACTIVE_STATUS_LABEL_TO_PARAM[active_status_label]

    # Search mode select
    search_mode_label = st.sidebar.selectbox(
        "Search matching", options=list(logic.SEARCH_MODE_LABEL_TO_PARAM.keys()), index=0, key="search_match"
    )
    search_mode_param = logic.SEARCH_MODE_LABEL_TO_PARAM[search_mode_label]

    # Number of ads
    count = st.sidebar.number_input(
        "Number of ads", min_value=1, max_value=1000, value=100, step=1, key="search_count"
    )

    # Token override
    sidebar_token = st.sidebar.text_input(
        "Apify API token", type="password", key="search_token"
    )

    # Install hint if apify-client missing
    ApifyClient, import_err = logic._import_apify_client()
    if import_err or ApifyClient is None:
        st.sidebar.warning("`apify-client` not installed. Run: `pip install apify-client`.")

    # Final token resolution
    apify_token = logic.resolve_apify_token(sidebar_token)

    # Fetch button
    fetch_clicked = st.sidebar.button("Fetch ads", type="primary", key="search_fetch_btn")

    # Prepare filter dict
    kw_raw = keyword_input.strip()
    kw_display = f'"{kw_raw}"' if search_mode_param == "keyword_exact" and not (kw_raw.startswith('"') and kw_raw.endswith('"')) else kw_raw

    filters = {
        "country_code": country_code,
        "country_label": country_label,
        "keyword_raw": kw_raw,
        "keyword_display": kw_display,
        "ad_category": ad_category_label,
        "ad_type_param": ad_type_param,
        "active_status_label": active_status_label,
        "active_status_param": active_status_param,
        "search_mode_label": search_mode_label,
        "search_mode_param": search_mode_param,
        "count": int(count),
    }

    return filters, apify_token, fetch_clicked


# =============================================================================
# SIDEBAR: SAVED MODE
# =============================================================================
def render_sidebar_saved_mode():
    st.sidebar.header("Saved Ads")
    team_choice = st.sidebar.selectbox(
        "Select team table",
        options=["(choose)"] + logic.TEAM_TABLES,
        index=0,
        key="saved_team_sel",
    )
    return None if team_choice == "(choose)" else team_choice


# =============================================================================
# FILTER BAR SUMMARY
# =============================================================================
def render_filter_bar(*, country_label: str, ad_category_label: str, keyword: str, active_status_label: str):
    st.markdown(
        f"""
        <div class='fb-filter-bar'>
            <div class='fb-filter-pill'><strong>{country_label}</strong></div>
            <div class='fb-filter-pill'><strong>{ad_category_label}</strong></div>
            <div class='fb-filter-pill'>"{keyword}"</div>
            <div class='fb-filter-pill fb-filter-pill-status'><strong>{active_status_label}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# DETAIL TABLE HTML
# =============================================================================
def _make_detail_table_html(rows):
    cells = []
    for label, value in rows:
        val = value if value not in (None, "", [], {}) else "–"
        cells.append(f"<tr><td>{label}</td><td>{val}</td></tr>")
    return f"<table class='fb-detail-table'>{''.join(cells)}</table>"


# =============================================================================
# SAVE CARD UI
# =============================================================================
def _card_save_ui(idx: int, ad_fields: dict, raw_item: dict):
    table = st.selectbox("Save to team", options=logic.TEAM_TABLES, key=f"save_select_{idx}")
    if st.button("Confirm save", key=f"confirm_save_{idx}"):
        logic.db_insert_team(table, ad_fields, raw_item)
        st.success(f"Saved to {table}!")
        st.session_state.pop("save_pending_idx", None)


# =============================================================================
# CARD RENDERER (shared)
# =============================================================================
def render_ad_card(item: dict, idx: int, variant: str, *, team: str | None = None, raw_item: dict | None = None):
    """
    Render one ad card.

    variant = "search": show See Ad Details + Save
    variant = "saved":  show See Ad Details only (select saved detail)
    """
    f = logic.extract_selected_fields(item)

    page_name = f.get("page_name") or item.get("pageName") or "(no page name)"
    ad_text = item.get("adText") or item.get("ad_text") or item.get("text") or ""
    short_text = logic.summarize_text(ad_text, 200)
    ad_archive_id = f.get("ad_archive_id") or item.get("adId") or item.get("id") or f"#{idx}"
    status = logic.detect_status(item)
    running_days = logic.compute_running_days(item)

    # Prefer snapshot original image
    img_from_snapshot = f.get("original_image_url") or f.get("original_picture_url")
    if img_from_snapshot:
        media_type, media_url = "image", img_from_snapshot
    else:
        media_type, media_url = logic.extract_primary_media(item)

    with st.container():
        st.markdown("<div class='fb-card-wrapper'>", unsafe_allow_html=True)
        if media_url:
            if media_type == "image":
                st.markdown(
                    f"<div class='fb-card-media'><img src='{media_url}'/></div>",
                    unsafe_allow_html=True,
                )
            elif media_type == "video":
                st.video(media_url)
        st.markdown(
            f"""
            <div class='fb-card'>
                <div class='fb-card-badges'>
                    <span class='fb-card-badge'>{status}</span>
                    <span class='fb-card-badge fb-card-badge-secondary'>{running_days or '–'}D</span>
                </div>
                <div class='fb-card-header'>
                    <div class='fb-card-brand'>{page_name}</div>
                    <div class='fb-card-sub'>Archive ID: {ad_archive_id}</div>
                </div>
                <div class='fb-card-body'>{short_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if variant == "search":
            c1, c2 = st.columns(2)
            if c1.button("See Ad Details", key=f"detail_{idx}"):
                st.session_state["selected_ad_idx"] = idx
            if c2.button("Save", key=f"save_{idx}"):
                st.session_state["save_pending_idx"] = idx
            if st.session_state.get("save_pending_idx") == idx:
                _card_save_ui(idx, f, raw_item or item)

        elif variant == "saved":
            if st.button("See Ad Details", key=f"saved_detail_{team}_{idx}"):
                st.session_state[f"saved_selected_idx_{team}"] = idx

        st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# DETAIL VIEW — SEARCH RESULTS
# =============================================================================
def render_ad_detail(item: dict):
    f = logic.extract_selected_fields(item)

    page_name = f.get("page_name") or "(no page name)"
    ad_archive_id = f.get("ad_archive_id") or "–"

    img_from_snapshot = f.get("original_image_url") or f.get("original_picture_url")
    if img_from_snapshot:
        media_type, media_url = "image", img_from_snapshot
    else:
        media_type, media_url = logic.extract_primary_media(item)

    st.markdown("---")
    st.markdown(
        f"<h3 style='margin-bottom:0;'>{page_name}</h3>"
        f"<div style='color:#666;font-size:0.9rem;'>Ad Archive ID: {ad_archive_id}</div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 1], gap="large")
    with left:
        if media_url:
            if media_type == "image":
                st.image(media_url, use_column_width=True)
            elif media_type == "video":
                st.video(media_url)
        if f.get("link_url"):
            st.markdown(f"[Ad Destination URL]({f['link_url']})")
        if f.get("page_profile_uri"):
            st.markdown(f"[Page Profile]({f['page_profile_uri']})")

    with right:
        st.markdown("### Details")
        info_rows = [
            ("ad_archive_id", f.get("ad_archive_id")),
            ("categories", f.get("categories")),
            ("collation_count", f.get("collation_count")),
            ("collation_id", f.get("collation_id")),
            ("start_date", f.get("start_date")),
            ("end_date", f.get("end_date")),
            ("entity_type", f.get("entity_type")),
            ("is_active", f.get("is_active")),
            ("page_id", f.get("page_id")),
            ("page_name", f.get("page_name")),
            ("cta_text", f.get("cta_text")),
            ("cta_type", f.get("cta_type")),
            ("page_entity_type", f.get("page_entity_type")),
            ("page_profile_picture_url", f.get("page_profile_picture_url")),
            ("page_profile_uri", f.get("page_profile_uri")),
            ("state_media_run_label", f.get("state_media_run_label")),
            ("total_active_time", f.get("total_active_time")),
            ("original_image_url", f.get("original_image_url")),
        ]
        st.markdown(_make_detail_table_html(info_rows), unsafe_allow_html=True)

    with st.expander("All fields (raw JSON)"):
        st.json(item)
    with st.expander("Debug: Extracted fields"):
        st.json(f)


# =============================================================================
# BUILD ITEM-LIKE STRUCTURE FROM DB ROW
# =============================================================================
def _db_row_to_item(row: dict) -> dict:
    """
    Convert DB row -> item-like dict for extract_selected_fields/media helpers.
    Uses raw_json if stored; otherwise constructs minimal snapshot.
    """
    if isinstance(row.get("raw_json"), dict):
        return row["raw_json"]

    snap = {
        "link_url": row.get("link_url"),
        "cards": {
            "cta_text": row.get("cta_text"),
            "cta_type": row.get("cta_type"),
            "link_url": row.get("link_url"),
        },
        "page_categories": {
            "page_entity_type": row.get("page_entity_type"),
        },
        "images": {
            "original_image_url": row.get("original_image_url"),
        },
        "page_profile_picture_url": row.get("page_profile_picture_url"),
        "page_profile_uri": row.get("page_profile_uri"),
    }

    return {
        "ad_archive_id": row.get("ad_archive_id"),
        "categories": row.get("categories"),
        "collation_count": row.get("collation_count"),
        "collation_id": row.get("collation_id"),
        "start_date": row.get("start_date"),
        "end_date": row.get("end_date"),
        "entity_type": row.get("entity_type"),
        "is_active": bool(row.get("is_active")),
        "page_id": row.get("page_id"),
        "page_name": row.get("page_name"),
        "state_media_run_label": row.get("state_media_run_label"),
        "total_active_time": row.get("total_active_time"),
        "snapshot": snap,
    }


# =============================================================================
# DETAIL VIEW — SAVED ADS
# =============================================================================
def render_saved_ad_detail(db_row: dict):
    item_like = _db_row_to_item(db_row)
    f = logic.extract_selected_fields(item_like)

    page_name = f.get("page_name") or "(no page name)"
    ad_archive_id = f.get("ad_archive_id") or "–"

    img_from_snapshot = f.get("original_image_url") or f.get("original_picture_url")
    if img_from_snapshot:
        media_type, media_url = "image", img_from_snapshot
    else:
        media_type, media_url = logic.extract_primary_media(item_like)

    st.markdown("---")
    st.markdown(
        f"<h3 style='margin-bottom:0;'>{page_name}</h3>"
        f"<div style='color:#666;font-size:0.9rem;'>Ad Archive ID: {ad_archive_id}</div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 1], gap="large")
    with left:
        if media_url:
            if media_type == "image":
                st.image(media_url, use_column_width=True)
            elif media_type == "video":
                st.video(media_url)
        if f.get("link_url"):
            st.markdown(f"[Ad Destination URL]({f['link_url']})")
        if f.get("page_profile_uri"):
            st.markdown(f"[Page Profile]({f['page_profile_uri']})")

    with right:
        st.markdown("### Details")
        info_rows = [
            ("ad_archive_id", f.get("ad_archive_id")),
            ("categories", f.get("categories")),
            ("collation_count", f.get("collation_count")),
            ("collation_id", f.get("collation_id")),
            ("start_date", f.get("start_date")),
            ("end_date", f.get("end_date")),
            ("entity_type", f.get("entity_type")),
            ("is_active", f.get("is_active")),
            ("page_id", f.get("page_id")),
            ("page_name", f.get("page_name")),
            ("cta_text", f.get("cta_text")),
            ("cta_type", f.get("cta_type")),
            ("page_entity_type", f.get("page_entity_type")),
            ("page_profile_picture_url", f.get("page_profile_picture_url")),
            ("page_profile_uri", f.get("page_profile_uri")),
            ("state_media_run_label", f.get("state_media_run_label")),
            ("total_active_time", f.get("total_active_time")),
            ("original_image_url", f.get("original_image_url")),
        ]
        st.markdown(_make_detail_table_html(info_rows), unsafe_allow_html=True)

    raw = db_row.get("raw_json")
    if isinstance(raw, dict):
        with st.expander("All fields (raw JSON from DB)"):
            st.json(raw)
    else:
        with st.expander("DB row"):
            st.json(db_row)

    with st.expander("Debug: Extracted fields"):
        st.json(f)


# =============================================================================
# MAIN SEARCH PAGE COMPOSER
# =============================================================================
def render_main_search_page(ads_items: list[dict], params: dict | None):
    if params:
        render_filter_bar(
            country_label=params.get("country_label", "US"),
            ad_category_label=params.get("ad_category", "All ads"),
            keyword=params.get("keyword_display", params.get("keyword_raw", "")),
            active_status_label=params.get("active_status_label", "Active ads"),
        )
    else:
        st.markdown(
            "<div class='fb-filter-bar'><div class='fb-filter-pill'>Set filters in sidebar</div></div>",
            unsafe_allow_html=True,
        )

    if ads_items:
        st.success(f"Retrieved {len(ads_items)} ads.")

        # Export controls --------------------------------------------------
        exp_cols = st.columns(3)
        with exp_cols[0]:
            st.download_button(
                label="Download JSON",
                data=json.dumps(ads_items, indent=2, ensure_ascii=False),
                file_name="fb_ads_raw.json",
                mime="application/json",
                key="search_download_json",
            )
        with exp_cols[1]:
            df = logic.ads_to_dataframe(ads_items)
            st.download_button(
                label="Download CSV (curated)",
                data=df.to_csv(index=False),
                file_name="fb_ads_curated.csv",
                mime="text/csv",
                key="search_download_csv",
            )
        with exp_cols[2]:
            with st.expander("Preview table (curated)"):
                st.dataframe(df, use_container_width=True, key="search_preview_df")

        # Cards -------------------------------------------------------------
        cols_per_row = 3
        for row_start in range(0, len(ads_items), cols_per_row):
            cols = st.columns(cols_per_row, gap="large")
            for i, col in enumerate(cols):
                idx = row_start + i
                if idx >= len(ads_items):
                    continue
                with col:
                    render_ad_card(
                        ads_items[idx],
                        idx,
                        variant="search",
                        raw_item=ads_items[idx],  # for saving
                    )

        # Detail panel ------------------------------------------------------
        sel_idx = st.session_state.get("selected_ad_idx")
        if sel_idx is not None and 0 <= sel_idx < len(ads_items):
            render_ad_detail(ads_items[sel_idx])
    else:
        st.info("Submit a query from the sidebar to fetch ads.")


# =============================================================================
# SAVED ADS PAGE (load from DB + cards + detail)
# =============================================================================
def render_saved_ads_page(team: str, rows: list[dict]):
    st.header(f"Saved Ads — {team}")
    if not rows:
        st.info("No ads saved yet.")
        return

    items = [_db_row_to_item(r) for r in rows]

    # Card grid
    cols_per_row = 3
    for row_start in range(0, len(items), cols_per_row):
        cols = st.columns(cols_per_row, gap="large")
        for i, col in enumerate(cols):
            idx = row_start + i
            if idx >= len(items):
                continue
            with col:
                render_ad_card(
                    items[idx],
                    idx,
                    variant="saved",
                    team=team,
                )

    # Detail panel
    sel_key = f"saved_selected_idx_{team}"
    sel_idx = st.session_state.get(sel_key)
    if sel_idx is not None and 0 <= sel_idx < len(rows):
        render_saved_ad_detail(rows[sel_idx])
