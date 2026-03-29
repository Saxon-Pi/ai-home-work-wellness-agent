"""
ラズパイ と IoT Core の疎通確認用コード
ダミーのペイロードを ラズパイ → IoT Core に送信する
※ 自分の環境だとラズパイの Python バージョンが古く AWSIoTPythonSDK でエラーが出るため、
  paho-mqtt を使用して接続確認をしたときのバージョン
"""

import json
import ssl
import time
import paho.mqtt.client as mqtt

# エンドポイントはコンソールから確認する
ENDPOINT = "a1hfmham2ql5ac-ats.iot.ap-northeast-1.amazonaws.com"
PORT = 8883
CLIENT_ID = "raspi-home-1"
# トピック名
TOPIC = "wellness/device/raspi-home-1/telemetry"

# 各証明書の格納先、ファイル名に合わせる
CA_PATH = "AmazonRootCA1.pem"
CERT_PATH = "certificate.pem.crt"
KEY_PATH = "private.pem.key"


def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)


def on_publish(client, userdata, mid):
    print("Published message id:", mid)


client = mqtt.Client(client_id=CLIENT_ID)
client.on_connect = on_connect
client.on_publish = on_publish

client.tls_set(
    ca_certs=CA_PATH,
    certfile=CERT_PATH,
    keyfile=KEY_PATH,
    cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLSv1_2,
)

client.connect(ENDPOINT, PORT, keepalive=60)
client.loop_start()

while True:
    # テスト用ペイロード
    payload = {
        "device_id": "raspi-home-1",
        "timestamp_ms": int(time.time() * 1000),
        "temperature": 25.0,
        "humidity": 40.0,
        "co2_ppm": 500,
    }

    result = client.publish(TOPIC, json.dumps(payload), qos=1)
    print("Publish result:", result.rc, payload)
    time.sleep(5)
