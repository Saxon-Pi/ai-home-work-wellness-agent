"""
ラズパイ と IoT Core の疎通確認用コード
ダミーのペイロードを ラズパイ → IoT Core に送信する
"""

import json
import time
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

# エンドポイントはコンソールから確認する
ENDPOINT = "a1hfmham2ql5ac-ats.iot.ap-northeast-1.amazonaws.com"

client = AWSIoTMQTTClient("raspi-home-1")

client.configureEndpoint(ENDPOINT, 8883)
# ダウンロードした証明書ファイル名が異なる場合は、ファイル名に合わせて変更すること
client.configureCredentials(
    "certs/AmazonRootCA1.pem",
    "certs/private.pem.key",
    "certs/certificate.pem.crt"
)

client.connect()

# トピック名
topic = "wellness/device/raspi-home-1/telemetry"

# テスト用ペイロード
while True:
    payload = {
        "device_id": "raspi-home-1",
        "timestamp_ms": int(time.time() * 1000),
        "temperature": 25.0,
        "humidity": 40.0,
        "co2_ppm": 500
    }

    client.publish(topic, json.dumps(payload), 1)
    print("Published:", payload)

    time.sleep(5)
