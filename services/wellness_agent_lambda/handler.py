"""
DynamoDB → Lambda → AI Agent
DynamoDB に登録された 直近1時間の室内データ を AI Agent に渡す

Agentに渡すデータは以下
- CO2 / 温度 / 湿度 の現在値
- 直近1時間の平均 CO2
- 直近1時間の最大 CO2
- CO2 の上昇傾向

データイメージ
{
  "device_id": "raspi-home-1",
  "now": {
    "co2_ppm": 1877,
    "temperature": 25.19,
    "humidity": 52.68
  },
  "last_1h": {
    "avg_co2_ppm": 1450,
    "max_co2_ppm": 2018,
    "trend": "rising"
  }
}
"""

import os
import time
from decimal import Decimal
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

    return response["Items"]
