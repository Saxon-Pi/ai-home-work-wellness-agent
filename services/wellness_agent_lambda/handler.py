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
import json
import urllib.request
from typing import Any, Dict, List
from statistics import mean
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["METRICS_TABLE_NAME"]
DEVICE_ID = os.environ.get("DEVICE_ID", "raspi-home-1") # デバイスID (PK)
LOOKBACK_MINUTES = int(os.environ.get("LOOKBACK_MINUTES", "60")) # データ取得期間 (min)
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

secretsmanager = boto3.client("secretsmanager")
LINE_SECRET_NAME = os.environ["LINE_SECRET_NAME"]

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=BEDROCK_REGION,
)

line_config_cache = None

# LINE 通知用トークンを Secrets Manager から取得する
def get_line_config() -> Dict[str, str]:
    global line_config_cache

    # トークンをキャッシュ化して　Secrets Manager 呼び出しを削減
    if line_config_cache is not None:
        return line_config_cache

    response = secretsmanager.get_secret_value(SecretId=LINE_SECRET_NAME)
    secret_string = response["SecretString"]
    secret = json.loads(secret_string)

    line_config_cache = {
        "channel_access_token": secret["LINE_CHANNEL_ACCESS_TOKEN"],
        "to_user_id": secret["LINE_TO_USER_ID"],
    }

    return line_config_cache

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

# 現在の状態をもとにステータスを分類する
def classify_environment(summary: Dict[str, Any]) -> Dict[str, str]:
    latest = summary["latest"]

    co2 = latest["co2_ppm"]
    temp = latest["temperature"]
    humidity = latest["humidity"]
    
    # 厚生労働省の事務所衛生基準規則などを参考に、暫定的な閾値で室内環境を分類
    # 要対応 (CO2:1000ppm以上, 温度:30℃以上、湿度:70%以上 のいずれかに該当する場合)
    if co2 >= 1000 or temp >= 30 or humidity >= 70:
        status = "alert"
        label = "要対応"
    # 注意 (CO2:800ppm以上, 温度:28℃以上、湿度:60%以上 のいずれかに該当する場合)
    elif co2 >= 800 or temp >= 28 or humidity >= 60:
        status = "warning"
        label = "注意"
    else:
        status = "good"
        label = "良好"

    return {
        "status": status,
        "label": label,
    }

def build_prompt(summary: Dict[str, Any]) -> str:
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

# Bedrock による健康アドバイス生成
def generate_advice_with_bedrock(prompt: str) -> str:
    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ],
                }
            ],
        }

        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())

        text_blocks = response_body.get("content", [])
        if not text_blocks:
            return "アドバイス生成に失敗しました。"

        advice = "".join(
            block.get("text", "")
            for block in text_blocks
            if block.get("type") == "text"
        ).strip()

        if not advice:
            return "アドバイス生成に失敗しました。"

        return advice

    except ClientError as e:
        print("Bedrock ClientError:", str(e))
        return "アドバイス生成に失敗しました。"

    except Exception as e:
        print("Bedrock UnexpectedError:", str(e))
        return "アドバイス生成に失敗しました。"

# LINE メッセージを整える
def format_line_message(summary: Dict[str, Any], status_label: str, advice: str) -> str:
    latest = summary["latest"]

    # Agent の回答の前に付与する室内環境情報
    header = (
        f"【室内環境：{status_label}】\n"
        f"CO2 {latest['co2_ppm']} ppm / " # TODO: (正常)/(注意)/(要対応) の分類も付けたい
        f"{latest['temperature']}℃ / "    # TODO: (正常)/(注意)/(要対応) の分類も付けたい
        f"{latest['humidity']}%"          # TODO: (正常)/(注意)/(要対応) の分類も付けたい
    )

    return f"{header}\n\n{advice}"

# LINE 通知を送信する
def send_line_message(message: str) -> None:
    line_config = get_line_config()

    url = "https://api.line.me/v2/bot/message/push"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {line_config['channel_access_token']}",
    }

    body = {
        "to": line_config["to_user_id"],
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ],
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as res:
            print("LINE response:", res.read().decode("utf-8"))
    except Exception as e:
        print("LINE send error:", str(e))
        raise

def handler(event, context):
    # センサデータ取得 〜 プロンプト構築
    items = get_recent_sensor_data(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

    if not items:
        error_message = "センサーデータが取得できませんでした。デバイスの状態を確認してください。"
        print("error:", error_message)

        return {
            "ok": False,
            "message": error_message,
        }
    
    # Bedrock 呼び出し
    summary = summarize_sensor_data(items)
    env_status = classify_environment(summary)

    prompt = build_prompt(summary)
    advice = generate_advice_with_bedrock(prompt)

    line_message = format_line_message(
        summary=summary,
        status_label=env_status["label"],
        advice=advice,
    )

    # Agent の回答を LINE で通知
    send_line_message(line_message)

    print("summary:", summary)
    print("env_status:", env_status)
    #print("prompt:", prompt)
    print("advice:", advice)
    print("line_message:", line_message)

    return {
        "ok": True,
        "summary": summary,
        "env_status": env_status,
        #"prompt": prompt,
        "advice": advice,
        "line_message": line_message,
    }
