import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import CITIES


def render_japan_map(selected_city_kanji: str) -> go.Figure:
    """ダーク基調の日本地図パネル（クリック選択対応・選択都市を赤丸ハイライト）"""
    fig = go.Figure()
    other_lats, other_lons, other_names = [], [], []
    sel_lat, sel_lon, sel_name = None, None, None

    for c in CITIES:
        if c["kanji"] == selected_city_kanji:
            sel_lat, sel_lon, sel_name = c["lat"], c["lon"], c["kanji"]
        else:
            other_lats.append(c["lat"])
            other_lons.append(c["lon"])
            other_names.append(c["kanji"])

    fig.add_trace(
        go.Scattergeo(
            lon=other_lons, lat=other_lats, text=other_names, customdata=other_names,
            textposition="bottom center", mode="markers+text",
            marker=dict(size=10, color="#00f0ff", opacity=0.9, line=dict(width=1, color="#0b0f17")),
            textfont=dict(color="#94a3b8", size=11),
            hovertemplate="<b>%{text}</b>（クリックで切替）<extra></extra>",
        )
    )

    if sel_lat is not None:
        fig.add_trace(
            go.Scattergeo(
                lon=[sel_lon], lat=[sel_lat], customdata=[sel_name], mode="markers",
                marker=dict(size=26, color="rgba(255, 42, 85, 0.25)", line=dict(width=1.5, color="#ff2a55")),
                hoverinfo="skip", showlegend=False,
            )
        )
        fig.add_trace(
            go.Scattergeo(
                lon=[sel_lon], lat=[sel_lat], text=[f"<b>{sel_name}</b>"], customdata=[sel_name],
                textposition="top center", mode="markers+text",
                marker=dict(size=15, color="#ff2a55", line=dict(width=2, color="#ffffff")),
                textfont=dict(color="#ff4d6d", size=14),
                hovertemplate=f"<b>🔴 {sel_name}（選択中）</b><extra></extra>",
            )
        )

    fig.update_geos(
        scope="asia", resolution=50, showcoastlines=True, coastlinecolor="#334155",
        showland=True, landcolor="#161e2e", showocean=True, oceancolor="#0b0f17",
        showcountries=True, countrycolor="#1e293b",
        lataxis_range=[24.0, 46.0], lonaxis_range=[125.0, 147.0], bgcolor="#111827",
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0), height=300,
        paper_bgcolor="#111827", plot_bgcolor="#111827", showlegend=False,
        clickmode="event+select",
    )
    return fig


def render_dual_axis_chart(city_df: pd.DataFrame, city_kanji: str) -> go.Figure:
    """2軸複合チャート（左軸：最高/最低気温折れ線、右軸：降水量棒グラフ）"""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if "precipitation_sum" in city_df.columns:
        fig.add_trace(
            go.Bar(
                x=city_df["date"], y=city_df["precipitation_sum"].fillna(0.0), name="降水量 (mm)",
                marker_color="rgba(56, 189, 248, 0.42)", marker_line_color="#38bdf8", marker_line_width=1,
                hovertemplate="%{y:.1f} mm<extra>降水量</extra>",
            ),
            secondary_y=True,
        )

    fig.add_trace(
        go.Scatter(
            x=city_df["date"], y=city_df["temp_max"], name="最高気温 (℃)", mode="lines+markers",
            line=dict(color="#ff5e7e", width=2.4), marker=dict(size=6, color="#ff5e7e"),
            hovertemplate="%{y:.1f} ℃<extra>最高気温</extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=city_df["date"], y=city_df["temp_min"], name="最低気温 (℃)", mode="lines+markers",
            line=dict(color="#fbbf24", width=2.4), marker=dict(size=6, color="#fbbf24"),
            hovertemplate="%{y:.1f} ℃<extra>最低気温</extra>",
        ),
        secondary_y=False,
    )

    fig.update_layout(
        title=dict(text=f"📈 {city_kanji} の日次気温・降水量推移", font=dict(color="#f1f5f9", size=15), x=0.01),
        paper_bgcolor="#111827", plot_bgcolor="#0f172a", font=dict(color="#cbd5e1"),
        height=370, margin=dict(l=16, r=16, t=48, b=16), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=True, gridcolor="#1e293b", zeroline=False),
    )

    fig.update_yaxes(
        title_text="気温 (℃)", title_font=dict(color="#fbbf24"), tickfont=dict(color="#fbbf24"),
        showgrid=True, gridcolor="#1e293b", zeroline=False, secondary_y=False,
    )

    max_precip = (
        max(city_df["precipitation_sum"].fillna(0.0).max() * 1.3, 10.0)
        if "precipitation_sum" in city_df.columns and not city_df.empty else 10.0
    )
    fig.update_yaxes(
        title_text="降水量 (mm)", title_font=dict(color="#38bdf8"), tickfont=dict(color="#38bdf8"),
        showgrid=False, range=[0, max_precip], secondary_y=True,
    )
    return fig
