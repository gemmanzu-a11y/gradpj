# 전력예보 | SMP 기반 EV 충전 추천 대시보드

KPX 시간별 SMP 예측 결과를 사용해 EV 충전에 유리한 시간대를 추천하는 Streamlit MVP입니다.
현재 버전은 V5 day-ahead 예측 CSV를 표시하며, 가격 날씨/위험도/급등 가능성을 함께 보여줍니다.

## 기능

- 내일 24시간 SMP 예측 그래프 표시
- 전체 24시간 기준 가장 저렴한 기본 충전 시간 표시
- EV 조건 입력
  - 배터리 용량
  - 현재 SOC
  - 목표 SOC
  - 충전기 출력
  - 충전 가능 시간
- 조건에 맞는 가장 저렴한 연속 충전 구간 추천
- 가격 날씨, 위험도, 급등 가능성 표시

## 로컬 실행

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

브라우저에서 다음 주소를 엽니다.

```text
http://localhost:8501
```

## Streamlit Cloud 배포

1. 이 폴더를 GitHub 저장소로 올립니다.
2. [Streamlit Community Cloud](https://streamlit.io/cloud)에 접속합니다.
3. `New app`을 누릅니다.
4. GitHub 저장소를 선택합니다.
5. Main file path를 `app.py`로 설정합니다.
6. `Deploy`를 누릅니다.

## 배포에 필요한 파일

```text
app.py
requirements.txt
outputs/next_day_smp_forecast_tuned.csv
outputs/recommended_3h_charging_window_tuned.csv
outputs/v5_metrics.json
```

현재 앱은 배포 환경에서 모델을 다시 학습하지 않고, 미리 생성된 예측 CSV를 읽어 화면에 표시합니다.

## 현재 한계

- 전력수요, 날씨, 실제 충전요금제는 아직 반영하지 않았습니다.
- 예측 대상일은 현재 저장된 예측 CSV 기준입니다.
- V2G 방전 추천은 아직 포함하지 않았습니다.
