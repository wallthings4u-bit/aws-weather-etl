from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from charts import render_dual_axis_chart, render_japan_map
from config import CITIES, NOC_CSS, format_weather_with_emoji
from data_loader import fetch_daily_precipitation, fetch_realtime_weather, load_weather_data

st.set_page_config(
    page_title="主要都市の現在の天気 & 過去の気象履歴",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(NOC_CSS, unsafe_allow_html=True)


def main():
    st.title("🌤️ 主要都市の現在の天気 & 過去の気象履歴")

    with st.sidebar:
        st.markdown("### 🎛️ 監視ターゲット設定")
        if st.button("🔄 最新データを再取得", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    try:
        with st.spinner("Athenaから蓄積データを取得中..."):
            df = load_weather_data()
    except Exception as e:
        st.error(f"Athenaへのクエリ実行に失敗しました: {e}")
        return

    if df.empty:
        st.warning("表示できる蓄積データがありません。")
        return

    available_kanji = set(df["city_kanji"].unique().tolist())
    city_options = [c["kanji"] for c in CITIES if c["kanji"] in available_kanji] or sorted(list(available_kanji))

    if "pending_city" in st.session_state:
        st.session_state["selected_city"] = st.session_state.pop("pending_city")

    if "selected_city" not in st.session_state or st.session_state["selected_city"] not in city_options:
        st.session_state["selected_city"] = "東京" if "東京" in city_options else next(iter(city_options))

    selected_city = st.sidebar.selectbox("都市を選択（地図クリックでも切替可）", city_options, key="selected_city")

    latest_fetched_raw = df["fetched_at"].dropna().max()
    with st.sidebar:
        st.markdown("---")
        if pd.notna(latest_fetched_raw):
            latest_dt = pd.to_datetime(latest_fetched_raw)
            latest_jst = latest_dt.tz_localize("UTC").tz_convert("Asia/Tokyo") if latest_dt.tzinfo is None else latest_dt.tz_convert("Asia/Tokyo")
            hours_diff = (datetime.now(ZoneInfo("Asia/Tokyo")) - latest_jst).total_seconds() / 3600
            formatted_time = latest_jst.strftime("%Y-%m-%d %H:%M JST")
            if hours_diff <= 26:
                st.success(f"✅ **日次ETL正常稼働中**\n\n最終取得: `{formatted_time}`\n\n同期都市数: {len(city_options)} 都市")
            else:
                st.warning(f"⚠️ **バッチ更新遅延の可能性**\n\n最終取得: `{formatted_time}`")

    city_df = df[df["city_kanji"] == selected_city].sort_values("date").reset_index(drop=True)
    precip_df = fetch_daily_precipitation(selected_city)
    city_df = pd.merge(city_df, precip_df, on="date", how="left") if not precip_df.empty else city_df.assign(precipitation_sum=0.0)

    realtime, err_msg = fetch_realtime_weather(selected_city)
    now_jst = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")

    # -----------------------------------------------------
    # 1. 上段：監視拠点マップ（クリック連動） ＋ リアルタイム気象（2×2均等カード）
    # -----------------------------------------------------
    col_map, col_rt = st.columns([1.05, 1.95], gap="large")
    with col_map:
        st.markdown('<div class="noc-section-header">🗾 監視拠点マップ（都市クリックで切替）</div>', unsafe_allow_html=True)
        map_event = st.plotly_chart(
            render_japan_map(selected_city),
            use_container_width=True,
            key=f"japan_map_{selected_city}",
            on_select="rerun",
            selection_mode="points",
            config={"displayModeBar": False},
        )
        if map_event and map_event.selection and map_event.selection.points:
            first_point = next(iter(map_event.selection.points), {})
            clicked_city = first_point.get("customdata")
            if clicked_city in city_options and clicked_city != selected_city:
                st.session_state["pending_city"] = clicked_city
                st.rerun()

    with col_rt:
        if realtime:
            obs_time = realtime["time"].split("T")[-1] if "T" in realtime["time"] else now_jst
            st.markdown(
                f'<div class="noc-section-header"><span class="status-dot"></span> リアルタイム気象（{selected_city} / {obs_time} 時点）</div>',
                unsafe_allow_html=True,
            )
            weather_disp = format_weather_with_emoji(realtime["weather_desc"])
            precip_val = float(realtime.get("precipitation") or 0.0)
            humidity_val = realtime.get("humidity")
            humidity_str = f"{int(humidity_val)} %" if pd.notna(humidity_val) else "-"
            is_rain = precip_val > 0 or any(k in weather_disp for k in ["雨", "雷", "☔", "🌧️", "⛈️", "🌦️"])
            weather_cls = "noc-card noc-card-alert" if is_rain else "noc-card"
            precip_cls = "noc-card noc-card-alert" if precip_val > 0 else "noc-card"

            row1_c1, row1_c2 = st.columns(2, gap="medium")
            with row1_c1:
                st.markdown(
                    f'<div class="{weather_cls}" style="min-height:118px;"><div class="noc-label">現在の天気</div>'
                    f'<div class="noc-weather-value">{weather_disp}</div>'
                    f'<div class="noc-sub-value">API即時取得</div></div>',
                    unsafe_allow_html=True,
                )
            with row1_c2:
                st.markdown(
                    f'<div class="noc-card" style="min-height:118px;"><div class="noc-label">現在の気温</div>'
                    f'<div class="noc-metric-value">{realtime["temp"]:.1f} ℃</div>'
                    f'<div class="noc-sub-value">風速: {realtime["wind_speed"]:.1f} km/h</div></div>',
                    unsafe_allow_html=True,
                )

            row2_c1, row2_c2 = st.columns(2, gap="medium")
            with row2_c1:
                st.markdown(
                    f'<div class="noc-card" style="min-height:118px;"><div class="noc-label">湿度</div>'
                    f'<div class="noc-metric-value">{humidity_str}</div>'
                    f'<div class="noc-sub-value">相対湿度</div></div>',
                    unsafe_allow_html=True,
                )
            with row2_c2:
                precip_color = "#ff4d6d" if precip_val > 0 else "#00f0ff"
                precip_note = "☔ 降水観測中" if precip_val > 0 else "降水なし"
                st.markdown(
                    f'<div class="{precip_cls}" style="min-height:118px;"><div class="noc-label">降水量</div>'
                    f'<div class="noc-metric-value" style="color:{precip_color};">{precip_val:.1f} mm</div>'
                    f'<div class="noc-sub-value">{precip_note}</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.warning(f"リアルタイム気象データを取得できませんでした（{err_msg}）")

    # -----------------------------------------------------
    # 2. 中段：日次バッチ最新データ
    # -----------------------------------------------------
    latest = city_df.iloc[-1]
    st.markdown(f'<div class="noc-section-header">🗄️ 日次バッチ最新データ（{selected_city} / {latest["date"].strftime("%Y-%m-%d")}）</div>', unsafe_allow_html=True)

    daily_weather_disp = format_weather_with_emoji(latest["weather_desc"], latest.get("weather_code"))
    sunrise_str = str(latest["sunrise"])[-5:] if pd.notna(latest["sunrise"]) else "-"
    sunset_str = str(latest["sunset"])[-5:] if pd.notna(latest["sunset"]) else "-"

    d_col1, d_col2, d_col3, d_col4 = st.columns([1.3, 1.0, 1.0, 1.1], gap="medium")
    with d_col1:
        st.markdown(f'<div class="noc-card" style="min-height:105px;"><div class="noc-label">日次天気予報</div><div class="noc-weather-value">{daily_weather_disp}</div></div>', unsafe_allow_html=True)
    with d_col2:
        st.markdown(f'<div class="noc-card" style="min-height:105px;"><div class="noc-label">最高気温</div><div class="noc-metric-value" style="color:#ff5e7e;">{latest["temp_max"]:.1f} ℃</div></div>', unsafe_allow_html=True)
    with d_col3:
        st.markdown(f'<div class="noc-card" style="min-height:105px;"><div class="noc-label">最低気温</div><div class="noc-metric-value" style="color:#fbbf24;">{latest["temp_min"]:.1f} ℃</div></div>', unsafe_allow_html=True)
    with d_col4:
        st.markdown(f'<div class="noc-card" style="min-height:105px;"><div class="noc-label">日の出 / 日の入り</div><div class="noc-metric-value" style="font-size:1.45rem;">{sunrise_str} / {sunset_str}</div></div>', unsafe_allow_html=True)

    # -----------------------------------------------------
    # 3. 日次バッチ最新データの下：2軸複合チャート（気温・降水量推移）
    # -----------------------------------------------------
    st.plotly_chart(render_dual_axis_chart(city_df, selected_city), use_container_width=True, config={"displayModeBar": False})

    # -----------------------------------------------------
    # 4. 下段：履歴データ一覧（Athena蓄積）
    # -----------------------------------------------------
    st.markdown('<div class="noc-section-header">📋 履歴データ一覧（Athena蓄積）</div>', unsafe_allow_html=True)
    display_df = city_df.sort_values("date", ascending=False).copy()
    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
    display_df["weather_desc"] = display_df.apply(lambda r: format_weather_with_emoji(r["weather_desc"], r.get("weather_code")), axis=1)

    table_df = display_df[["date", "city_kanji", "weather_desc", "temp_max", "temp_min", "precipitation_sum", "sunrise", "sunset", "fetched_at"]].rename(
        columns={"date": "日付", "city_kanji": "都市", "weather_desc": "天気予報", "temp_max": "最高気温 (℃)", "temp_min": "最低気温 (℃)", "precipitation_sum": "降水量 (mm)", "sunrise": "日の出", "sunset": "日の入り", "fetched_at": "取得日時"}
    )
    st.dataframe(table_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
