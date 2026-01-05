from nonebot import require
require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as localstore
from pathlib import Path
from pydantic import BaseModel, Field

class Config(BaseModel):
    sign_in_data_path: Path = Field(
        default_factory=lambda: localstore.get_plugin_data_file("user_data.json")
    )
    hitokoto_api_url: str = "http://127.0.0.1:4399/v2/hitokoto"
    hitokoto_backup_api_url: str = "https://60s.viki.moe/v2/hitokoto"
    
    # 好感度等级定义
    # (阈值, 等级名称)
    favorability_levels: list[tuple[float, str]] = [
        (0.0, "初见"),
        (25.0, "面熟"),
        (50.0, "初识"),
        (75.0, "普通"),
        (100.0, "熟悉"),
        (125.0, "信赖"),
        (150.0, "知心"),
        (175.0, "深厚"),
        (200.0, "挚友"),
        (225.0, "亲密"),
    ]

def get_level_name(favorability: float) -> str:
    """根据好感度获取等级名称"""
    level_name = "陌生"
    for threshold, name in Config().favorability_levels:
        if favorability >= threshold:
            level_name = name
        else:
            break
    return level_name
