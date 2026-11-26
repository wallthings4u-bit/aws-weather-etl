import io
import json
import logging
import os
from datetime import datetime, timezone, timedelta
import boto3
import pandas as pd
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
JST = timezone(timedelta(hours=9))

CITIES = [
    {"name": "Sapporo", "lat": 43.0621, "lon": 141.3544},
    {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    {"name": "Osaka", "lat": 34.6937, "lon": 135.5023},
    {"name": "Matsuyama", "lat": 33.8392, "lon": 132.7656},
    {"name": "Fukuoka", "lat": 33.5902, "lon": 130.4017},
    {"name": "Naha", "lat": 26.2124, "lon": 127.6809},
]

WMO_WEATHER_MAP = {
    0: "快晴",
    1: "晴れ",
    2: "一部曇り",
    3: "曇り",
    45: "霧",
    48: "着氷性の霧",
    51: "弱い霧雨",
    53: "霧雨",
    55: "強い霧雨",
    61: "弱い雨",
    63: "雨",
    65: "強い雨",
    71: "弱い雪",
    73: "雪",
    75: "強い雪",
    80: "にわか雨",
    81: "強いにわか雨",
    82: "激しいにわか雨",
    95: "雷雨",
}


def fetch_weather_data() -> list[dict]:
    lats = ",".join(str(c["lat"]) for c in CITIES)
    lons = ",".join(str(c["lon"]) for c in CITIES)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lats,
        "longitude": lons,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
        "timezone": "Asia/Tokyo",
        "forecast_days": 1,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def transform_to_parquet(raw_data: list[dict], now_jst: datetime) -> tuple[str, bytes]:
    """APIレスポンスをPandas DataFrame経由でParquetバイナリ（Snappy圧縮）に変換する"""
    records = []
    target_date = ""

    for city_info, city_weather in zip(CITIES, raw_data):
        daily = city_weather["daily"]
        target_date = daily["time"][0]
        code = int(daily["weather_code"][0])

        records.append({
            "date": target_date,
            "city": city_info["name"],
            "weather_code": code,
            "weather_desc": WMO_WEATHER_MAP.get(code, "その他"),
            "temp_max": float(daily["temperature_2m_max"][0]),
            "temp_min": float(daily["temperature_2m_min"][0]),
            "sunrise": daily["sunrise"][0],
            "sunset": daily["sunset"][0],
            "fetched_at": now_jst.isoformat(),
        })

    df = pd.DataFrame(records)

    # メモリ上のバッファにParquet形式で書き出し（Snappy圧縮）
    parquet_buffer = io.BytesIO()
    df.to_parquet(parquet_buffer, engine="pyarrow", compression="snappy", index=False)

    return target_date, parquet_buffer.getvalue()


def lambda_handler(event, context):
    now_jst = datetime.now(JST)
    logger.info("Starting weather data ingestion at %s", now_jst.isoformat())

    # 1. 外部APIからデータ取得
    raw_data = fetch_weather_data()

    # 2. Parquet形式へ変換
    target_date, parquet_bytes = transform_to_parquet(raw_data, now_jst)
    year, month, day = target_date.split("-")

    # 3. パーティション構成のS3キー生成 (.parquet)
    s3_key = f"raw/weather_daily/year={year}/month={month}/day={day}/weather_{year}{month}{day}.parquet"

    # 4. S3へアップロード
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=parquet_bytes,
        ContentType="application/vnd.apache.parquet",
    )

    logger.info("Successfully uploaded Parquet data to s3://%s/%s", BUCKET_NAME, s3_key)
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Success", "s3_key": s3_key}),
    }
