"""
IoT Core → Ingest Lambda → Timestream
Rule の対象 topic にマッチするメッセージが来たら Ingest Lambda が起動する
- IoT Core から来た payload を受け取る
- payload からデータを抽出する
- Timestream にデータを WriteRecords する
"""

import json
import os
from typing import Any, Dict, List
import boto3

timestream = boto3.client("timestream-write")

DATABASE_NAME = os.environ["TIMESTREAM_DATABASE_NAME"]
TABLE_NAME = os.environ["TIMESTREAM_TABLE_NAME"]

# payload からデータを抽出し、Timestream の書き込み仕様に合わせたデータ構造に整形
def build_records(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    device_id    = str(event["device_id"])     # デバイスID
    timestamp_ms = str(event["timestamp_ms"])  # タイムスタンプ
    temperature  = float(event["temperature"]) # 温度
    humidity     = float(event["humidity"])    # 湿度
    co2_ppm      = int(event["co2_ppm"])       # CO2濃度

    print("Parsed values:", {
        "device_id": device_id,
        "temperature": temperature,
        "humidity": humidity,
        "co2_ppm": co2_ppm,
    })

    # 共通データ (payload内の全measureに共通の項目)
    common_attributes = {
        "Dimensions": [
            {
                "Name": "device_id",
                "Value": device_id,
            }
        ],
        "Time": timestamp_ms,
        "TimeUnit": "MILLISECONDS",
    }

    # 個別データ (その時刻・そのデバイスにおける観測項目)
    records = [
        {
            "MeasureName": "temperature",
            "MeasureValue": temperature,
            "MeasureValueType": "DOUBLE",
        },
        {
            "MeasureName": "humidity",
            "MeasureValue": humidity,
            "MeasureValueType": "DOUBLE",
        },
        {
            "MeasureName": "co2_ppm",
            "MeasureValue": co2_ppm,
            "MeasureValueType": "BIGINT",
        },
    ]

    return common_attributes, records

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    print("Received event:", json.dumps(event, ensure_ascii=False))

    # 必要なデータが揃っていない場合はエラー
    required_keys = ["device_id", "timestamp_ms", "temperature", "humidity", "co2_ppm"]
    missing_keys = [key for key in required_keys if key not in event]

    if missing_keys:
        raise ValueError(f"Missing required keys: {missing_keys}")
    
    # データが揃っていれば構造化
    try:    
        common_attributes, records = build_records(event)
    except Exception as e:
        print("Build records failed: ", str(e))
        raise
    
    # Timestream に書き込み
    response = timestream.write_records(
        DatabaseName=DATABASE_NAME,
        TableName=TABLE_NAME,
        Records=records,
        CommonAttributes=common_attributes,
    )

    print("Timestream write response:", json.dumps(response, default=str))

    return {
        "ok": True,
        "device_id": event["device_id"],
        "record_count": len(records),
    }
