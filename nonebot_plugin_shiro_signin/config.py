from nonebot import get_plugin_config
from pydantic import BaseModel

class Config(BaseModel):
    hitokoto_api_url: str = "https://v1.hitokoto.cn"
    hitokoto_backup_api_url: str = "https://international.v1.hitokoto.cn"
    
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
    
    # 金币等级定义
    # (阈值, 等级名称)
    coin_levels: list[tuple[int, str]] = [
        (0, "囊中羞涩"),
        (100, "初有资产"),
        (300, "小有积蓄"),
        (500, "财源广进"),
        (1000, "商贾之才"),
        (2000, "腰缠万贯"),
        (5000, "金玉满堂"),
        (10000, "富甲一方"),
        (50000, "富可敌国"),
    ]

config = get_plugin_config(Config)

def get_level_name(favorability: float) -> str:
    """根据好感度获取等级名称"""
    level_name = "陌生"
    for threshold, name in config.favorability_levels:
        if favorability >= threshold:
            level_name = name
        else:
            break
    return level_name

def get_coin_level_name(coins: int) -> str:
    """根据金币数量获取等级名称"""
    level_name = "一贫如洗"
    for threshold, name in config.coin_levels:
        if coins >= threshold:
            level_name = name
        else:
            break
    return level_name
