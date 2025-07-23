#!/usr/bin/env python3
"""
app.py — FB Ads Explorer (Streamlit) w/ SQLite saved teams.

Modes:
  • Search Ads  – scrape via Apify, view, save.
  • Saved Ads   – browse ads saved in team1/team2/team3.

This file coordinates page config, mode switching, data fetch, and delegating
UI rendering to ui.py. Database helpers live in logic.py.
"""

from __future__ import annotations

import streamlit as st

import ui            # local
import logic         # local


# -----------------------------------------------------------------------------
# Init
# -----------------------------------------------------------------------------
st.set_page_config(page_title="FB Ads Explorer", layout="wide")
ui.inject_global_css()
logic.init_db()  # ensure SQLite tables exist


# -----------------------------------------------------------------------------
# Mode selector (top of sidebar)
# -----------------------------------------------------------------------------
mode = st.sidebar.radio(
    "Mode",
    ["Search Ads", "Saved Ads"],
    index=0,
    key="app_mode_radio",
)
# Sidebar heading (left)

# Main heading (right)
st.markdown(
    """
    <style>
    .custom-title {
        text-align: center;
        font-size: 2.5rem;
        font-weight: 700;
        color: #2d3a4a;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        background: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
    }
    .custom-subtitle {
        text-align: center;
        font-size: 1.3rem;
        color: #4e6fae;
        margin-bottom: 2rem;
        background: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
    }
    </style>
    <div class="custom-title">Facebook Ad Analytics</div>
    <div class="custom-subtitle">by PixelPay Media</div>
    """,
    unsafe_allow_html=True,
)

# Clear cross-mode state if switching
_last_mode = st.session_state.get("_last_mode")
if _last_mode is not None and _last_mode != mode:
    # Search-mode state keys
    st.session_state.pop("selected_ad_idx", None)
    st.session_state.pop("save_pending_idx", None)
    # Saved-mode state keys (for each team)
    for t in logic.TEAM_TABLES:
        st.session_state.pop(f"saved_selected_idx_{t}", None)
st.session_state["_last_mode"] = mode


# -----------------------------------------------------------------------------
# SEARCH MODE
# -----------------------------------------------------------------------------
if mode == "Search Ads":
    filters, apify_token, fetch_clicked = ui.render_sidebar_search()

    if fetch_clicked:
        if not apify_token:
            st.error("Please provide an Apify API token in the sidebar.")
            st.stop()

        url = logic.build_fb_ads_library_url(
            country=filters["country_code"],
            keyword=filters["keyword_raw"],
            ad_type=filters["ad_type_param"],
            active_status=filters["active_status_param"],
            search_mode=filters["search_mode_param"],
        )

        st.session_state["last_query_url"] = url
        st.session_state["last_query_params"] = filters

        with st.spinner("Running Apify scrape…"):
            try:
                items = logic.run_apify_scrape(
                    apify_token,
                    url,
                    int(filters["count"]),
                    filters["active_status_param"],
                )
            except Exception as e:  # noqa: BLE001
                st.error(f"Apify scrape failed: {e}")
                st.stop()

        st.session_state["ads_items"] = items
        st.session_state.pop("selected_ad_idx", None)
        st.session_state.pop("save_pending_idx", None)

    params = st.session_state.get("last_query_params")
    ads_items = st.session_state.get("ads_items", [])
    ui.render_main_search_page(ads_items, params)

# -----------------------------------------------------------------------------
# SAVED MODE
# -----------------------------------------------------------------------------
else:
    team_choice = ui.render_sidebar_saved_mode()
    if team_choice:
        rows = logic.db_fetch_team(team_choice)
        ui.render_saved_ads_page(team_choice, rows)
    else:
        st.info("Select a team from the sidebar to view saved ads.")


# -----------------------------------------------------------------------------
# Global Debug
# -----------------------------------------------------------------------------
with st.expander("Debug info"):
    st.write("Mode:", mode)
    st.write("Last query params:", st.session_state.get("last_query_params"))
    st.write("Last query URL:", st.session_state.get("last_query_url"))
