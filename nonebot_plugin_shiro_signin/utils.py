import json
import os
import httpx
from pathlib import Path
import nonebot_plugin_localstore as localstore
from .config import config

DATA_PATH = localstore.get_plugin_data_file("user_data.json")

async def get_hitokoto() -> tuple[str, str]:
    """获取一言 (尝试主 API 和备用 API)"""
    async with httpx.AsyncClient() as client:
        # 尝试主 API
        try:
            response = await client.get(config.hitokoto_api_url, timeout=3.0)
            if response.status_code == 200:
                data = response.json()
                return data.get('hitokoto', '生活原本沉闷，但跑起来就有风。'), data.get('from', '网络')
        except Exception:
            pass
        
        # 尝试备用 API
        try:
            response = await client.get(config.hitokoto_backup_api_url, timeout=3.0)
            if response.status_code == 200:
                data = response.json()
                # 备用 API 格式: {"data": {"hitokoto": "..."}}
                if "data" in data and isinstance(data["data"], dict):
                    return data["data"].get("hitokoto", "生活原本沉闷，但跑起来就有风。"), "网络"
        except Exception:
            pass
            
    return "生活原本沉闷，但跑起来就有风。", "网络"

def load_data() -> dict:
    """加载用户数据"""
    if not DATA_PATH.exists():
        return {}
    try:
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data: dict):
    """保存用户数据"""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user_data(user_id: str) -> dict:
    """获取单个用户或群聊的数据"""
    data = load_data()
    # 如果是群聊 ID (通常以 group_ 开头或纯数字)，提供不同的默认值
    default = {
        "favorability": 0.0, 
        "last_sign_in": "", 
        "first_sign_in": "",
        "action_points": 0, 
        "coins": 0, 
        "inventory": [],
        "total_sign_ins": 0,
        "achievements": [],
        "blacklist_count": 0,
        "is_perm_blacklisted": False,
        "nickname": "",
        "last_work_time": "",
        "remaining_works": 1,
        "custom_title": "",     # 自定义头衔
        "bank_coins": 0,        # 银行存款
        "last_rob_time": 0,      # 上次抢劫时间 (timestamp)
        "achievement_progress": {"red_packet_total": 0, "steal_success": 0, "consecutive_fails": 0}
    }
    if user_id.startswith("group_"):
        default = {"favorability": 100.0, "daily_fav_count": 0.0, "last_update": ""}
    
    # 兼容旧数据，补齐缺失字段
    if user_id in data and not user_id.startswith("group_"):
        changed = False
        # 批量检查并设置默认值
        for key, value in default.items():
            if key not in data[user_id]:
                data[user_id][key] = value
                changed = True
        
        if changed:
            save_data(data)
            
    return data.get(user_id, default)

def update_user_data(user_id: str, **kwargs):
    """更新单个用户或群聊的数据"""
    data = load_data()
    if user_id not in data:
        # 获取默认值并根据 kwargs 更新
        user_data = get_user_data(user_id)
        data[user_id] = user_data
    
    for key, value in kwargs.items():
        if value is not None:
            data[user_id][key] = value
            
    save_data(data)
