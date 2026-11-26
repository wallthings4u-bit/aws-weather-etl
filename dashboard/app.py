import os
import awswrangler as wr
import pandas as pd
import plotly.express as px
import streamlit as st

# ページ設定
st.set_page_config(
    page_title="Weather Data Dashboard",
    page_icon="🌤️",
    layout="wide",
)

# AWS / Athena 設定（環境変数があれば優先、なければデフォルト値を使用）
REGION = os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1")
DATABASE = os.getenv("ATHENA_DATABASE", "aws_weather_etl_db")
WORKGROUP = os.getenv("ATHENA_WORKGROUP", "aws-weather-etl-workgroup")


@st.cache_data(ttl=600)
def load_weather_data() -> pd.DataFrame:
    """Athenaから気象データを取得する（10分間キャッシュ）"""
    # Partition Projectionが効くようにパーティションキーを条件に含めるか、全件取得して整形
    # 同一日付・都市で複数回取得されている場合は最新の fetched_at を採用するクエリ
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
        ctas_approach=False,  # ワークグループのSSE_S3出力先設定をそのまま使うためFalse推奨
    )
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def main():
    st.title("🌤️ AWS Serverless Weather ETL Dashboard")
    st.caption("Open-Meteo API → Lambda (Parquet) → S3 → Glue / Athena → Streamlit")

    # サイドバー：更新ボタンとフィルター
    with st.sidebar:
        st.header("設定・フィルター")
        if st.button("🔄 最新データを再取得", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    try:
        with st.spinner("Athenaからデータを取得中..."):
            df = load_weather_data()
    except Exception as e:
        st.error(f"Athenaへのクエリ実行に失敗しました: {e}")
        st.info("AWS認証情報（aws configure 等）と、データベース名・ワークグループ名を確認してください。")
        return

    if df.empty:
        st.warning("表示できるデータがありません。Lambdaが実行されS3にデータが保存されているか確認してください。")
        return

    # 都市選択フィルター
    cities = sorted(df["city"].unique().tolist())
    selected_city = st.sidebar.selectbox("都市を選択", cities, index=0)

    city_df = df[df["city"] == selected_city].sort_values("date").reset_index(drop=True)

    # 1. 最新データのサマリー（KPIカード）
    latest = city_df.iloc[-1]
    st.subheader(f"📍 {selected_city} の最新気象データ（{latest['date'].strftime('%Y-%m-%d')}）")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("天気", latest["weather_desc"])
    with col2:
        st.metric("最高気温", f"{latest['temp_max']:.1f} °C")
    with col3:
        st.metric("最低気温", f"{latest['temp_min']:.1f} °C")
    with col4:
        # 日の出・日の入りはISO形式文字列から時刻部分（HH:MM）を抽出して表示
        sunrise_str = str(latest["sunrise"])[-5:] if pd.notna(latest["sunrise"]) else "-"
        sunset_str = str(latest["sunset"])[-5:] if pd.notna(latest["sunset"]) else "-"
        st.metric("日の出 / 日の入り", f"{sunrise_str} / {sunset_str}")

    st.divider()

    # 2. 気温推移グラフ（Plotly）
    st.subheader(f"📈 {selected_city} の気温推移")
    fig = px.line(
        city_df,
        x="date",
        y=["temp_max", "temp_min"],
        labels={"date": "日付", "value": "気温 (°C)", "variable": "指標"},
        markers=True,
        color_discrete_map={"temp_max": "#EF553B", "temp_min": "#636EFA"},
    )
    # 凡例名を日本語に調整
    fig.for_each_trace(
        lambda t: t.update(name="最高気温 (°C)" if t.name == "temp_max" else "最低気温 (°C)")
    )
    fig.update_layout(hovermode="x unified", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

    # 3. 履歴データテーブル
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
