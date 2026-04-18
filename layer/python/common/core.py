"""
ツールで使用する既存の関数群
元々の Lambda関数 (old_handler.py) で定義した関数をツールに流用する
"""

import os
import time
import json
import urllib.request
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
from statistics import mean
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["METRICS_TABLE_NAME"]                    # センサデータテーブル
AGENT_STATE_TABLE_NAME = os.environ["AGENT_STATE_TABLE_NAME"]    # ステータステーブル
DEVICE_ID = os.environ.get("DEVICE_ID", "raspi-home-1")          # デバイスID (PK)
LOOKBACK_MINUTES = int(os.environ.get("LOOKBACK_MINUTES", "60")) # データ取得期間 (min)
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
agent_state_table = dynamodb.Table(AGENT_STATE_TABLE_NAME)

secretsmanager = boto3.client("secretsmanager")
LINE_SECRET_NAME = os.environ["LINE_SECRET_NAME"]

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=BEDROCK_REGION,
)

line_config_cache = None

JST = timezone(timedelta(hours=9))

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

# 前回の通知情報（室内環境ステータスなど）を保存する
def save_agent_state(device_id: str, status: str, message: str, notified_at_ms: int) -> None:
    agent_state_table.put_item(
        Item={
            "device_id": device_id,
            "last_status": status,                 # 室内環境ステータス
            "last_message": message,               # LINEメッセージ
            "last_notified_at_ms": notified_at_ms, # 通知時刻
        }
    )

# 前回の通知情報（室内環境ステータスなど）を取得する
def get_last_agent_state(device_id: str) -> Dict[str, Any] | None:
    # 主キー完全一致で 1レコード だけ取得
    response = agent_state_table.get_item(
        Key={"device_id": device_id}
    )
    return response.get("Item")

# LINE 通知の要否を判定する (平常時に短期間の通知を避ける)
def should_send_notification(
    current_status: str,
    last_state: Dict[str, Any] | None,
    now_ms: int,
) -> bool:
    # 前回の室内環境ステータスが存在しなければ通知
    if last_state is None:
        return True

    last_status = last_state.get("last_status")
    last_notified_at_ms = int(float(last_state.get("last_notified_at_ms", 0)))

    # 前回からステータスが変化したら通知
    if current_status != last_status:
        return True
    
    elapsed_ms = now_ms - last_notified_at_ms

    # ステータスが "alert" なら 30分ごとに再通知
    if current_status == "alert":
        return elapsed_ms >= 30 * 60 * 1000
    
    # ステータスが "good" / "warning" なら 1時間ごとに再通知
    return elapsed_ms >= 60 * 60 * 1000

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

    # CO2 のトレンド分類用情報の作成
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

# 直近1時間の室内環境データを取得する (最新値、1時間平均、1時間最大、CO2トレンド、環境ステータス)
def get_environment_summary(device_id: str, lookback_minutes: int = 60) -> Dict[str, Any]:
    items = get_recent_sensor_data(device_id=device_id, lookback_minutes=lookback_minutes)

    if not items:
        error_message = "センサーデータが取得できませんでした。デバイスの状態を確認してください。"
        print("error:", error_message)

        return {
            "ok": False,
            "message": error_message,
        }

    summary = summarize_sensor_data(items)
    env_status = classify_environment(summary)

    return {
        "ok": True,
        "summary": summary,
        "env_status": env_status,
    }

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

# LINE のチャットに応答する
def reply_line_message(reply_token: str, message: str) -> None:
    line_config = get_line_config()

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {line_config['channel_access_token']}",
    }
    
    body = {
        "replyToken": reply_token,
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

    with urllib.request.urlopen(req) as res:
        print("LINE reply response:", res.read().decode("utf-8"))

# Google Calendar API の start/end を datetime に変換する
def parse_google_calendar_datetime(value: Dict[str, str]) -> Optional[datetime]:
    # dateTime (開始時刻・終了時刻が明確にあるイベント) がある場合はそちらを優先
    if "dateTime" in value:
        dt_str = value["dateTime"]
        return datetime.fromisoformat(dt_str)

    # 終日イベントの場合は JST 00:00 として扱う
    if "date" in value:
        date_str = value["date"]
        return datetime.fromisoformat(date_str).replace(tzinfo=JST)

    return None

# datetime を JST の ISO 8601 文字列に変換する
# 例: datetime(2026, 4, 17, 13, 0, tzinfo=JST) -> 2026-04-17T13:00:00+09:00
def to_isoformat_jst(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(JST).isoformat()

# Google Calendar API のイベントを Agent 用の共通形式に整形する
def normalize_calendar_event(event: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    出力イメージ：
    {
        "summary": "顧客MTG",
        "start": "2026-04-17T13:00:00+09:00",
        "end": "2026-04-17T14:00:00+09:00"
    }
    """

    start_dt = parse_google_calendar_datetime(event.get("start", {}))
    end_dt = parse_google_calendar_datetime(event.get("end", {}))

    if start_dt is None:
        return None

    return {
        "summary": event.get("summary", "予定"),
        "start": to_isoformat_jst(start_dt),
        "end": to_isoformat_jst(end_dt),
    }

# 取得した Google Calendar イベント一覧から、Agent に渡すイベントサマリを作成する
# 出力は「直近1時間にイベントが入っているか」のフラグと、今後のイベント一覧 (最大3件) 
def get_calendar_context_from_events(
    events: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    if now is None:
        now = datetime.now(JST)

    parsed_events: List[Dict[str, Any]] = []   # API から取得したイベント一覧 (整形済)
    upcoming_events: List[Dict[str, Any]] = [] # 最終的に Agent に渡す今後のイベント一覧（最大3件）

    # Google Calendar API から取得したイベントを個別に整形
    for event in events:
        normalized_event = normalize_calendar_event(event)
        if normalized_event is None:
            continue

        start_dt = datetime.fromisoformat(normalized_event["start"])
        parsed_events.append(
            {
                "summary": normalized_event["summary"],
                "start_dt": start_dt,
                "start": normalized_event["start"],
                "end": normalized_event["end"],
            }
        )

    # 現在以降のイベントのみを抽出
    future_events = [e for e in parsed_events if e["start_dt"] >= now]
    future_events.sort(key=lambda x: x["start_dt"])

    # 次のイベントを最大3件抽出
    next_three = future_events[:3]

    for event in next_three:
        upcoming_events.append(
            {
                "summary": event["summary"],
                "start": event["start"],
                "end": event["end"],
            }
        )

    # 直近1時間以内に予定が入っているかのフラグ
    within_1h_limit = now + timedelta(hours=1)
    has_event_within_1h = any(e["start_dt"] <= within_1h_limit for e in next_three)

    return {
        "ok": True,
        "has_event_within_1h": has_event_within_1h,
        "upcoming_events": upcoming_events,
    }
