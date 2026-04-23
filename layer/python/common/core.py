"""
ツールで使用する既存の関数群
元々の Lambda関数 (old_handler.py) で定義した関数をツールに流用する
"""

import os
import time
import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
from statistics import mean
import uuid
from io import BytesIO
import matplotlib.pyplot as plt
import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["METRICS_TABLE_NAME"]                    # センサデータテーブル
AGENT_STATE_TABLE_NAME = os.environ["AGENT_STATE_TABLE_NAME"]    # ステータステーブル
DEVICE_ID = os.environ.get("DEVICE_ID", "raspi-home-1")          # デバイスID (PK)
LOOKBACK_MINUTES = int(os.environ.get("LOOKBACK_MINUTES", "60")) # データ取得期間 (min)
WEATHER_LATITUDE = os.environ.get("WEATHER_LATITUDE")            # 緯度 (天気取得用)
WEATHER_LONGITUDE = os.environ.get("WEATHER_LONGITUDE")          # 経度 (天気取得用)
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
ATHENA_DATABASE = os.environ["ATHENA_DATABASE"]
ATHENA_TABLE = os.environ["ATHENA_TABLE"]
ATHENA_OUTPUT_LOCATION = os.environ["ATHENA_OUTPUT_LOCATION"]
REPORT_BUCKET_NAME = os.environ["REPORT_BUCKET_NAME"]

dynamodb = boto3.resource("dynamodb")
athena = boto3.client("athena")
s3_client = boto3.client("s3")

table = dynamodb.Table(TABLE_NAME)
agent_state_table = dynamodb.Table(AGENT_STATE_TABLE_NAME)

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name=BEDROCK_REGION,
)

JST = timezone(timedelta(hours=9))

# シークレットのキャッシュ
secretsmanager = boto3.client("secretsmanager")
LINE_SECRET_NAME = os.environ["LINE_SECRET_NAME"]
GOOGLE_CALENDAR_SECRET_NAME = os.environ["GOOGLE_CALENDAR_SECRET_NAME"]
line_config_cache = None
google_oauth_cache: Optional[Dict[str, str]] = None

# =====================================================
# 室内環境データの取得
# =====================================================

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

# =====================================================
# LINE 通知
# =====================================================

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

# =====================================================
# Google Calendar 連携
# =====================================================

# Google OAuth 設定を Secrets Manager から取得する
def get_google_calendar_oauth_config() -> Dict[str, str]:
    global google_oauth_cache

    # トークンをキャッシュ化して　Secrets Manager 呼び出しを削減
    if google_oauth_cache is not None:
        return google_oauth_cache

    response = secretsmanager.get_secret_value(SecretId=GOOGLE_CALENDAR_SECRET_NAME)
    secret = json.loads(response["SecretString"])

    google_oauth_cache = {
        "client_id": secret["GOOGLE_CLIENT_ID"],
        "client_secret": secret["GOOGLE_CLIENT_SECRET"],
        "refresh_token": secret["GOOGLE_REFRESH_TOKEN"],
    }

    return google_oauth_cache

