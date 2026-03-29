"""
IoT Core → Ingest Lambda → DynamoDB
Rule の対象 topic にマッチするメッセージが来たら Ingest Lambda が起動する
- IoT Core から来た payload を受け取る
- payload からデータを抽出する
- DynamoDB にデータを PutItem する
"""

import json
import os
from decimal import Decimal
from typing import Any, Dict, List
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["METRICS_TABLE_NAME"])

# Python の float型データを DynamoDB に保存できる形に変換
def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value))

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    print("Received event:", json.dumps(event, ensure_ascii=False))

    # 必要なデータが揃っていない場合はエラー
    required_keys = ["device_id", "timestamp_ms", "temperature", "humidity", "co2_ppm"]
    missing_keys = [key for key in required_keys if key not in event]

    if missing_keys:
        raise ValueError(f"Missing required keys: {missing_keys}")
    
    device_id    = str(event["device_id"])     # デバイスID
    timestamp_ms = int(event["timestamp_ms"])  # タイムスタンプ
    temperature  = float(event["temperature"]) # 温度
    humidity     = float(event["humidity"])    # 湿度
    co2_ppm      = int(event["co2_ppm"])       # CO2濃度

    item = {
        "device_id"    : device_id,
        "timestamp_ms" : timestamp_ms,
        "temperature"  : to_decimal(temperature),
        "humidity"     : to_decimal(humidity),
        "co2_ppm"      : co2_ppm,
    }

    print("Parsed values:",
          json.dumps(
              {
                  "device_id": device_id,
                  "temperature": temperature,
                  "humidity": humidity,
                  "co2_ppm": co2_ppm,
                  },
                  ensure_ascii=False,
          ),
    )
    
    table.put_item(Item=item)

    return {
        "ok": True,
        "device_id": event["device_id"],
        "timestamp_ms": timestamp_ms,
    }
