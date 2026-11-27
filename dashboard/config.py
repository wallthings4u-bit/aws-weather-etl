import pandas as pd

# 都市マスター定義（漢字表記・検索キーワード・緯度経度・気象庁アメダスID）
CITIES = [
    {"kanji": "札幌", "keywords": ["札幌", "sapporo"],   "lat": 43.0618, "lon": 141.3545, "amedas": "14163"},
    {"kanji": "東京", "keywords": ["東京", "tokyo"],     "lat": 35.6762, "lon": 139.6503, "amedas": "44132"},
    {"kanji": "大阪", "keywords": ["大阪", "osaka"],     "lat": 34.6937, "lon": 135.5023, "amedas": "62078"},
    {"kanji": "松山", "keywords": ["松山", "matsuyama"], "lat": 33.8392, "lon": 132.7657, "amedas": "73166"},
    {"kanji": "福岡", "keywords": ["福岡", "fukuoka"],   "lat": 33.5902, "lon": 130.4017, "amedas": "82182"},
    {"kanji": "那覇", "keywords": ["那覇", "naha"],      "lat": 26.2124, "lon": 127.6809, "amedas": "91197"},
]

WEATHER_CODE_MAP = {
    0: "快晴 ☀️", 1: "晴れ 🌤️", 2: "一部曇り ⛅", 3: "曇り ☁️",
    45: "霧 🌫️", 48: "着氷性の霧 🌫️",
    51: "弱い霧雨 🌦️", 53: "霧雨 🌦️", 55: "強い霧雨 🌧️",
    61: "弱い雨 ☔", 63: "雨 ☔", 65: "強い雨 ⛈️",
    71: "弱い雪 ❄️", 73: "雪 ❄️", 75: "大雪 ❄️",
    80: "にわか雨 🌦️", 81: "強いにわか雨 🌧️", 82: "激しいにわか雨 ⛈️",
    95: "雷雨 ⚡", 96: "ひょうを伴う雷雨 ⛈️", 99: "激しい雷雨 ⛈️",
}

NOC_CSS = """
<style>
.stApp { background-color: #0b0f17; color: #e2e8f0; font-family: 'Segoe UI', 'Meiryo', sans-serif; }
[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #1f2937; }
.noc-card {
    background-color: #111827; border: 1px solid #1f2937; border-left: 4px solid #00f0ff;
    border-radius: 6px; padding: 16px 20px; margin-bottom: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.noc-card-alert { border-left: 4px solid #ff2a55; }
.noc-label { font-size: 0.85rem; color: #94a3b8; letter-spacing: 0.05em; margin-bottom: 6px; font-weight: 600; }
.noc-weather-value { font-size: 1.7rem; font-weight: 700; color: #f8fafc; line-height: 1.45; white-space: nowrap; overflow: visible; }
.noc-metric-value { font-size: 1.8rem; font-weight: 700; color: #00f0ff; line-height: 1.35; font-family: 'Consolas', monospace; }
.noc-sub-value { font-size: 0.88rem; color: #38bdf8; margin-top: 4px; }
.noc-section-header {
    font-size: 1.15rem; font-weight: 700; color: #f1f5f9; border-bottom: 1px solid #1e293b;
    padding-bottom: 6px; margin-top: 14px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px;
}
.status-dot { height: 10px; width: 10px; background-color: #10b981; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #10b981; }
</style>
"""

def get_city_info(city_name: str) -> dict | None:
    lower_name = str(city_name).lower()
    for c in CITIES:
        if any(k in lower_name for k in c["keywords"]):
            return c
    return None

def normalize_city_to_kanji(city_name: str) -> str:
    info = get_city_info(city_name)
    return info["kanji"] if info else str(city_name)

def format_weather_with_emoji(weather_text: str, weather_code=None) -> str:
    if pd.notna(weather_code):
        try:
            code_int = int(weather_code)
            if code_int in WEATHER_CODE_MAP:
                return WEATHER_CODE_MAP[code_int]
        except (ValueError, TypeError):
            pass

    if not weather_text or pd.isna(weather_text):
        return "❓ 不明"
    w = str(weather_text).strip()
    if any(e in w for e in ["☀️", "🌤️", "⛅", "☁️", "🌧️", "⛈️", "❄️", "🌫️", "🌦️", "☔", "⚡"]):
        return w

    if "雷" in w:
        return f"⛈️ {w}"
    elif "雪" in w or "吹雪" in w:
        return f"❄️ {w}"
    elif "豪雨" in w or "大雨" in w or "強い雨" in w:
        return f"⛈️ {w}"
    elif "雨" in w or "霧雨" in w:
        return f"☔ {w}"
    elif "霧" in w:
        return f"🌫️ {w}"
    elif "快晴" in w or "晴" in w:
        return f"🌤️ {w}" if "曇" in w else f"☀️ {w}"
    elif "曇" in w:
        return f"☁️ {w}"
    return f"🌡️ {w}"
