import os
import socket
import awswrangler as wr
import pandas as pd
import requests
import urllib3.util.connection as urllib3_cn
import streamlit as st

from config import WEATHER_CODE_MAP, get_city_info, normalize_city_to_kanji

DATABASE = os.getenv("ATHENA_DATABASE", "aws_weather_etl_db")
WORKGROUP = os.getenv("ATHENA_WORKGROUP", "aws-weather-etl-workgroup")


def _allowed_gai_family():
    return socket.AF_INET


urllib3_cn.allowed_gai_family = _allowed_gai_family


def _first_item(val):
    if isinstance(val, list) and len(val) > 0:
        return val.pop(0)
    return val


@st.cache_data(ttl=300)
def fetch_realtime_weather(city: str) -> tuple[dict | None, str | None]:
    """Open-Meteo -> 気象庁アメダス -> wttr.in の順でリアルタイム気象を取得"""
    info = get_city_info(city)
    if not info:
        return None, f"都市 '{city}' の座標マスタが見つかりません"

    headers = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
    errors = []

    # 1. Open-Meteo API
    om_url = "https://" + "://open-meteo.com" + "/v1/forecast"
    try:
        res = requests.get(
            om_url,
            params={
                "latitude": info["lat"],
                "longitude": info["lon"],
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "timezone": "Asia/Tokyo",
            },
            headers=headers,
            timeout=6,
        )
        if res.status_code == 200 and res.text.strip():
            data = res.json().get("current", {})
            if data and "temperature_2m" in data:
                code = data.get("weather_code")
                return {
                    "time": data.get("time", ""),
                    "temp": float(data["temperature_2m"]),
                    "humidity": data.get("relative_humidity_2m"),
                    "precipitation": float(data.get("precipitation") or 0.0),
                    "wind_speed": float(data.get("wind_speed_10m") or 0.0),
                    "weather_desc": WEATHER_CODE_MAP.get(code, f"コード:{code}"),
                }, None
        errors.append(f"Open-Meteo空応答(status={res.status_code})")
    except Exception as e:
        errors.append(f"Open-Meteo({type(e).__name__})")

    # 2. 気象庁 アメダス最新観測値（URL分割結合でリンク改変を完全防止）
    jma_host = "https://" + "www.jma.go.jp"
    try:
        amedas_id = info["amedas"]
        t_res = requests.get(jma_host + "/bosai/amedas/data/latest_time.txt", headers=headers, timeout=6)
        t_res.raise_for_status()
        latest_t = t_res.text.strip()
        dt_str = latest_t[:19].replace("-", "").replace("T", "").replace(":", "")
        obs_url = jma_host + f"/bosai/amedas/data/map/{dt_str[:12]}00.json"
        obs_res = requests.get(obs_url, headers=headers, timeout=8)
        obs_res.raise_for_status()
        obs_data = obs_res.json().get(amedas_id, {})

        temp_val = _first_item(obs_data.get("temp"))
        hum_val = _first_item(obs_data.get("humidity"))
        precip_val = _first_item(obs_data.get("precipitation1h")) or 0.0
        wind_raw = _first_item(obs_data.get("wind"))
        wind_val = (float(wind_raw) * 3.6) if wind_raw is not None else 0.0

        if temp_val is not None:
            desc = "雨 ☔" if float(precip_val) > 0 else "晴れ / 曇り 🌤️"
            return {
                "time": latest_t[:16],
                "temp": float(temp_val),
                "humidity": hum_val,
                "precipitation": float(precip_val),
                "wind_speed": round(wind_val, 1),
                "weather_desc": desc,
            }, None
        errors.append(f"JMAデータ空(ID:{amedas_id})")
    except Exception as e:
        errors.append(f"JMA({e})")

    # 3. wttr.in JSON API（最終バックアップ）
    wttr_host = "https://" + "wttr.in"
    try:
        en_city = list(info["keywords"]).pop()
        w_res = requests.get(wttr_host + f"/{en_city}?format=j1", headers=headers, timeout=8)
        if w_res.status_code == 200 and w_res.text.strip():
            curr = _first_item(w_res.json().get("current_condition", [])) or {}
            precip_mm = float(curr.get("precipMM", 0.0))
            desc_obj = _first_item(curr.get("weatherDesc", [])) or {}
            desc_en = desc_obj.get("value", "")
            desc_ja = (
                "雨 ☔" if precip_mm > 0 or "rain" in desc_en.lower()
                else ("曇り ☁️" if "cloud" in desc_en.lower() or "overcast" in desc_en.lower() else "晴れ ☀️")
            )
            return {
                "time": curr.get("localObsDateTime", ""),
                "temp": float(curr["temp_C"]),
                "humidity": int(curr["humidity"]),
                "precipitation": precip_mm,
                "wind_speed": float(curr["windspeedKmph"]),
                "weather_desc": desc_ja,
            }, None
    except Exception as e:
        errors.append(f"wttr({type(e).__name__})")

    return None, " / ".join(errors)


@st.cache_data(ttl=600)
def fetch_daily_precipitation(city: str, past_days: int = 92) -> pd.DataFrame:
    """2軸グラフの右軸（降水量棒グラフ）用に日次降水量を取得する"""
    info = get_city_info(city)
    if not info:
        return pd.DataFrame(columns=["date", "precipitation_sum"])

    headers = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
    om_url = "https://" + "://open-meteo.com" + "/v1/forecast"
    try:
        res = requests.get(
            om_url,
            params={
                "latitude": info["lat"],
                "longitude": info["lon"],
                "daily": "precipitation_sum",
                "past_days": past_days,
                "forecast_days": 1,
                "timezone": "Asia/Tokyo",
            },
            headers=headers,
            timeout=8,
        )
        if res.status_code == 200 and res.text.strip():
            daily = res.json().get("daily", {})
            if daily and "time" in daily:
                return pd.DataFrame({
                    "date": pd.to_datetime(daily["time"]),
                    "precipitation_sum": daily.get("precipitation_sum", [0.0] * len(daily["time"])),
                })
    except Exception:
        pass

    return pd.DataFrame(columns=["date", "precipitation_sum"])


@st.cache_data(ttl=600)
def load_weather_data() -> pd.DataFrame:
    """Athenaから蓄積済みの日次気象データを取得する（10分間キャッシュ）"""
    query = """
    WITH ranked_data AS (
        SELECT
            date, city, weather_code, weather_desc,
            temp_max, temp_min, sunrise, sunset, fetched_at,
            ROW_NUMBER() OVER (PARTITION BY date, city ORDER BY fetched_at DESC) AS rn
        FROM weather_daily
        WHERE year >= '2025'
    )
    SELECT date, city, weather_code, weather_desc, temp_max, temp_min, sunrise, sunset, fetched_at
    FROM ranked_data
    WHERE rn = 1
    ORDER BY date ASC, city ASC
    """
    df = wr.athena.read_sql_query(sql=query, database=DATABASE, workgroup=WORKGROUP, ctas_approach=False)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["city_kanji"] = df["city"].apply(normalize_city_to_kanji)
    return df
