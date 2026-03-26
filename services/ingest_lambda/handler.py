"""
IoT Core → Ingest Lambda → Timestream
- IoT Core から来た payload を受ける
- 必須項目を読む
- Timestream に WriteRecords する
"""
import json
import os
from typing import Any, Dict, List

import boto3

timestream = boto3.client("timestream-write")

DATABASE_NAME = os.environ["TIMESTREAM_DATABASE_NAME"]
TABLE_NAME = os.environ["TIMESTREAM_TABLE_NAME"]

# payload から必要なデータを取り出す
def build_records(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    device_id = str(event["device_id"])       # デバイスID
    timestamp_ms = str(event["timestamp_ms"]) # タイムスタンプ
    temperature = str(event["temperature"])   # 温度
    humidity = str(event["humidity"])         # 湿度
    co2_ppm = str(event["co2_ppm"])           # CO2濃度

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