# refresh token を使って Google OAuth の access_token を取得する
def get_google_access_token() -> str:
    oauth = get_google_calendar_oauth_config()

    token_url = "https://oauth2.googleapis.com/token"

    payload = urllib.parse.urlencode(
        {
            "client_id": oauth["client_id"],
            "client_secret": oauth["client_secret"],
            "refresh_token": oauth["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        token_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urllib.request.urlopen(req) as res:
        token_response = json.loads(res.read().decode("utf-8"))

    access_token = token_response.get("access_token")
    if not access_token:
        raise RuntimeError("Google access token の取得に失敗しました")

    return access_token

# Google Calendar API から今後のイベントを取得する
def fetch_google_calendar_events(
    calendar_id: str = "primary",
    max_results: int = 10,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    if now is None:
        now = datetime.now(JST)

    access_token = get_google_access_token()

    # Calendar の検索条件
    params = {
        "timeMin": now.astimezone(timezone.utc).isoformat(), # 現在時刻以降のイベントを取得
        "maxResults": str(max_results), # 最大取得件数
        "singleEvents": "true",         # 繰り返しイベントを個別に取得
        "orderBy": "startTime",         # 開始時刻順にソート
    }

    # API のエンドポイント
    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/"
        f"{urllib.parse.quote(calendar_id, safe='')}/events?"
        f"{urllib.parse.urlencode(params)}"
    )

    # リクエスト
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(req) as res:
        response_data = json.loads(res.read().decode("utf-8"))

    return response_data.get("items", [])

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
# 出力は「直近1時間以内にイベントがあるか」のフラグと、
# 今後のイベント一覧（開始時刻が近い順で最大3件）
def get_calendar_context_from_events(
    events: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    if now is None:
        now = datetime.now(JST)

    parsed_events: List[Dict[str, Any]] = []   # APIから取得したイベント一覧（整形済み、start_dt付き）
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
    future_events.sort(key=lambda e: e["start_dt"])

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

# API実行 → イベント整理 → Agent 用フォーマット変換 までの統合レイヤー
def get_calendar_context() -> Dict[str, Any]:
    try:
        events = fetch_google_calendar_events()
        return get_calendar_context_from_events(events)

    except Exception as e:
        print("Google Calendar fetch error:", str(e))

        return {
            "ok": False,
            "message": "Google Calendar のイベント取得に失敗しました。",
            "has_event_within_1h": False,
            "upcoming_events": [],
        }

# =====================================================
# Open-Meteo (天気予報) 連携
# =====================================================

# Open-Meteo の weather_code を日本語ラベルに変換する
def weather_code_to_label(code: int) -> str:
    mapping = {
        0: "快晴",
        1: "晴れ",
        2: "一部曇り",
        3: "曇り",
        45: "霧",
        48: "霧氷",
        51: "弱い霧雨",
        53: "霧雨",
        55: "強い霧雨",
        56: "弱い着氷性霧雨",
        57: "強い着氷性霧雨",
        61: "弱い雨",
        63: "雨",
        65: "強い雨",
        66: "弱い着氷性の雨",
        67: "強い着氷性の雨",
        71: "弱い雪",
        73: "雪",
        75: "強い雪",
        77: "霧雪",
        80: "弱いにわか雨",
        81: "にわか雨",
        82: "強いにわか雨",
        85: "弱いにわか雪",
        86: "強いにわか雪",
        95: "雷雨",
        96: "弱い雷雨と雹",
        99: "強い雷雨と雹",
    }

    return mapping.get(code, "不明")

# 文字列の target_datetime を datetime に変換する
def parse_target_datetime(target_datetime: Optional[str]) -> datetime:
    if not target_datetime:
        return datetime.now(JST)

    # UTC → JST 変換 (タイムゾーンがない場合はJSTとして扱う)
    dt = datetime.fromisoformat(target_datetime)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)

    return dt.astimezone(JST)

# target_dt に最も近い hourly データのインデックスを返す
def find_nearest_hourly_index(hourly_times: List[str], target_dt: datetime) -> int:
    min_diff = None
    min_idx = 0

    for i, t in enumerate(hourly_times):
        # Open-Meteo の hourly time は timezone 文字列なしで返るため、API指定の Asia/Tokyo 前提で JST を付与
        hourly_dt = datetime.fromisoformat(t).replace(tzinfo=JST)
        diff = abs((hourly_dt - target_dt).total_seconds())

        if min_diff is None or diff < min_diff:
            min_diff = diff
            min_idx = i

    return min_idx

# 月から季節コンテキスト（summer / winter / other）を判定する
def get_season_context(target_dt: Optional[datetime] = None) -> Dict[str, Any]:
    if target_dt is None:
        target_dt = datetime.now(JST)

    month = target_dt.month

    # 夏季: 7 ~ 9 月
    if month in [7, 8, 9]:
        season = "summer"
    # 冬季: 12 ~ 2 月
    elif month in [12, 1, 2]:
        season = "winter"
    else:
        season = "other"

    return {
        "season": season,
        "month": month,
    }

# 天気情報と季節情報から健康アラートを生成する
def build_health_alerts(
    weather: Dict[str, Any],
    season_context: Dict[str, Any],
) -> Dict[str, bool]:
    season = season_context["season"]  # summer / winter / other
    temp_max_c = weather["temp_max_c"] # 最高気温
    humidity = weather["humidity"]     # 湿度

    # 夏季 かつ 最高気温が35℃ 以上なら、熱中症リスクあり
    heat_risk = season == "summer" and temp_max_c >= 35
    # 冬季 かつ 湿度が40% 以下なら、乾燥リスクあり
    dryness_risk = season == "winter" and humidity <= 40

    return {
        "heat_risk": heat_risk,
        "dryness_risk": dryness_risk,
    }

# Open-Meteo API から指定日時に近い天気と日次の気温情報を取得する
def fetch_weather_data(target_datetime: Optional[str] = None) -> Dict[str, Any]:
    """
    出力イメージ：
    {
        "condition": "晴れ",
        "temperature_c": 35.2,
        "humidity": 58,
        "temp_max_c": 36.0,
        "temp_min_c": 24.0
    }
    """

    if not WEATHER_LATITUDE or not WEATHER_LONGITUDE:
        raise RuntimeError("WEATHER_LATITUDE or WEATHER_LONGITUDE is not set")

    target_dt = parse_target_datetime(target_datetime)
    print(f"[Weather] fetch target: {target_dt.isoformat()}")

    params = {
        "latitude": WEATHER_LATITUDE,
        "longitude": WEATHER_LONGITUDE,
        "timezone": "Asia/Tokyo",
        "hourly": "temperature_2m,relative_humidity_2m,weather_code", # 1時間ごとの予報データ
        "daily": "temperature_2m_max,temperature_2m_min",             # 1日単位のサマリデータ
        "forecast_days": "3", # 最大3日分の予報を取得
    }

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"{urllib.parse.urlencode(params)}"
    )

    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )

    with urllib.request.urlopen(req) as res:
        response_data = json.loads(res.read().decode("utf-8"))

    hourly = response_data["hourly"]
    daily = response_data["daily"]

    # hourly データは 1時間ごとの配列
    hourly_times = hourly["time"]
    hourly_temps = hourly["temperature_2m"]
    hourly_humidity = hourly["relative_humidity_2m"]
    hourly_weather_code = hourly["weather_code"]

    # hourly 配列から target_dt に最も近いインデックスを特定
    idx = find_nearest_hourly_index(hourly_times, target_dt)

    # 指定時刻の 温度 / 湿度 / 天気コード を取得
    forecast_temp = hourly_temps[idx]
    forecast_humidity = hourly_humidity[idx]
    forecast_weather_code = hourly_weather_code[idx]

    # target_dt から日付文字列（YYYY-MM-DD）を作成
    target_date_str = target_dt.strftime("%Y-%m-%d")
    daily_dates = daily["time"]

    # 日付に該当するインデックスを特定
    if target_date_str in daily_dates:
        daily_idx = daily_dates.index(target_date_str)
    else:
        # target_date が daily データに含まれない場合は先頭の日付を使用
        daily_idx = 0

    # 指定日付の 最低気温 / 最高気温 を取得
    forecast_temp_max = daily["temperature_2m_max"][daily_idx]
    forecast_temp_min = daily["temperature_2m_min"][daily_idx]

    return {
        "condition": weather_code_to_label(int(forecast_weather_code)),
        "temperature_c": float(forecast_temp),
        "humidity": int(forecast_humidity),
        "temp_max_c": float(forecast_temp_max),
        "temp_min_c": float(forecast_temp_min),
        "target_datetime": target_dt.isoformat(),
    }

# API実行 → 天気情報整理 → Agent 用フォーマット変換 までの統合レイヤー
def get_weather_context(target_datetime: Optional[str] = None) -> Dict[str, Any]:
    """
    出力イメージ：
    {
        "ok": true,
        "weather": {
            "condition": "晴れ",
            "temperature_c": 35.2,
            "humidity": 58,
            "temp_max_c": 36.0,
            "temp_min_c": 24.0
        },
        "season_context": {
            "season": "summer",
            "month": 8
        },
        "health_alerts": {
            "heat_risk": true,
            "dryness_risk": false
        }
    }
    """

    try:
        target_dt = parse_target_datetime(target_datetime)
        print(f"[Weather] target_datetime(raw): {target_datetime}")
        print(f"[Weather] target_datetime(parsed JST): {target_dt.isoformat()}")
        weather = fetch_weather_data(target_datetime=target_dt.isoformat())
        season_context = get_season_context(target_dt=target_dt)
        health_alerts = build_health_alerts(
            weather=weather,
            season_context=season_context,
        )

        return {
            "ok": True,
            "weather": weather,
            "season_context": season_context,
            "health_alerts": health_alerts,
        }

    except Exception as e:
        print("Weather fetch error:", str(e))
        return {
            "ok": False,
            "message": "天気情報の取得に失敗しました。",
            "weather": {},
            "season_context": {},
            "health_alerts": {
                "heat_risk": False,
                "dryness_risk": False,
            },
        }
    
# =====================================================
# グラフレポート作成
# =====================================================

# グラフの描画範囲に応じてデータの取得期間と集約粒度を決める
# (範囲は1時間、1日、7日のいずれかを選択)
def get_period_config(period: str) -> Dict[str, Any]:
    configs = {
        "1h": {
            "lookback_seconds": 60 * 60,
            "bucket_minutes": 10,
        },
        "1d": {
            "lookback_seconds": 24 * 60 * 60,
            "bucket_minutes": 30,
        },
        "7d": {
            "lookback_seconds": 7 * 24 * 60 * 60,
            "bucket_minutes": 60,
        },
    }

    if period not in configs:
        raise ValueError(f"unsupported period: {period}")
    
    return configs[period]

# Athena クエリが完了するまで待機する
def wait_for_athena_query(query_execution_id: str, poll_seconds: float = 1.0) -> None:
    while True:
        # クエリ実行状況の取得
        response = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = response["QueryExecution"]["Status"]["State"]

        # クエリが 成功/失敗 なら終了
        if state == "SUCCEEDED":
            return
        if state in ["FAILED", "CANCELLED"]:
            reason = response["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(f"Athena query failed: {state} {reason}")

        time.sleep(poll_seconds)

# 指定期間のセンサデータを Athena から取得する
def run_athena_query_for_sensor_history(period: str) -> List[Dict[str, Any]]:
    config = get_period_config(period)

    # データ取得期間
    now_ms = int(time.time() * 1000)
    from_ms = now_ms - (config["lookback_seconds"] * 1000)

    # CO2、温度、湿度をクエリ
    query = f"""
    SELECT
      timestamp_ms,
      CAST(co2_ppm AS DOUBLE) AS co2_ppm,
      CAST(temperature AS DOUBLE) AS temperature,
      CAST(humidity AS DOUBLE) AS humidity
    FROM "{ATHENA_DATABASE}"."{ATHENA_TABLE}"
    WHERE device_id = '{DEVICE_ID}'
      AND timestamp_ms BETWEEN {from_ms} AND {now_ms}
    ORDER BY timestamp_ms ASC
    """.strip()

    # クエリ実行
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT_LOCATION},
    )

    # クエリ完了まで待機
    query_execution_id = response["QueryExecutionId"]
    wait_for_athena_query(query_execution_id)

    # Athena の結果は一度に全部返ってこないため paginator
    paginator = athena.get_paginator("get_query_results")
    rows: List[Dict[str, Any]] = []

    page_iterator = paginator.paginate(QueryExecutionId=query_execution_id)

    # 全ページを 1つの配列にまとめる
    header: List[str] | None = None
    for page in page_iterator:
        for row in page["ResultSet"]["Rows"]:
            values = [col.get("VarCharValue", "") for col in row["Data"]]

            # ヘッダー処理 (最初の1行はcolumn名)
            if header is None:
                header = values
                continue
            
            # JSONライクに変換してリスト化
            record = dict(zip(header, values))
            rows.append(record)

    return rows
