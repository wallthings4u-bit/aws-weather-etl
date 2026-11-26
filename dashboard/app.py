import os
from datetime import datetime
from zoneinfo import ZoneInfo

import awswrangler as wr
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ページ設定
st.set_page_config(
    page_title="Weather Data Dashboard",
    page_icon="🌤️",
    layout="wide",
)

# AWS / Athena 設定
REGION = os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1")
DATABASE = os.getenv("ATHENA_DATABASE", "aws_weather_etl_db")
WORKGROUP = os.getenv("ATHENA_WORKGROUP", "aws-weather-etl-workgroup")

# 5都市の緯度・経度マスタ（日本語・英語どちらのDB表記でも対応）
CITY_COORDS = [
    (["札幌", "sapporo"], {"lat": 43.0618, "lon": 141.3545}),
    (["東京", "tokyo"], {"lat": 35.6762, "lon": 139.6503}),
    (["大阪", "osaka"], {"lat": 34.6937, "lon": 135.5023}),
    (["松山", "matsuyama"], {"lat": 33.8392, "lon": 132.7657}),
    (["福岡", "fukuoka"], {"lat": 33.5902, "lon": 130.4017}),
]

def get_city_coords(city_name: str) -> dict | None:
    """都市名の表記揺れ（日本語・英語・大文字小文字・括弧付きなど）を吸収して緯度経度を返す"""
    lower_name = str(city_name).lower()
    for keywords, coords in CITY_COORDS:
        if any(k in lower_name for k in keywords):
            return coords
    return None

# WMO天気コードの簡易マッピング
WEATHER_CODE_MAP = {
    0: "快晴 ☀️",
    1: "晴れ 🌤️",
    2: "一部曇り ⛅",
    3: "曇り ☁️",
    45: "霧 🌫️",
    48: "着氷性の霧 🌫️",
    51: "弱い霧雨 🌦️",
    53: "霧雨 🌦️",
    55: "強い霧雨 🌧️",
    61: "弱い雨 ☔",
    63: "雨 ☔",
    65: "強い雨 ⛈️",
    71: "弱い雪 ❄️",
    73: "雪 ❄️",
    75: "大雪 ❄️",
    80: "にわか雨 🌦️",
    81: "強いにわか雨 🌧️",
    82: "激しいにわか雨 ⛈️",
    95: "雷雨 ⚡",
}


@st.cache_data(ttl=300)
def fetch_realtime_weather(city: str) -> tuple[dict | None, str | None]:
    """Open-Meteo APIから現在のリアルタイム気象データを取得（5分間キャッシュ）"""
    coords = get_city_coords(city)
    if not coords:
        return None, f"都市 '{city}' の座標マスタが見つかりません"

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "current_weather": "true",
        "timezone": "Asia/Tokyo",
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        try:
            payload = res.json()
        except Exception:
            preview = repr(res.text[:100])
            return None, f"JSON変換失敗 (HTTP {res.status_code}, 内容: {preview})"

        data = payload.get("current_weather", {})
        code = data.get("weathercode")
        return {
            "time": data.get("time", ""),
            "temp": data.get("temperature"),
            "humidity": None,
            "wind_speed": data.get("windspeed"),
            "weather_desc": WEATHER_CODE_MAP.get(code, f"コード:{code}"),
        }, None
    except Exception as e:
        return None, f"API通信エラー: {e}"


@st.cache_data(ttl=600)
def load_weather_data() -> pd.DataFrame:
    """Athenaから蓄積済みの日次気象データを取得する（10分間キャッシュ）"""
    query = """
    WITH ranked_data AS (
        SELECT
            date,
            city,
            weather_code,
            weather_desc,
            temp_max,
            temp_min,
            sunrise,
            sunset,
            fetched_at,
            ROW_NUMBER() OVER (
                PARTITION BY date, city
                ORDER BY fetched_at DESC
            ) AS rn
        FROM weather_daily
        WHERE year >= '2025'
    )
    SELECT
        date,
        city,
        weather_code,
        weather_desc,
        temp_max,
        temp_min,
        sunrise,
        sunset,
        fetched_at
    FROM ranked_data
    WHERE rn = 1
    ORDER BY date ASC, city ASC
    """
    df = wr.athena.read_sql_query(
        sql=query,
        database=DATABASE,
        workgroup=WORKGROUP,
        ctas_approach=False,
    )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def main():
    st.title("🌤️ 天気データ リアルタイム＆履歴ダッシュボード")
    st.caption("リアルタイム気象API（即時取得） ＋ AWS S3 / Athena データレイク（日次蓄積分析）")

    with st.sidebar:
        st.header("設定・フィルター")
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

    cities = sorted(df["city"].unique().tolist())
    selected_city = st.sidebar.selectbox("都市を選択", cities, index=0)

    # セクション1：リアルタイム気象データ（API即時取得）
    realtime, err_msg = fetch_realtime_weather(selected_city)
    now_jst = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")

    if realtime:
        obs_time = realtime["time"].split("T")[-1] if "T" in realtime["time"] else now_jst
        st.subheader(f"⏱ {selected_city} のリアルタイム気象（{obs_time} 時点 / API即時取得）")

        r_col1, r_col2, r_col3, r_col4 = st.columns(4)
        with r_col1:
            st.metric("現在の天気", realtime["weather_desc"])
        with r_col2:
            st.metric("現在の気温", f"{realtime['temp']:.1f} °C")
        with r_col3:
            st.metric("風速", f"{realtime['wind_speed']:.1f} km/h")
    else:
        st.warning(f"リアルタイム気象データを取得できませんでした（{err_msg}）")
    st.divider()

    # セクション2：蓄積データの最新日サマリー（Athena）
    city_df = df[df["city"] == selected_city].sort_values("date").reset_index(drop=True)
    latest = city_df.iloc[-1]
    st.subheader(f"🗄️ {selected_city} の日次バッチ最新データ（{latest['date'].strftime('%Y-%m-%d')} / Athena蓄積）")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("日次天気予報", latest["weather_desc"])
    with col2:
        st.metric("最高気温", f"{latest['temp_max']:.1f} °C")
    with col3:
        st.metric("最低気温", f"{latest['temp_min']:.1f} °C")
    with col4:
        sunrise_str = str(latest["sunrise"])[-5:] if pd.notna(latest["sunrise"]) else "-"
        sunset_str = str(latest["sunset"])[-5:] if pd.notna(latest["sunset"]) else "-"
        st.metric("日の出 / 日の入り", f"{sunrise_str} / {sunset_str}")

    # セクション3：気温推移グラフ & 履歴テーブル
    st.subheader(f"📈 {selected_city} の日次気温推移（Athena蓄積データ）")
    fig = px.line(
        city_df,
        x="date",
        y=["temp_max", "temp_min"],
        labels={"date": "日付", "value": "気温 (°C)", "variable": "指標"},
        markers=True,
        color_discrete_map={"temp_max": "#EF553B", "temp_min": "#636EFA"},
    )
    fig.for_each_trace(
        lambda t: t.update(name="最高気温 (°C)" if t.name == "temp_max" else "最低気温 (°C)")
    )
    fig.update_layout(hovermode="x unified", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 履歴データ一覧")
    display_df = city_df.sort_values("date", ascending=False).copy()
    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        display_df[["date", "city", "weather_desc", "temp_max", "temp_min", "sunrise", "sunset", "fetched_at"]],
        use_container_width=True,
        hide_index=True,
    )


if __name__ == "__main__":
    main()
