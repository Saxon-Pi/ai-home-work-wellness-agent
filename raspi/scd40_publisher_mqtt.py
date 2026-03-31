"""
ラズパイと SCD40センサーモジュールを接続し、
取得した CO2・温度・湿度データを MQTT で IoT Core に publish するコード

ラズパイとセンサーのやり取りは以下のイメージ
- ラズパイ が I2C でセンサーに命令を送る
- センサーが内部で測定する
- ラズパイ が測定結果の生データを読む
- 生データが壊れていないか CRC で確認する
- CO2 / 温度 / 湿度に変換する
"""

import json
import ssl
import time
import paho.mqtt.client as mqtt
from smbus2 import SMBus, i2c_msg

# エンドポイントはコンソールから確認する
ENDPOINT = "a1hfmham2ql5ac-ats.iot.ap-northeast-1.amazonaws.com"
PORT = 8883
CLIENT_ID = "raspi-home-1"
# トピック名
TOPIC = "wellness/device/raspi-home-1/telemetry"

# ダウンロードした証明書ファイル名が異なる場合は、ファイル名に合わせて変更すること
CA_PATH = "AmazonRootCA1.pem"
CERT_PATH = "certificate.pem.crt"
KEY_PATH = "private.pem.key"

I2C_ADDR = 0x62
bus = SMBus(1)

def on_connect(client, userdata, flags, rc):
    print("Connected with result code:", rc)

def on_publish(client, userdata, mid):
    print("Published message id:", mid)

# SCD40 に命令を送信
def send_command(command: int) -> None:
    msb = (command >> 8) & 0xFF
    lsb = command & 0xFF
    msg = i2c_msg.write(I2C_ADDR, [msb, lsb])
    bus.i2c_rdwr(msg)

# SCD40 から返ってきた生データをバイト列で読み込む
def read_bytes(length: int) -> bytes:
    msg = i2c_msg.read(I2C_ADDR, length)
    bus.i2c_rdwr(msg)
    return bytes(msg)

# 受信データの破損を確認するための CRC を計算
def calc_crc(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc

# 2バイトの値を取り出して CRC チェックし、整数として取り出す
def parse_word_with_crc(raw: bytes, offset: int) -> int:
    word = raw[offset:offset + 2]
    crc = raw[offset + 2]
    if calc_crc(word) != crc:
        raise ValueError("CRC mismatch at offset {}".format(offset))
    return (word[0] << 8) | word[1]

def start_periodic_measurement():
    # 0x21B1: 測定開始
    send_command(0x21B1)
    # 初回測定が安定するまで待機
    time.sleep(5)

# センサー値の読み取り
def read_measurement():
    # 0xEC05: 測定結果の取得
    send_command(0xEC05)
    time.sleep(0.01)

    # CO2, temp, humidity が各2byte + CRC1byte = 9 bytes
    raw = read_bytes(9)

    co2_raw = parse_word_with_crc(raw, 0)
    temp_raw = parse_word_with_crc(raw, 3)
    hum_raw = parse_word_with_crc(raw, 6)

    # 正規化 & スケール変換 & オフセット
    temperature = -45 + 175 * (temp_raw / 65535.0) # -45 ～ +130 ℃
    humidity = 100 * (hum_raw / 65535.0) # 0 ~ 100 %

    return co2_raw, temperature, humidity


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

start_periodic_measurement()

while True:
    # センサーの測定値をペイロードとして publish
    co2, temp, hum = read_measurement()

    payload = {
        "device_id": "raspi-home-1",
        "timestamp_ms": int(time.time() * 1000),
        "temperature": round(temp, 2), # 小数点二桁
        "humidity": round(hum, 2),     # 小数点二桁
        "co2_ppm": int(co2),
    }

    result = client.publish(TOPIC, json.dumps(payload), qos=1)
    print("Publish result:", result.rc, payload)
    time.sleep(5)
