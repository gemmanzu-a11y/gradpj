from __future__ import annotations

import math
import json
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
FORECAST_PATH = OUTPUTS / "next_day_smp_forecast_tuned.csv"
DEFAULT_RECOMMENDATION_PATH = OUTPUTS / "recommended_3h_charging_window_tuned.csv"
V5_METRICS_PATH = OUTPUTS / "v5_metrics.json"
LIGHTGBM_METRICS_PATH = OUTPUTS / "lightgbm_tuned_metrics.json"

TITLE = "전력예보 | SMP 기반 EV 충전 추천"
PRICE_WEATHER_NOTE = "가격 날씨는 SMP 예측 기반 위험도이며 실제 기상예보와 다릅니다."


st.set_page_config(
    page_title="SMP EV 충전 추천",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def load_forecast() -> pd.DataFrame:
    df = pd.read_csv(FORECAST_PATH, encoding="utf-8-sig")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["market_date"] = pd.to_datetime(df["market_date"])
    df["time_label"] = df["datetime"].dt.strftime("%H:%M")
    df["ramp_probability"] = pd.to_numeric(df.get("ramp_probability", 0.0), errors="coerce").fillna(0.0)
    df["risk_level"] = df.get("risk_level", "낮음")
    df["price_weather"] = df.get("price_weather", "안정")
    return df.sort_values("datetime").reset_index(drop=True)


@st.cache_data
def load_default_recommendation() -> pd.DataFrame:
    df = pd.read_csv(DEFAULT_RECOMMENDATION_PATH, encoding="utf-8-sig")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["ramp_probability"] = pd.to_numeric(df.get("ramp_probability", 0.0), errors="coerce").fillna(0.0)
    df["risk_level"] = df.get("risk_level", "낮음")
    df["price_weather"] = df.get("price_weather", "안정")
    return df


@st.cache_data
def load_metrics() -> dict:
    for path in (V5_METRICS_PATH, LIGHTGBM_METRICS_PATH):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def required_charge_hours(
    battery_kwh: float,
    current_soc: float,
    target_soc: float,
    charger_kw: float,
) -> tuple[float, int, float]:
    needed_kwh = battery_kwh * max(target_soc - current_soc, 0) / 100
    raw_hours = needed_kwh / charger_kw if charger_kw > 0 else 0
    rounded_hours = max(1, math.ceil(raw_hours)) if needed_kwh > 0 else 0
    return needed_kwh, rounded_hours, raw_hours


def filter_available_hours(df: pd.DataFrame, start_hour: int, end_hour: int) -> pd.DataFrame:
    hours = df["hour"].replace({24: 0})
    if start_hour == end_hour:
        mask = pd.Series(True, index=df.index)
    elif start_hour < end_hour:
        mask = (hours >= start_hour) & (hours < end_hour)
    else:
        mask = (hours >= start_hour) | (hours < end_hour)
    return df.loc[mask].copy()


def cheapest_block(df: pd.DataFrame, required_hours: int) -> pd.DataFrame:
    if required_hours <= 0:
        return pd.DataFrame()

    candidates = []
    ordered = df.sort_values("datetime").reset_index(drop=True)
    for start in range(0, len(ordered) - required_hours + 1):
        block = ordered.iloc[start : start + required_hours].copy()
        hour_gap = block["datetime"].diff().dropna()
        if not hour_gap.eq(pd.Timedelta(hours=1)).all():
            continue
        candidates.append((block["predicted_smp"].mean(), start, block))

    if not candidates:
        return pd.DataFrame()

    return min(candidates, key=lambda item: item[0])[2]


def recommendation_summary(block: pd.DataFrame) -> tuple[str, str, float]:
    start = block["datetime"].iloc[0]
    end = block["datetime"].iloc[-1] + pd.Timedelta(hours=1)
    return start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"), block["predicted_smp"].mean()


def style_metric(label: str, value: str, help_text: str | None = None):
    st.metric(label, value, help=help_text)


def format_probability(value: float) -> str:
    return f"{value * 100:.1f}%"


missing_files = [path for path in [FORECAST_PATH, DEFAULT_RECOMMENDATION_PATH] if not path.exists()]
if missing_files:
    st.error("대시보드에 필요한 예측 결과 파일이 없습니다.")
    for path in missing_files:
        st.code(str(path.relative_to(ROOT)))
    st.stop()

forecast = load_forecast()
default_recommendation = load_default_recommendation()
metrics = load_metrics()
forecast_date = forecast["market_date"].iloc[0].strftime("%Y-%m-%d")
max_risk_row = forecast.sort_values(["ramp_probability", "predicted_smp"], ascending=False).iloc[0]

st.title(TITLE)
st.caption("예측 SMP를 바탕으로 EV 충전에 유리한 시간대를 추천합니다.")
st.info(PRICE_WEATHER_NOTE)

if metrics:
    with st.expander("모델 성능 보기"):
        metric_cols = st.columns(4)
        model_name = metrics.get("selected_model", metrics.get("model", "SMP forecast model"))
        mae = metrics.get("final_test_mae", metrics.get("mae", 0))
        rmse = metrics.get("rmse", None)
        charging_regret = metrics.get("average_charging_regret", None)
        metric_cols[0].metric("모델", model_name)
        metric_cols[1].metric("MAE", f"{mae:.3f}")
        metric_cols[2].metric("RMSE", "-" if rmse is None else f"{rmse:.3f}")
        metric_cols[3].metric("충전 regret", "-" if charging_regret is None else f"{charging_regret:.3f}")

with st.sidebar:
    st.header("EV 조건")
    battery_kwh = st.number_input("배터리 용량 (kWh)", min_value=20.0, max_value=150.0, value=60.0, step=1.0)
    current_soc = st.slider("현재 배터리 (%)", min_value=0, max_value=100, value=35, step=1)
    target_soc = st.slider("목표 배터리 (%)", min_value=0, max_value=100, value=80, step=1)
    charger_kw = st.number_input("충전기 출력 (kW)", min_value=1.0, max_value=350.0, value=7.0, step=0.5)
    st.divider()
    st.subheader("충전 가능 시간")
    start_hour = st.selectbox("시작 시간", options=list(range(0, 24)), index=22, format_func=lambda x: f"{x:02d}:00")
    end_hour = st.selectbox("종료 시간", options=list(range(0, 24)), index=8, format_func=lambda x: f"{x:02d}:00")

if target_soc < current_soc:
    st.warning("목표 배터리량이 현재 배터리량보다 낮습니다. 충전 필요량은 0으로 계산됩니다.")

needed_kwh, needed_hours, raw_hours = required_charge_hours(
    battery_kwh=battery_kwh,
    current_soc=current_soc,
    target_soc=target_soc,
    charger_kw=charger_kw,
)

available = filter_available_hours(forecast, start_hour, end_hour)
ev_recommendation = cheapest_block(available, needed_hours)
default_start, default_end, default_avg = recommendation_summary(default_recommendation)

top_cols = st.columns(6)
with top_cols[0]:
    style_metric("예측 대상일", forecast_date)
with top_cols[1]:
    style_metric("기본 추천", f"{default_start[-5:]}~{default_end[-5:]}", "전체 24시간 중 가장 싼 연속 3시간")
with top_cols[2]:
    style_metric("기본 평균 SMP", f"{default_avg:.2f}")
with top_cols[3]:
    style_metric("필요 충전 시간", f"{needed_hours}시간", f"정확 계산값: {raw_hours:.2f}시간")
with top_cols[4]:
    style_metric("가격 날씨", str(max_risk_row.get("price_weather", "-")), "가격 예측 기준 최대 위험 시간")
with top_cols[5]:
    style_metric(
        "위험도 / 급등 가능성",
        f"{max_risk_row.get('risk_level', '-')} · {format_probability(float(max_risk_row['ramp_probability']))}",
    )

left, right = st.columns([1.05, 1.35], gap="large")

with left:
    st.subheader("조건 반영 추천")
    st.write(
        f"필요 충전량은 **{needed_kwh:.1f} kWh**이고, "
        f"충전기 출력 기준 약 **{raw_hours:.2f}시간**이 필요합니다."
    )

    if needed_hours == 0:
        st.success("이미 목표 배터리량을 만족합니다. 추가 충전이 필요하지 않습니다.")
    elif ev_recommendation.empty:
        st.error("선택한 충전 가능 시간 안에서 필요한 연속 충전 시간을 찾지 못했습니다.")
        st.info("충전 가능 시간을 넓히거나 목표 배터리량을 낮춰보세요.")
    else:
        ev_start, ev_end, ev_avg = recommendation_summary(ev_recommendation)
        st.success(f"추천 충전 시간: {ev_start} ~ {ev_end}")
        avg_ramp = ev_recommendation["ramp_probability"].mean()
        rec_cols = st.columns(3)
        rec_cols[0].metric("평균 예측 SMP", f"{ev_avg:.2f}")
        rec_cols[1].metric("충전 시간", f"{len(ev_recommendation)}시간")
        rec_cols[2].metric("급등 가능성", format_probability(avg_ramp))

        display = ev_recommendation[
            ["time_label", "predicted_smp", "risk_level", "price_weather", "ramp_probability"]
        ].rename(
            columns={
                "time_label": "시간",
                "predicted_smp": "예측 SMP",
                "risk_level": "위험도",
                "price_weather": "가격 날씨",
                "ramp_probability": "급등 가능성",
            }
        )
        display["급등 가능성"] = display["급등 가능성"].map(format_probability)
        st.dataframe(display, width="stretch", hide_index=True)

with right:
    st.subheader("내일 24시간 SMP 예측")
    chart_df = forecast[["time_label", "predicted_smp"]].rename(
        columns={"time_label": "시간", "predicted_smp": "예측 SMP"}
    )
    st.line_chart(chart_df, x="시간", y="예측 SMP", height=320)

st.subheader("시간대별 예측값")
table_df = forecast[
    ["time_label", "predicted_smp", "lag_24", "lag_168", "price_weather", "risk_level", "ramp_probability"]
].rename(
    columns={
        "time_label": "시간",
        "predicted_smp": "예측 SMP",
        "lag_24": "전일 같은 시간 SMP",
        "lag_168": "전주 같은 시간 SMP",
        "price_weather": "가격 날씨",
        "risk_level": "위험도",
        "ramp_probability": "급등 가능성",
    }
)
table_df["급등 가능성"] = table_df["급등 가능성"].map(format_probability)
st.dataframe(table_df, width="stretch", hide_index=True)

st.caption(
    "현재 화면은 저장된 day-ahead SMP 예측 CSV를 표시합니다. "
    "전력수요, 실제 기상예보, 실제 충전요금제는 아직 반영하지 않았습니다."
)
