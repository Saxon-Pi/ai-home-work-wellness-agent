"""
DynamoDB → Lambda → AI Agent
DynamoDB に登録された 直近1時間の室内データ を AI Agent に渡す

Agentに渡すデータは以下
- CO2 / 温度 / 湿度 の現在値
- CO2 / 温度 / 湿度 の平均値
- CO2 / 温度 / 湿度 の最大値
- CO2 の上昇傾向

Agent に渡す入力イメージ
{
  "count": 720,
  "latest": {
    "timestamp_ms": 1775311107431,
    "co2_ppm": 2025,
    "temperature": 25.2,
    "humidity": 52.7
  },
  "avg_1h": {
    "co2_ppm": 1450.3,
    "temperature": 24.8,
    "humidity": 50.9
  },
  "max_1h": {
    "co2_ppm": 2150,
    "temperature": 26.1,
    "humidity": 56.3
  },
  "co2_trend": "rising"
}
"""

import os
import time
from decimal import Decimal
from typing import Any, Dict, List
from statistics import mean
from typing import Any, Dict, List
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["METRICS_TABLE_NAME"])

# 特定のデバイスID から送られてきた室内データを取得する
def get_recent_sensor_data(device_id: str, lookback_minutes: int = 60) -> List[Dict[str, Any]]:
    # 直近1時間 のデータに絞り込み
    now_ms = int(time.time() * 1000)
    from_ms = now_ms - (lookback_minutes * 60 * 1000)

    # Dynamo DB からデータ取得
    response = table.query(
        KeyConditionExpression=(
            Key("device_id").eq(device_id) &             # デバイスID
            Key("timestamp_ms").between(from_ms, now_ms) # 時間の絞り込み
        ),
        ScanIndexForward=True,
    )

    """
    戻り値イメージ
    [
        {
            "device_id": "raspi-home-1",
            "timestamp_ms": Decimal("1775372956361"),
            "co2_ppm": Decimal("820"),
            "temperature": Decimal("25.277714199"),
            "humidity": Decimal("57.933928435")
        },
        {
            "device_id": "raspi-home-1",
            "timestamp_ms": Decimal("1775372961361"),
            "co2_ppm": Decimal("830"),
            "temperature": Decimal("25.3"),
            "humidity": Decimal("58.1")
        },
        ...
    ]
    """
    return response["Items"]

# センサ値を小数点一桁に丸める
def round1(value: float) -> float:
    return round(float(value), 1)

# センサ値を整理する
def summarize_sensor_data(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not items:
        return {
            "count": 0,
            "message": "no recent sensor data",
        }

    latest = items[-1] # 最新データ

    # DynamoDB から取得したデータを配列に格納
    co2_values = [float(item["co2_ppm"]) for item in items]
    temp_values = [float(item["temperature"]) for item in items]
    humidity_values = [float(item["humidity"]) for item in items]

    # CO2 のトレンド分析用情報の作成
    first_co2 = co2_values[0]   # 取得期間の最初の CO2
    latest_co2 = co2_values[-1] # 取得期間最後（最新）の CO2

    # 取得期間で CO2 濃度が 100 ppm 以上増加した場合：rising
    if latest_co2 - first_co2 >= 100: 
        co2_trend = "rising"
    # 取得期間で CO2 濃度が 100 ppm 以上減少した場合：falling
    elif first_co2 - latest_co2 >= 100:
        co2_trend = "falling"
    # それ以外：stable
    else:
        co2_trend = "stable"

    # Agent AI に渡すデータ
    return {
      "count": len(items),
      "latest": {
          "timestamp_ms": int(latest["timestamp_ms"]),
          "co2_ppm": int(float(latest["co2_ppm"])),
          "temperature": round1(latest["temperature"]),
          "humidity": round1(latest["humidity"]),
      },
      "avg_1h": {
          "co2_ppm": round1(mean(co2_values)),
          "temperature": round1(mean(temp_values)),
          "humidity": round1(mean(humidity_values)),
      },
      "max_1h": {
          "co2_ppm": int(max(co2_values)),
          "temperature": round1(max(temp_values)),
          "humidity": round1(max(humidity_values)),
      },
      "co2_trend": co2_trend,
    }

def build_prompt(summary: dict) -> str:
    if summary.get("count", 0) == 0:
        return (
            "室内環境データが取得できませんでした。"
            "データ欠損時の短い案内を日本語で返してください。"
        )

    latest = summary["latest"]
    avg_1h = summary["avg_1h"]
    max_1h = summary["max_1h"]
    co2_trend = summary["co2_trend"]

    return f"""
[役割]
あなたはテレワークで働く人々の健康を支援する Wellness Support Specialist です。

[目的]
以下の室内環境データをもとに、ユーザが快適・効率的に仕事ができるように、
短く自然な日本語でアドバイスをしてください。

[室内環境データ]
【現在値】
- CO2: {latest['co2_ppm']} ppm
- 温度: {latest['temperature']} ℃
- 湿度: {latest['humidity']} %

【直近1時間の平均】
- CO2: {avg_1h['co2_ppm']} ppm
- 温度: {avg_1h['temperature']} ℃
- 湿度: {avg_1h['humidity']} %

【直近1時間の最大値】
- CO2: {max_1h['co2_ppm']} ppm
- 温度: {max_1h['temperature']} ℃
- 湿度: {max_1h['humidity']} %

【傾向】
- CO2トレンド: {co2_trend}

[アドバイスのルール]
- 必ず日本語の文章を出力すること
- 2〜4文程度の簡潔な文章とすること
- 不安を煽りすぎず、自然な内容とすること
- 必要に応じて換気、水分補給、休憩、室温調整などを提案すること
""".strip()

def handler(event, context):
    device_id = "raspi-home-1"

    # センサデータ取得 〜 プロンプト構築
    items = get_recent_sensor_data(device_id=device_id, lookback_minutes=60)
    
    if not items:
        return {
            "ok": False,
            "message": "センサーデータが取得できませんでした。デバイスの状態を確認してください。"
        }
    
    summary = summarize_sensor_data(items)
    prompt = build_prompt(summary)

    print("summary:", summary)
    print("prompt:", prompt)

    # Bedrock 呼び出し
    # advice = generate_advice_with_bedrock(prompt)

    return {
        "ok": True,
        "summary": summary,
        "prompt": prompt,
    }
