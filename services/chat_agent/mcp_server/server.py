from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from common.core import get_weather_context

mcp = FastMCP("wellness-tools")


@mcp.tool()
def get_weather_context_tool(target_datetime: str) -> Dict[str, Any]:
    """
    指定日時の天気情報と季節に関する健康アラート情報を取得するツールです。
    夕方、夜、明日の朝など、特定の時間帯の天気や過ごし方についてアドバイスする際に使用してください。

    引数:
    - target_datetime: ISO 8601 形式の日時文字列
      例: 2026-04-20T18:00:00+09:00

    以下の情報を返します:
    - weather:
        - condition: 指定日時に近い時間の天気
        - temperature_c: 指定日時に近い時間の外気温
        - humidity: 指定日時に近い時間の外気湿度
        - temp_max_c: その日の最高気温
        - temp_min_c: その日の最低気温
    - season_context:
        - season: summer / winter / other
        - month: 対象日時の月
    - health_alerts:
        - heat_risk: 熱中症対策が必要か
        - dryness_risk: 乾燥対策が必要か
    """
    return get_weather_context(target_datetime=target_datetime)


if __name__ == "__main__":
    mcp.run()
