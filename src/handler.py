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

    api_host = ".".join(["api", "open-meteo", "com"])
    url = f"https://{api_host}/v1/forecast"
    params = {
        "latitude": lats,
        "longitude": lons,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,sunrise,sunset",
        "hourly": "relative_humidity_2m",
        "timezone": "Asia/Tokyo",
        "forecast_days": 1,
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def validate_weather_data(df: pd.DataFrame) -> None:
    """S3格納前の動的データ品質チェック（都市・項目の追加に自動追従）"""
    # 1. レコード件数チェック（CITIESマスタの件数と動的に一致するか）
    if len(df) != len(CITIES):
        raise ValueError(
            f"Data Quality Error: 取得件数({len(df)})が対象都市数({len(CITIES)})と不一致です"
        )

    # 2. 都市名の重複・欠落チェック
    expected_cities = {c["name"] for c in CITIES}
    actual_cities = set(df["city"].tolist())
    if actual_cities != expected_cities:
        raise ValueError(
            f"Data Quality Error: 都市リストが不一致です (差分: {expected_cities ^ actual_cities})"
        )

    # 3. 全カラム共通の欠損（NULL / NaN）チェック（新規追加項目も自動で検証対象）
    if df.isnull().any().any():
        null_cols = df.columns[df.isnull().any()].tolist()
        raise ValueError(f"Data Quality Error: 欠損値(NULL)が検出されました: {null_cols}")

    # 4. 気象データのドメイン値・整合性チェック（対象カラムが存在する場合のみ検証）
    if "temp_max" in df.columns and "temp_min" in df.columns:
        if not df["temp_max"].between(-50.0, 50.0).all() or not df["temp_min"].between(-50.0, 50.0).all():
            raise ValueError("Data Quality Error: 気温が許容範囲(-50℃〜50℃)外です")
        if (df["temp_max"] < df["temp_min"]).any():
            raise ValueError("Data Quality Error: 最高気温が最低気温を下回っています")

    if "precipitation_sum" in df.columns:
        if (df["precipitation_sum"] < 0.0).any():
            raise ValueError("Data Quality Error: 降水量が負の値になっています")

    if "humidity_mean" in df.columns:
        if not df["humidity_mean"].between(0.0, 100.0).all():
            raise ValueError("Data Quality Error: 平均湿度が許容範囲(0%〜100%)外です")

    logger.info("Data quality validation passed successfully (%d records).", len(df))


def transform_to_parquet(raw_data: list[dict], now_jst: datetime) -> tuple[str, bytes]:
    """APIレスポンスをPandas DataFrame経由でParquetバイナリ（Snappy圧縮）に変換する"""
    records = []
    target_date = ""

    for city_info, city_weather in zip(CITIES, raw_data):
        daily = city_weather["daily"]
        hourly = city_weather.get("hourly", {})

        target_date = daily["time"][0]
        code = int(daily["weather_code"][0])

        # 降水量（mm）
        precip_list = daily.get("precipitation_sum", [0.0])
        precip_val = float(precip_list[0]) if precip_list and precip_list[0] is not None else 0.0

        # 24時間の相対湿度から日平均湿度（%）を算出
        hum_list = [h for h in hourly.get("relative_humidity_2m", []) if h is not None]
        humidity_mean = round(sum(hum_list) / len(hum_list), 1) if hum_list else 0.0

        records.append({
            "date": target_date,
            "city": city_info["name"],
            "weather_code": code,
            "weather_desc": WMO_WEATHER_MAP.get(code, "その他"),
            "temp_max": float(daily["temperature_2m_max"][0]),
            "temp_min": float(daily["temperature_2m_min"][0]),
            "precipitation_sum": precip_val,
            "humidity_mean": humidity_mean,
            "sunrise": daily["sunrise"][0],
            "sunset": daily["sunset"][0],
            "fetched_at": now_jst.isoformat(),
        })

    df = pd.DataFrame(records)

    # S3格納前のデータ品質チェックを実行
    validate_weather_data(df)

    # メモリ上のバッファにParquet形式で書き出し（Snappy圧縮）
    parquet_buffer = io.BytesIO()
    df.to_parquet(parquet_buffer, engine="pyarrow", compression="snappy", index=False)

    return target_date, parquet_buffer.getvalue()


def lambda_handler(event, context):
    now_jst = datetime.now(JST)
    logger.info("Starting weather data ingestion at %s", now_jst.isoformat())

    # 1. 外部APIからデータ取得
    raw_data = fetch_weather_data()

    # 2. データ品質検証 ＆ Parquet形式へ変換
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
