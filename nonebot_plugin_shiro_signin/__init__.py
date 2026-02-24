import random
import time
import uuid
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from nonebot import on_command, get_driver, get_plugin_config, require, get_bot, logger, on_notice
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent, Message, MessageSegment, PokeNotifyEvent
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from nonebot.permission import SUPERUSER

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as localstore
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_htmlrender import html_to_pic

from .config import Config, get_level_name, get_coin_level_name
from .utils import get_user_data, update_user_data, get_hitokoto, load_data, save_data

TEMPLATES_PATH = Path(__file__).parent / "templates"

__plugin_meta__ = PluginMetadata(
    name="shiro签到",
    description="支持签到、好感度查询、商店、红包、银行等系统的综合签到插件",
    usage="""基础功能：
签到: 每日签到获取金币/好感度/行动值
查询好感度: 查看个人信息卡片
好感度排行: 查看群内好感度排名
商店: 购买道具
背包: 查看持有道具
使用 <道具名>: 使用道具
打工: 消耗打工次数赚取金币
行动: 消耗行动值增加好感度
发红包 <金额> <数量>: 发送拼手气红包
发世界红包 <金额> <数量>: 发送全服红包
抢红包: 领取红包
偷窃 <@某人>: 消耗1行动值尝试偷窃金币（慎用！）
银行 [存/取] <金额>: 存取金币赚利息
改名 <新称号>: 使用改名卡修改称号
转账 <@某人> <金额>: 给群友转账
富豪榜: 查看金币排行榜
决斗 <@某人>: 消耗2行动值发起PK
掷骰子 [赌注]: 与真寻比大小赚金币
买彩票: 20金币一张，次日开奖
彩票池: 查看彩票奖池信息""",
    config=Config,
)

config = get_plugin_config(Config)
superusers = get_driver().config.superusers

# 数据路径
RED_PACKET_DATA_FILE = localstore.get_plugin_data_file("active_red_packets.json")
BLACKLIST_FILE = localstore.get_plugin_data_file("red_packet_blacklist.json")
LOTTERY_DATA_FILE = localstore.get_plugin_data_file("lottery_data.json")

# 匹配器定义
sign_in = on_command("签到", priority=5, block=True)
favorability_rank = on_command("好感度排行", aliases={"好感度榜", "排行榜"}, priority=5, block=True)
query_favorability = on_command("查询好感度", aliases={"好感度", "我的好感度", "个人信息"}, priority=5, block=True)
set_favorability = on_command("设置好感度", priority=5, block=True)
set_coins = on_command("设置金币", priority=5, block=True)
set_ap = on_command("设置行动值", priority=5, block=True)
take_action = on_command("行动", aliases={"进行行动", "互动"}, priority=5, block=True)
open_shop = on_command("商店", aliases={"绪山商店", "绪山百货"}, priority=5, block=True)
buy_item = on_command("购买", priority=5, block=True)
use_item = on_command("使用", aliases={"使用道具", "吃", "穿", "玩"}, priority=5, block=True)
view_inventory = on_command("背包", aliases={"我的背包", "仓库"}, priority=5, block=True)
do_work = on_command("打工", aliases={"工", "上班"}, priority=5, block=True)

# 新增功能
send_red_packet = on_command("发红包", priority=5, block=True)
send_global_red_packet = on_command("发世界红包", priority=5, block=True)
grab_red_packet = on_command("抢红包", priority=5, block=True)
rob_user = on_command("偷窃", aliases={"抢劫", "偷"}, priority=5, block=True)
bank_cmd = on_command("银行", aliases={"真寻银行"}, priority=5, block=True)
rename_card = on_command("改名", aliases={"修改称号", "设置称号"}, priority=5, block=True)

# 红包黑名单指令
add_red_packet_blacklist = on_command("添加红包黑名单", priority=5, block=True)
remove_red_packet_blacklist = on_command("移除红包黑名单", priority=5, block=True)
view_red_packet_blacklist = on_command("红包黑名单", priority=5, block=True)

# 新增功能指令
transfer_coins = on_command("转账", priority=5, block=True)
wealth_rank = on_command("富豪榜", aliases={"金币榜", "富豪排行"}, priority=5, block=True)
duel_user = on_command("决斗", aliases={"PK", "挑战"}, priority=5, block=True)
play_dice = on_command("掷骰子", aliases={"摇骰子", "比大小"}, priority=5, block=True)
buy_lottery = on_command("买彩票", priority=5, block=True)
lottery_info = on_command("彩票池", aliases={"奖池"}, priority=5, block=True)

def load_red_packets():
    """加载活跃红包数据"""
    if not RED_PACKET_DATA_FILE.exists():
        return {}
    try:
        with open(RED_PACKET_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 转换时间字符串为 datetime 对象
            for pid, packet in data.items():
                if "create_time" in packet:
                    try:
                        packet["create_time"] = datetime.fromisoformat(packet["create_time"])
                    except:
                        packet["create_time"] = datetime.now()
            return data
    except Exception as e:
        logger.error(f"加载红包数据失败: {e}")
        return {}

def save_red_packets():
    """保存活跃红包数据"""
    RED_PACKET_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        # 复制数据以避免修改原始数据
        data_to_save = {}
        for pid, packet in active_red_packets.items():
            packet_copy = packet.copy()
            # 转换 datetime 对象为 ISO 格式字符串
            if "create_time" in packet_copy and isinstance(packet_copy["create_time"], datetime):
                packet_copy["create_time"] = packet_copy["create_time"].isoformat()
            data_to_save[pid] = packet_copy
            
        with open(RED_PACKET_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"保存红包数据失败: {e}")

# 全局变量
active_red_packets = load_red_packets()

def load_blacklist():
    if not BLACKLIST_FILE.exists():
        return []
    try:
        with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_blacklist(blacklist):
    BLACKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(blacklist, f, ensure_ascii=False, indent=4)

# 红包黑名单群组
GLOBAL_RED_PACKET_BLACKLIST = load_blacklist()

# 运势定义
FORTUNES = {
    "大吉": {"work_rate": 1.3, "steal_rate": 0.15, "desc": "运势极佳，诸事顺遂！"},
    "中吉": {"work_rate": 1.2, "steal_rate": 0.08, "desc": "运势不错，是个好兆头。"},
    "小吉": {"work_rate": 1.1, "steal_rate": 0.03, "desc": "平平淡淡才是真。"},
    "吉": {"work_rate": 1.0, "steal_rate": 0.0, "desc": "不好不坏，努力会有回报。"},
    "末吉": {"work_rate": 0.95, "steal_rate": -0.03, "desc": "运气稍差，小心行事。"},
    "凶": {"work_rate": 0.9, "steal_rate": -0.08, "desc": "诸事不宜，最好在家休息。"},
    "大凶": {"work_rate": 0.8, "steal_rate": -0.15, "desc": "...今天还是别出门了吧。"}
}

def load_lottery_data():
    if not LOTTERY_DATA_FILE.exists():
        return {"pool": 0, "participants": []}
    try:
        with open(LOTTERY_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"pool": 0, "participants": []}

def save_lottery_data(data):
    LOTTERY_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOTTERY_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 隐藏成就定义
HIDDEN_ACHIEVEMENTS = [
    {"id": "philanthropist", "name": "慈善家", "condition": lambda u: u["achievement_progress"]["red_packet_total"] >= 10000, "reward_coins": 1000, "desc": "累计发红包超过 10,000 金币"},
    {"id": "phantom_thief", "name": "怪盗基德", "condition": lambda u: u["achievement_progress"]["steal_success"] >= 50, "reward_coins": 2000, "desc": "累计成功偷窃 50 次"},
    {"id": "bad_luck", "name": "非酋", "condition": lambda u: u["achievement_progress"]["consecutive_fails"] >= 3, "reward_coins": 500, "desc": "连续 3 次打工收益最低或偷窃失败"}
]

async def check_hidden_achievements(bot: Bot, event: MessageEvent, user_id: str):
    """检查并发放隐藏成就"""
    user_data = get_user_data(user_id)
    achievements = user_data.get("achievements", [])
    
    new_achievements = []
    for ach in HIDDEN_ACHIEVEMENTS:
        if ach["id"] not in achievements:
            try:
                if ach["condition"](user_data):
                    achievements.append(ach["id"])
                    new_achievements.append(ach)
                    # 发放奖励
                    user_data["coins"] += ach["reward_coins"]
            except Exception as e:
                logger.error(f"检查成就 {ach['id']} 失败: {e}")
                
    if new_achievements:
        update_user_data(user_id, achievements=achievements, coins=user_data["coins"])
        msg = "🎉 恭喜达成隐藏成就！\n"
        for ach in new_achievements:
            msg += f"【{ach['name']}】: {ach['desc']} (奖励 {ach['reward_coins']} 金币)\n"
        await bot.send(event, msg)

@add_red_packet_blacklist.handle()
async def handle_add_blacklist(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not str(event.user_id) in superusers:
        await add_red_packet_blacklist.finish("只有管理员才能操作哦！")
        
    group_id = args.extract_plain_text().strip()
    if not group_id:
        if isinstance(event, GroupMessageEvent):
            group_id = str(event.group_id)
        else:
            await add_red_packet_blacklist.finish("请输入群号！")
            
    if group_id in GLOBAL_RED_PACKET_BLACKLIST:
        await add_red_packet_blacklist.finish("这个群已经在黑名单里啦！")
        
    GLOBAL_RED_PACKET_BLACKLIST.append(group_id)
    save_blacklist(GLOBAL_RED_PACKET_BLACKLIST)
    await add_red_packet_blacklist.finish(f"已将群 {group_id} 加入红包黑名单！")

@remove_red_packet_blacklist.handle()
async def handle_remove_blacklist(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not str(event.user_id) in superusers:
        await remove_red_packet_blacklist.finish("只有管理员才能操作哦！")
        
    group_id = args.extract_plain_text().strip()
    if not group_id:
        if isinstance(event, GroupMessageEvent):
            group_id = str(event.group_id)
        else:
            await remove_red_packet_blacklist.finish("请输入群号！")
            
    if group_id not in GLOBAL_RED_PACKET_BLACKLIST:
        await remove_red_packet_blacklist.finish("这个群不在黑名单里哦！")
        
    GLOBAL_RED_PACKET_BLACKLIST.remove(group_id)
    save_blacklist(GLOBAL_RED_PACKET_BLACKLIST)
    await remove_red_packet_blacklist.finish(f"已将群 {group_id} 移出红包黑名单！")

@view_red_packet_blacklist.handle()
async def handle_view_blacklist(bot: Bot, event: MessageEvent):
    if not str(event.user_id) in superusers:
        await view_red_packet_blacklist.finish("只有管理员才能操作哦！")
        
    if not GLOBAL_RED_PACKET_BLACKLIST:
        await view_red_packet_blacklist.finish("当前没有红包黑名单群组。")
        
    msg = "当前红包黑名单群组：\n" + "\n".join(GLOBAL_RED_PACKET_BLACKLIST)
    await view_red_packet_blacklist.finish(msg)


@scheduler.scheduled_job("cron", hour=0, minute=0, id="sign_in_daily_reset")
async def reset_daily_works():
    """每日重置打工次数"""
    try:
        data = load_data()
        count = 0
        for user_id in data:
            if not user_id.startswith("group_"):
                # 重置打工次数为 1 (默认值)
                data[user_id]["remaining_works"] = 1
                count += 1
        save_data(data)
        logger.info(f"已重置 {count} 名用户的每日打工次数")
    except Exception as e:
        logger.error(f"重置每日打工次数失败: {e}")

@scheduler.scheduled_job("interval", minutes=30)
async def check_expired_red_packets():
    """定期检查过期红包并退回"""
    now = datetime.now()
    expired_packets = []
    
    # 转换为list以避免迭代时修改字典大小
    for pid, packet in list(active_red_packets.items()):
        # 默认24小时过期
        create_time = packet.get("create_time")
        if not create_time:
            # 兼容旧数据，如果没有create_time，视为不过期或补上当前时间
            packet["create_time"] = now
            continue
            
        if now - create_time > timedelta(hours=24):
            expired_packets.append(pid)
            
    if expired_packets:
        for pid in expired_packets:
            if pid in active_red_packets:
                packet = active_red_packets[pid]
                sender_id = packet["sender_id"]
                remain_amount = packet["remain_amount"]
                
                if remain_amount > 0:
                    user_data = get_user_data(sender_id)
                    update_user_data(sender_id, coins=user_data.get("coins", 0) + remain_amount)
                    
                del active_red_packets[pid]
                
        save_red_packets()
        logger.info(f"已清理 {len(expired_packets)} 个过期红包")

# 启动时清理一次
try:
    # 延迟10秒执行，确保scheduler已启动
    scheduler.add_job(check_expired_red_packets, "date", run_date=datetime.now() + timedelta(seconds=10))
except Exception:
    # 忽略可能的scheduler未启动错误
    pass

# 《别当欧尼酱了》参考行动 - 基于时间段
ONIMAI_ACTIONS = {
    "late_night": [  # 00:00 - 05:00
        "和真寻酱在深夜偷偷联机打游戏（真寻酱：再玩一局，最后一局！）",
        "发现真寻酱在厨房偷吃深夜宵夜（真寻酱：呜哇！被发现了！）",
        "真寻酱在电脑前打瞌睡，头一点一点的（要把她抱到床上去吗？）",
        "陪真寻酱看深夜动画（真寻酱兴奋地讲解着剧情）",
        "真寻酱因为熬夜太晚，黑眼圈都出来了（被美波里训斥了呢）"
    ],
    "morning": [     # 05:00 - 09:00
        "试图叫醒赖床的真寻酱（真寻酱：再让我睡5分钟...就5分钟...）",
        "真寻酱睡眼惺忪地刷牙，头发乱蓬蓬的（像一只小猫一样呢）",
        "和真寻酱一起吃早餐（真寻酱似乎还没完全清醒）",
        "帮真寻酱梳头（真寻酱害羞地低下了头）",
        "真寻酱在玄关手忙脚乱地穿鞋（要迟到了要迟到了！）"
    ],
    "daytime": [     # 09:00 - 18:00
        "和真寻一起玩游戏（真寻酱似乎有点不服输呢）",
        "尝试美波里特制的“奇怪饮料”（感觉身体轻飘飘的...）",
        "被美波里强行换上女装（真寻酱：为什么我也要穿啊！）",
        "去商店街买可丽饼（真寻酱吃得满嘴都是奶油）",
        "辅导真寻酱写作业（真寻酱在草稿纸上画小人）",
        "和真寻酱一起买衣服（真寻酱在试衣间磨磨蹭蹭）",
        "一起喝下午茶（真寻酱对草莓蛋糕完全没有抵抗力）",
        "看真寻酱努力练习女子力的样子（真是个努力的好孩子呢）",
        "和真寻酱一起去游戏中心（真寻酱在抓娃娃机前大显身手）"
    ],
    "evening": [     # 18:00 - 24:00
        "一起去洗澡（真寻酱：哇啊啊不要看过来！）",
        "和真寻酱一起看晚间电视（真寻酱被电视里的内容逗得哈哈大笑）",
        "帮真寻酱吹头发（真寻酱舒服得快要睡着了）",
        "真寻酱穿上了宽松的睡衣（真寻酱：这个睡衣...是不是有点太大了？）",
        "和真寻酱商量明天的计划（真寻酱一脸期待的样子）",
        "和真寻酱一起睡午觉（真寻酱的睡颜真可爱呢）",
        "真寻酱在被窝里玩手机被抓住了（真寻酱：这就关机，这就关机！）"
    ]
}

ONIMAI_WORKS = [
    "在波特罗的咖啡店帮忙（真寻酱：欢迎光临！诶，不要一直盯着我看啦...）",
    "帮美波里整理实验数据（虽然完全看不懂，但还是努力帮忙了）",
    "作为美波里的素描模特（真寻酱：这、这种姿势太羞耻了！）",
    "帮忙打扫家里的卫生（真寻酱拿着鸡毛掸子到处跑）",
    "去便利店跑腿买东西（真寻酱：嘿嘿，顺便给自己买了布丁）",
    "在学校帮忙整理图书（真寻酱踮起脚尖放书的样子真可爱）",
    "帮美波里测试新发明的...游戏机？（真寻酱玩得不亦乐乎）",
    "帮忙照顾邻居家的宠物（真寻酱被大狗舔得满脸口水）",
    "在祭典摊位上帮忙（真寻酱穿着浴衣招揽客人）",
    "帮忙修剪家里的花草（真寻酱脸上沾到了泥土）"
]

def get_action_by_time() -> str:
    """根据当前时间获取行动描述"""
    hour = datetime.now().hour
    if 0 <= hour < 5:
        category = "late_night"
    elif 5 <= hour < 9:
        category = "morning"
    elif 9 <= hour < 18:
        category = "daytime"
    else:
        category = "evening"
    
    return random.choice(ONIMAI_ACTIONS[category])

# 商店物品定义
STORE_ITEMS = {
    "1": {
        "name": "美波里的奇怪药水", 
        "price": 80, 
        "desc": "美波里研制的不知名液体，喝了会有神奇的效果？",
        "effect_desc": "增加 1-2 次打工次数",
        "type": "work",
        "value": (1, 2)
    },
    "2": {
        "name": "真寻的羞耻小裙子", 
        "price": 50, 
        "desc": "虽然很羞耻，但是穿上会被夸可爱...",
        "effect_desc": "增加 5-10 点好感度",
        "type": "fav",
        "value": (5, 10)
    },
    "3": {
        "name": "深夜的罪恶薯片", 
        "price": 15, 
        "desc": "半夜偷偷吃零食最棒了！",
        "effect_desc": "恢复 1 点行动值",
        "type": "ap",
        "value": (1, 1)
    },
    "4": {
        "name": "最新款游戏机", 
        "price": 300, 
        "desc": "为了玩最新的3A大作，必须入手！",
        "effect_desc": "增加 20-40 点好感度",
        "type": "fav",
        "value": (20, 40)
    },
    "5": {
        "name": "乃爱借给你的漫画", 
        "price": 60, 
        "desc": "乃爱强烈安利的少女漫画，意外地好看？",
        "effect_desc": "恢复 3 点行动值",
        "type": "ap",
        "value": (3, 3)
    },
    "6": {
        "name": "出门必备防晒霜", 
        "price": 40, 
        "desc": "不想被晒黑的话就涂上吧（虽然不想出门）",
        "effect_desc": "增加 5 点好感度",
        "type": "fav",
        "value": (5, 5)
    },
    "7": {
        "name": "安心感满满的运动衫",
        "price": 150,
        "desc": "还是穿这件最自在...有哥哥的味道？",
        "effect_desc": "增加 15-25 点好感度",
        "type": "fav",
        "value": (15, 25)
    },
    "8": {
        "name": "看不懂的实验报告",
        "price": 200,
        "desc": "帮美波里整理这些乱七八糟的数据...",
        "effect_desc": "增加 2-4 次打工次数",
        "type": "work",
        "value": (2, 4)
    },
    "9": {
        "name": "美波里的爱心便当",
        "price": 40,
        "desc": "营养均衡的美味便当，包含了妹妹的爱",
        "effect_desc": "恢复 2 点行动值",
        "type": "ap",
        "value": (2, 2)
    },
    "10": {
        "name": "氪金点数",
        "price": 100,
        "desc": "再抽一发！这次一定是SSR！",
        "effect_desc": "增加 10-15 点好感度",
        "type": "fav",
        "value": (10, 15)
    },
    "11": {
        "name": "时光倒流药水", 
        "price": 5, 
        "desc": "如果能回到那天...把漏掉的签到补上就好了",
        "effect_desc": "增加 1 天累计签到并增加 0-1 点好感度",
        "type": "special",
        "value": "replenish"
    },
    "12": {
        "name": "真寻的姓名贴", 
        "price": 300, 
        "desc": "贴上这个，大家就知道该怎么称呼你了",
        "effect_desc": "永久修改称号",
        "type": "special",
        "value": "rename"
    },
    "13": {
        "name": "美波里的监控摄像头", 
        "price": 100, 
        "desc": "安装在房间角落，防止有人偷偷拿走零花钱",
        "effect_desc": "抵挡一次偷窃",
        "type": "special",
        "value": "shield"
    },
    "14": {
        "name": "防盗盾",
        "price": 10,
        "desc": "坚固的盾牌，放在背包里就能生效",
        "effect_desc": "被动道具，抵挡一次偷窃（自动消耗）",
        "type": "special",
        "value": "shield"
    }
}

# 成就定义
ACHIEVEMENTS = [
    {"id": "beginner", "name": "初级哥哥", "days": 7, "reward_coins": 30, "desc": "累计签到 7 天"},
    {"id": "intermediate", "name": "合格哥哥", "days": 30, "reward_coins": 100, "desc": "累计签到 30 天"},
    {"id": "advanced", "name": "资深哥哥", "days": 100, "reward_coins": 500, "desc": "累计签到 100 天"},
    {"id": "master", "name": "最强哥哥", "days": 365, "reward_coins": 2000, "desc": "累计签到 365 天"}
]

async def render_sign_card(
    user_id: str, 
    user_name: str, 
    favorability: float, 
    inc: float = 0, 
    is_query: bool = False,
    title_override: str = None,
    action_points: int = 0,
    coins: int = 0,
    total_sign_ins: int = 0,
    first_sign_in: str = "",
    remaining_works: int = 0,
    custom_title: str = ""
) -> bytes:
    """渲染签到/好感度卡片"""
    level_name = custom_title if custom_title else get_level_name(favorability)
    coin_level_name = get_coin_level_name(coins)
    hitokoto_text, hitokoto_from = await get_hitokoto()
    avatar_url = f"http://q.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
    
    # 渲染模板
    template_path = TEMPLATES_PATH / "sign_card.html"
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 替换变量
    title = title_override or ("好感度查询" if is_query else "今日签到")
    inc_display = "none" if is_query else "block"
    stat_width = "100%" if is_query else "auto"
    time_label = "查询时间" if is_query else "签到时间"
    
    replacements = {
        "{title}": title,
        "{avatar_url}": avatar_url,
        "{user_name}": user_name,
        "{inc}": f"{inc:.2f}",
        "{new_favorability}": f"{favorability:.2f}",
        "{level_name}": level_name,
        "{coin_level_name}": coin_level_name,
        "{hitokoto_text}": hitokoto_text,
        "{hitokoto_from}": hitokoto_from,
        "{sign_time}": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "{inc_display}": inc_display,
        "{stat_width}": stat_width,
        "{time_label}": time_label,
        "{action_points}": str(action_points),
        "{coins}": str(coins),
        "{total_sign_ins}": str(total_sign_ins),
        "{first_sign_in}": first_sign_in or "未知",
        "{ap_status}": "可行动" if action_points > 0 else "休息中",
        "{coin_status}": "可购买" if coins > 0 else "积累中",
        "{remaining_works}": str(remaining_works),
        "{work_status}": "可打工" if remaining_works > 0 else "休息中"
    }
    
    for k, v in replacements.items():
        html_content = html_content.replace(k, v)
        
    return await html_to_pic(html_content, viewport={"width": 500, "height": 650})

async def render_rank_card(rank_data: list) -> bytes:
    """渲染排行榜卡片"""
    template_path = TEMPLATES_PATH / "rank_card.html"
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    items_html = ""
    for idx, user in enumerate(rank_data, 1):
        avatar_url = f"http://q.qlogo.cn/headimg_dl?dst_uin={user['user_id']}&spec=640"
        items_html += f'''
        <div class="rank-item">
            <div class="rank-num">{idx}</div>
            <img class="user-avatar" src="{avatar_url}" alt="avatar">
            <div class="user-info">
                <div class="user-name">{user['nickname']}</div>
                <div class="user-detail">ID: {user['user_id']}</div>
            </div>
            <div class="coin-info">
                <div class="coin-value">💰 {user['coins']}</div>
            </div>
            <div class="fav-info">
                <div class="fav-value">{user['favorability']:.1f}</div>
                <div class="level-badge">{user['level_name']}</div>
            </div>
        </div>
        '''
    
    html_content = html_content.replace("{rank_items}", items_html)
    html_content = html_content.replace("{update_time}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    # 动态高度：基础高度 + 每个条目高度
    height = 150 + len(rank_data) * 80
    return await html_to_pic(html_content, viewport={"width": 500, "height": height})

async def render_shop_card(coins: int) -> bytes:
    """渲染商店卡片"""
    template_path = TEMPLATES_PATH / "shop_card.html"
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    items_html = ""
    for item_id, item in STORE_ITEMS.items():
        items_html += f'''
        <div class="item-card">
            <div class="item-info">
                <div class="item-header">
                    <span class="item-id">{item_id}</span>
                    <span class="item-name">{item["name"]}</span>
                </div>
                <div class="item-effect">✨ {item["effect_desc"]}</div>
                <div class="item-desc">{item["desc"]}</div>
            </div>
            <div class="item-price">💰 {item["price"]}</div>
        </div>
        '''
    
    html_content = html_content.replace("{coins}", str(coins))
    html_content = html_content.replace("{items_html}", items_html)
    
    return await html_to_pic(html_content, viewport={"width": 500, "height": 1200})

async def render_inventory_card(user_id: str, user_name: str, coins: int, inventory: list) -> bytes:
    """渲染背包卡片"""
    template_path = TEMPLATES_PATH / "inventory_card.html"
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    # 统计数量
    item_counts = {}
    for item in inventory:
        item_counts[item] = item_counts.get(item, 0) + 1
        
    items_html = ""
    if not item_counts:
        items_html = '<div class="empty-tips">背包里空空如也呢...<br>去美波里的商店买点东西吧？</div>'
    else:
        for item_name, count in item_counts.items():
            # 查找详细信息
            item_info = None
            for si in STORE_ITEMS.values():
                if si["name"] == item_name:
                    item_info = si
                    break
            
            desc = "未知物品"
            effect = "未知效果"
            if item_info:
                desc = item_info["desc"]
                effect = item_info["effect_desc"]
                
            items_html += f'''
            <div class="item-card">
                <div class="item-info">
                    <div class="item-header">
                        <span class="item-name">{item_name}</span>
                        <span class="item-count">x{count}</span>
                    </div>
                    <div class="item-effect">✨ {effect}</div>
                    <div class="item-desc">{desc}</div>
                </div>
            </div>
            '''
            
    avatar_url = f"http://q.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
    
    replacements = {
        "{avatar_url}": avatar_url,
        "{user_name}": user_name,
        "{coins}": str(coins),
        "{items_html}": items_html
    }
    
    for k, v in replacements.items():
        html_content = html_content.replace(k, v)
        
    # 动态高度
    height = 300 + len(item_counts) * 80 if item_counts else 400
    return await html_to_pic(html_content, viewport={"width": 500, "height": height})

async def render_work_card(
    user_id: str,
    user_name: str,
    coins: int,
    earned_coins: int,
    work_desc: str,
    remaining_works: int
) -> bytes:
    """渲染打工结果卡片"""
    coin_level_name = get_coin_level_name(coins)
    avatar_url = f"http://q.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"
    
    template_path = TEMPLATES_PATH / "work_card.html"
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    replacements = {
        "{avatar_url}": avatar_url,
        "{user_name}": user_name,
        "{work_desc}": work_desc,
        "{earned_coins}": str(earned_coins),
        "{coins}": str(coins),
        "{coin_level_name}": coin_level_name,
        "{remaining_works}": str(remaining_works),
        "{work_status}": "可打工" if remaining_works > 0 else "休息中",
        "{sign_time}": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    for k, v in replacements.items():
        html_content = html_content.replace(k, v)
        
    return await html_to_pic(html_content, viewport={"width": 500, "height": 600})

@favorability_rank.handle()
async def handle_rank(bot: Bot, event: MessageEvent):
    all_data = load_data()
    rank_list = []
    for user_id, user_data in all_data.items():
        # 过滤群聊数据和其他非用户数据
        if user_id.startswith("group_"):
            continue
            
        if user_data.get("is_perm_blacklisted"):
            continue
        fav = user_data.get("favorability", 0)
        if fav <= 0:
            continue
        
        # 优先使用存储的昵称，如果没有则暂时使用 ID
        nickname = user_data.get("nickname", "")
        if not nickname:
            nickname = user_id
            
        rank_list.append({
            "user_id": user_id,
            "nickname": nickname,
            "favorability": fav,
            "coins": user_data.get("coins", 0),
            "level_name": get_level_name(fav)
        })
    
    rank_list.sort(key=lambda x: x["favorability"], reverse=True)
    rank_data = rank_list[:15]
    
    # 尝试补全昵称
    for user in rank_data:
        # 如果昵称是 ID 或者为空，尝试获取
        if user["nickname"] == user["user_id"] or not user["nickname"]:
            name = ""
            
            # 优先尝试获取陌生人信息 (QQ昵称)
            try:
                info = await bot.get_stranger_info(user_id=int(user["user_id"]))
                name = info.get("nickname")
            except Exception:
                pass

            # 如果获取失败，且在群内，尝试获取群成员信息 (取 nickname 而非 card)
            if not name and isinstance(event, GroupMessageEvent):
                try:
                    info = await bot.get_group_member_info(group_id=event.group_id, user_id=int(user["user_id"]))
                    name = info.get("nickname")
                except Exception:
                    pass
            
            if name:
                user["nickname"] = name
                # 顺便更新数据库
                update_user_data(user["user_id"], nickname=name)
    
    if not rank_data:
        await favorability_rank.finish("暂时没有排行数据~")
        
    pic = await render_rank_card(rank_data)
    await favorability_rank.finish(MessageSegment.image(pic))

@sign_in.handle()
async def handle_sign_in(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    # 黑名单检查
    if user_data.get("is_perm_blacklisted"):
        await sign_in.finish(MessageSegment.at(user_id) + " 美波里说坏孩子不能签到哦！(已被永久拉黑)")
        
    user_name = event.sender.nickname or user_id
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 检查是否跨天，如果是新的一天则重置行动值
    last_sign_in = user_data.get("last_sign_in", "")
    first_sign_in = user_data.get("first_sign_in", "")
    current_ap = user_data.get("action_points", 0)
    total_sign_ins = user_data.get("total_sign_ins", 0)
    
    # 记录第一次签到时间
    if not first_sign_in:
        first_sign_in = today
    
    if last_sign_in != today:
        current_ap = 0  # 每日清空行动值
        # 每日重置打工次数为 1
        user_data["remaining_works"] = 1
    
    if last_sign_in == today:
        # 重复签到，提示并发送图片
        pic = await render_sign_card(
            user_id, user_name, user_data["favorability"], 
            is_query=True, title_override="今日已签到",
            action_points=current_ap,
            coins=user_data.get("coins", 0),
            total_sign_ins=total_sign_ins,
            remaining_works=user_data.get("remaining_works", 1)
        )
        
        # 获取今日运势
        fortune = user_data.get("fortune", {})
        fortune_str = ""
        if fortune and fortune.get("date") == today:
            fortune_str = f"\n今日运势: {fortune.get('type')} ({fortune.get('desc')})"
            
        await sign_in.finish(MessageSegment.at(user_id) + f" 哥哥今天已经签到过啦！明天再来吧~{fortune_str}\n首次签到: {first_sign_in}\n累计签到: {total_sign_ins}天\n当前行动值: {current_ap}\n商店金币: {user_data.get('coins', 0)}\n发送“行动”或“商店”看看吧~" + MessageSegment.image(pic))
    
    # 随机运势
    fortune_type = random.choice(list(FORTUNES.keys()))
    fortune_data = FORTUNES[fortune_type]
    fortune_info = {
        "type": fortune_type,
        "desc": fortune_data["desc"],
        "date": today
    }
    
    # 随机增加 0-1 的好感度
    inc = round(random.uniform(0, 1), 2)
    new_favorability = round(float(user_data["favorability"]) + inc, 2)
    
    # 奖励：行动值 +1（从0开始），金币 +0-5
    new_ap = 1  # 签到获得今日的 1 点行动值
    
    current_coins = user_data.get("coins", 0)
    coin_inc = random.randint(0, 5)
    
    # 更新总签到天数
    new_total_sign_ins = total_sign_ins + 1
    
    # 检查成就
    new_achievements = []
    earned_achievements = user_data.get("achievements", [])
    achievement_msg = ""
    
    for ach in ACHIEVEMENTS:
        if new_total_sign_ins >= ach["days"] and ach["id"] not in earned_achievements:
            earned_achievements.append(ach["id"])
            new_achievements.append(ach)
            coin_inc += ach["reward_coins"]
            achievement_msg += f"\n🏆 解锁成就：【{ach['name']}】奖励 {ach['reward_coins']} 金币！"
    
    new_coins = current_coins + coin_inc
    
    # 更新数据
    update_user_data(
        user_id, 
        favorability=new_favorability, 
        last_sign_in=today, 
        first_sign_in=first_sign_in,
        action_points=new_ap, 
        coins=new_coins,
        total_sign_ins=new_total_sign_ins,
        achievements=earned_achievements,
        nickname=user_name,
        fortune=fortune_info
    )
    
    # 渲染图片
    pic = await render_sign_card(
        user_id, user_name, new_favorability, 
        inc=inc, action_points=new_ap, coins=new_coins,
        total_sign_ins=new_total_sign_ins,
        first_sign_in=first_sign_in,
        remaining_works=user_data.get("remaining_works", 1),
        custom_title=user_data.get("custom_title", "")
    )
    
    # 自动点赞 (尝试点赞 10 次)
    try:
        await bot.send_like(user_id=int(user_id), times=10)
    except Exception as e:
        # 点赞失败不影响签到流程
        pass

    await sign_in.finish(
        MessageSegment.at(user_id) + f" 签到成功！哥哥今天也要元气满满哦！{achievement_msg}\n今日运势: {fortune_type} ({fortune_data['desc']})\n奖励：1点行动值 & {coin_inc}金币。\n累计签到: {new_total_sign_ins}天\n首次签到: {first_sign_in}\n好感度 +{inc:.2f}，当前总好感度: {new_favorability:.2f}\n当前金币: {new_coins}\n发送“商店”可以购买商品，“行动”可消耗行动值增加好感度~" + 
        MessageSegment.image(pic)
    )

@query_favorability.handle()
async def handle_query(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    # 黑名单检查
    if user_data.get("is_perm_blacklisted"):
        await query_favorability.finish(MessageSegment.at(user_id) + " 美波里说坏孩子不能看个人信息哦！")
        
    user_name = event.sender.nickname or user_id
    
    # 渲染图片
    pic = await render_sign_card(
        user_id, user_name, user_data["favorability"], 
        is_query=True, action_points=user_data.get("action_points", 0),
        coins=user_data.get("coins", 0),
        total_sign_ins=user_data.get("total_sign_ins", 0),
        first_sign_in=user_data.get("first_sign_in", ""),
        remaining_works=user_data.get("remaining_works", 1),
        custom_title=user_data.get("custom_title", "")
    )
    
    await query_favorability.finish(MessageSegment.image(pic))

@take_action.handle()
async def handle_action(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    # 黑名单检查
    if user_data.get("is_perm_blacklisted"):
        await take_action.finish(MessageSegment.at(user_id) + " 美波里说坏孩子不能和真寻互动哦！")
        
    user_name = event.sender.nickname or user_id
    current_ap = user_data.get("action_points", 0)
    
    if current_ap <= 0:
        await take_action.finish(MessageSegment.at(user_id) + " 累了嘛？行动值不足啦，明天签到恢复哦！")
    
    # 随机行动描述 (基于当前时间)
    action_desc = get_action_by_time()
    # 随机增加 0-1 的好感度
    inc = round(random.uniform(0, 1), 2)
    new_favorability = round(float(user_data["favorability"]) + inc, 2)
    new_ap = current_ap - 1
    
    # 更新数据
    update_user_data(user_id, favorability=new_favorability, action_points=new_ap)
    
    # 渲染卡片
    pic = await render_sign_card(
        user_id, user_name, new_favorability, 
        inc=inc, title_override="进行行动",
        action_points=new_ap,
        coins=user_data.get("coins", 0),
        total_sign_ins=user_data.get("total_sign_ins", 0),
        first_sign_in=user_data.get("first_sign_in", ""),
        remaining_works=user_data.get("remaining_works", 1),
        custom_title=user_data.get("custom_title", "")
    )
    
    await take_action.finish(
        MessageSegment.at(user_id) + f" 互动时间：{action_desc}\n好感度 +{inc:.2f}！\n当前好感度: {new_favorability:.2f}\n剩余行动值: {new_ap}" + 
        MessageSegment.image(pic)
    )

@open_shop.handle()
async def handle_shop(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    # 黑名单检查
    if user_data.get("is_perm_blacklisted"):
        await open_shop.finish(MessageSegment.at(user_id) + " 美波里说坏孩子不能进商店哦！")
        
    coins = user_data.get('coins', 0)
    
    # 渲染图片
    pic = await render_shop_card(coins)
    
    await open_shop.finish(MessageSegment.image(pic))

@buy_item.handle()
async def handle_buy(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    # 黑名单检查
    if user_data.get("is_perm_blacklisted"):
        await buy_item.finish(MessageSegment.at(user_id) + " 你已被列入永久黑名单，禁止购买商品。")
        
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await buy_item.finish("请输入要购买的商品编号哦，例如：购买 1，或者批量购买：购买 1 10")

    parts = args_text.split()
    item_id = parts[0]
    count = 1
    
    if len(parts) > 1:
        try:
            # 尝试解析第二个参数为数量
            val = int(parts[1])
            if val > 0:
                count = val
        except ValueError:
            pass
            
    # 智能识别: 如果第一个参数是数字且不在商品列表，但第二个参数在商品列表，则交换
    # (例如用户输入了 "购买 10 1" 意为买10个1号商品)
    if item_id not in STORE_ITEMS and len(parts) > 1 and parts[1] in STORE_ITEMS:
        try:
            c = int(parts[0])
            if c > 0:
                count = c
                item_id = parts[1]
        except:
            pass

    if item_id not in STORE_ITEMS:
        await buy_item.finish("这个商品编号好像不存在呢...")
        
    item = STORE_ITEMS[item_id]
    total_price = item["price"] * count
    
    if user_data.get("coins", 0) < total_price:
        await buy_item.finish(f"金币不足哦！购买 {count} 个 {item['name']} 需要 {total_price} 金币，你只有 {user_data.get('coins', 0)} 金币。")
        
    # 扣钱并添加进背包
    new_coins = user_data["coins"] - total_price
    inventory = user_data.get("inventory", [])
    
    # 批量添加
    inventory.extend([item["name"]] * count)
    
    update_user_data(user_id, coins=new_coins, inventory=inventory)
    
    await buy_item.finish(f"🛍️ 购买成功！你花费 {total_price} 金币购买了 {count} 个【{item['name']}】。\n效果: {item['effect_desc']}\n发送“使用 {item['name']}”即可生效哦！")

@use_item.handle()
async def handle_use(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    # 黑名单检查
    if user_data.get("is_perm_blacklisted"):
        await use_item.finish(MessageSegment.at(user_id) + " 你已被列入永久黑名单，禁止使用道具。")
        
    args_text = args.extract_plain_text().strip()
    
    if not args_text:
        await use_item.finish("你想使用哪个道具呢？请在指令后面加上道具名称哦，例如：使用 真寻酱的薯片")
    
    parts = args_text.split()
    item_name = parts[0]
    count = 1
    
    # 尝试解析数量
    if len(parts) > 1:
        try:
            val = int(parts[1])
            if val > 0:
                count = val
        except ValueError:
            # 可能是道具名包含空格？暂不支持含空格的道具名+数量，除非倒序。
            # 这里简单处理：如果第二个参数是数字，就当作数量
            pass
            
    # 如果第一个参数是数量（数字），第二个是道具名
    if item_name.isdigit() and len(parts) > 1:
        try:
            c = int(item_name)
            if c > 0:
                count = c
                item_name = parts[1] # 假设道具名没有空格
        except:
            pass
        
    inventory = user_data.get("inventory", [])
    
    # 统计背包中该道具的数量
    owned_count = inventory.count(item_name)
    
    if owned_count < count:
        if owned_count == 0:
             await use_item.finish(f"你的背包里好像没有【{item_name}】呢...")
        else:
             await use_item.finish(f"你的背包里只有 {owned_count} 个【{item_name}】，不够使用 {count} 个哦！")
        
    # 查找道具配置
    target_item = None
    for item in STORE_ITEMS.values():
        if item["name"] == item_name:
            target_item = item
            break
            
    if not target_item:
        await use_item.finish("这个道具似乎无法被直接使用呢...")
        
    # 特殊道具检查
    if target_item.get("value") == "rename":
        await use_item.finish("改名卡无需直接使用哦！请发送“改名 新称号”来使用它。\n(注意：改名会消耗一张改名卡)")
        
    if target_item.get("value") == "shield":
        await use_item.finish("防盗盾是自动生效的被动道具哦！放在背包里即可抵挡一次偷窃。\n(被偷窃时自动消耗)")

    # 消耗道具
    for _ in range(count):
        inventory.remove(item_name)
    
    # 执行效果 (批量计算)
    msg = f"✨ 批量使用了 {count} 个【{item_name}】！\n"
    
    total_inc_fav = 0.0
    total_inc_ap = 0
    total_inc_coins = 0
    total_inc_days = 0
    total_inc_work = 0
    
    new_fav = user_data.get("favorability", 0.0)
    new_ap = user_data.get("action_points", 0)
    new_total_sign_ins = user_data.get("total_sign_ins", 0)
    new_coins = user_data.get("coins", 0)
    earned_achievements = user_data.get("achievements", [])
    new_remaining_works = user_data.get("remaining_works", 1)
    
    for _ in range(count):
        if target_item["type"] == "fav":
            inc = round(random.uniform(target_item["value"][0], target_item["value"][1]), 2)
            total_inc_fav += inc
            
        elif target_item["type"] == "ap":
            inc = random.randint(target_item["value"][0], target_item["value"][1])
            total_inc_ap += inc

        elif target_item["type"] == "work":
            inc = random.randint(target_item["value"][0], target_item["value"][1])
            total_inc_work += inc
            
        elif target_item["type"] == "special" and target_item["value"] == "replenish":
            total_inc_days += 1
            inc = round(random.uniform(0, 1), 2)
            total_inc_fav += inc

    # 应用累加值
    new_fav = round(float(new_fav) + total_inc_fav, 2)
    new_ap += total_inc_ap
    new_remaining_works += total_inc_work
    
    if total_inc_days > 0:
        new_total_sign_ins += total_inc_days
        # 补签成就检查 (一次性检查最终状态)
        for ach in ACHIEVEMENTS:
            if new_total_sign_ins >= ach["days"] and ach["id"] not in earned_achievements:
                earned_achievements.append(ach["id"])
                new_coins += ach["reward_coins"]
                total_inc_coins += ach["reward_coins"]
                msg += f"\n🏆 解锁成就：【{ach['name']}】奖励 {ach['reward_coins']} 金币！"

    # 构建消息
    if total_inc_fav > 0:
        msg += f"好感度共增加了 {total_inc_fav:.2f} 点！当前: {new_fav:.2f}\n"
    if total_inc_ap > 0:
        msg += f"行动值共恢复了 {total_inc_ap} 点！当前: {new_ap}\n"
    if total_inc_work > 0:
        msg += f"打工次数共增加了 {total_inc_work} 次！当前: {new_remaining_works}\n"
    if total_inc_days > 0:
        msg += f"累计签到增加 {total_inc_days} 天！当前: {new_total_sign_ins} 天\n"
        
    new_coins += total_inc_coins # 成就奖励
    
    # 更新数据
    update_user_data(
        user_id, 
        favorability=new_fav, 
        action_points=new_ap, 
        total_sign_ins=new_total_sign_ins,
        coins=new_coins,
        inventory=inventory,
        achievements=earned_achievements,
        remaining_works=new_remaining_works
    )
    
    # 渲染新的卡片 (只显示最终状态，不再显示单次inc)
    pic = await render_sign_card(
        user_id, event.sender.nickname or user_id, new_fav, 
        inc=0, title_override="使用道具", # inc=0 不显示单次增加
        action_points=new_ap, 
        coins=new_coins,
        total_sign_ins=new_total_sign_ins,
        first_sign_in=user_data.get("first_sign_in", ""),
        remaining_works=new_remaining_works,
        custom_title=user_data.get("custom_title", "")
    )
    
    await use_item.finish(MessageSegment.at(user_id) + msg + MessageSegment.image(pic))

@view_inventory.handle()
async def handle_inventory(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    # 黑名单检查
    if user_data.get("is_perm_blacklisted"):
        await view_inventory.finish(MessageSegment.at(user_id) + " 美波里说坏孩子不能看背包哦！")
        
    inventory = user_data.get("inventory", [])
    coins = user_data.get("coins", 0)
    user_name = event.sender.nickname or user_id
    
    # 渲染图片
    pic = await render_inventory_card(user_id, user_name, coins, inventory)
    
    await view_inventory.finish(MessageSegment.image(pic))

@set_favorability.handle()
async def handle_set(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.get_user_id() not in superusers:
        await set_favorability.finish("权限不足，仅限超级用户使用。")
    
    arg_list = args.extract_plain_text().split()
    if len(arg_list) < 2:
        await set_favorability.finish("参数错误。用法: 设置好感度 [用户QQ] [数值]")
        return
    
    target_user_id = arg_list[0]
    try:
        new_val = round(float(arg_list[1]), 2)
    except ValueError:
        await set_favorability.finish("数值格式不正确。")
        return
    
    update_user_data(target_user_id, favorability=new_val)
    await set_favorability.finish(f"已成功将用户 {target_user_id} 的好感度设置为 {new_val:.2f}")

@set_coins.handle()
async def handle_set_coins(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.get_user_id() not in superusers:
        await set_coins.finish("权限不足，仅限超级用户使用。")
    
    arg_list = args.extract_plain_text().split()
    if len(arg_list) < 2:
        await set_coins.finish("参数错误。用法: 设置金币 [用户QQ] [数值]")
        return
    
    target_user_id = arg_list[0]
    try:
        new_val = int(arg_list[1])
    except ValueError:
        await set_coins.finish("金币数值必须是整数哦。")
        return
    
    update_user_data(target_user_id, coins=new_val)
    await set_coins.finish(f"已成功将用户 {target_user_id} 的金币设置为 {new_val}")

@set_ap.handle()
async def handle_set_ap(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if event.get_user_id() not in superusers:
        await set_ap.finish("权限不足，仅限超级用户使用。")
    
    arg_list = args.extract_plain_text().split()
    if len(arg_list) < 2:
        await set_ap.finish("参数错误。用法: 设置行动值 [用户QQ] [数值]")
        return
    
    target_user_id = arg_list[0]
    try:
        new_val = int(arg_list[1])
    except ValueError:
        await set_ap.finish("行动值必须是整数哦。")
        return
    
    update_user_data(target_user_id, action_points=new_val)
    await set_ap.finish(f"已成功将用户 {target_user_id} 的行动值设置为 {new_val}")

@do_work.handle()
async def handle_work(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    # 黑名单检查
    if user_data.get("is_perm_blacklisted"):
        await do_work.finish(MessageSegment.at(user_id) + " 你已被列入永久黑名单，无法打工。")
        
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 检查是否签到 (每日重置依赖签到)
    last_sign_in = user_data.get("last_sign_in", "")
    if last_sign_in != today:
         await do_work.finish(MessageSegment.at(user_id) + " 请先签到以获取今日打工次数哦！")
    
    remaining_works = user_data.get("remaining_works", 1)
    
    if remaining_works <= 0:
        await do_work.finish(MessageSegment.at(user_id) + " 你今天的打工次数已经用完啦！\n可以使用道具增加打工次数哦~")
        
    # 随机打工描述
    work_desc = random.choice(ONIMAI_WORKS)
    
    # 运势加成
    fortune = user_data.get("fortune", {})
    work_rate = 1.0
    if fortune and fortune.get("date") == today:
        fortune_type = fortune.get("type")
        if fortune_type in FORTUNES:
             work_rate = FORTUNES[fortune_type]["work_rate"]
    
    # 随机获得 0-10 金币
    base_coins = random.randint(0, 10)
    earned_coins = int(base_coins * work_rate)
    
    current_coins = user_data.get("coins", 0)
    new_coins = current_coins + earned_coins
    
    # 成就追踪
    achievement_progress = user_data.get("achievement_progress", {"red_packet_total": 0, "steal_success": 0, "consecutive_fails": 0})
    if earned_coins == 0:
        achievement_progress["consecutive_fails"] += 1
    else:
        achievement_progress["consecutive_fails"] = 0
        
    # 扣除次数
    new_remaining_works = remaining_works - 1
    
    # 更新数据
    update_user_data(
        user_id, 
        coins=new_coins, 
        last_work_time=today, 
        remaining_works=new_remaining_works,
        achievement_progress=achievement_progress
    )
    
    # 检查隐藏成就
    await check_hidden_achievements(bot, event, user_id)
    
    # 渲染卡片
    pic = await render_work_card(
        user_id, 
        event.sender.nickname or user_id,
        new_coins,
        earned_coins,
        work_desc,
        new_remaining_works
    )
    
    msg = f" 辛苦啦！打工结束，获得了 {earned_coins} 金币。\n剩余打工次数: {new_remaining_works}"
    await do_work.finish(MessageSegment.at(user_id) + msg + MessageSegment.image(pic))

@rename_card.handle()
async def handle_rename(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    new_title = args.extract_plain_text().strip()
    if not new_title:
        await rename_card.finish("你想要什么新称号呢？请在指令后加上哦，例如：改名 超级哥哥")
        
    if len(new_title) > 10:
        await rename_card.finish("呜...这个称号太长了，真寻记不住啦！(请控制在 10 个字符以内)")
        
    inventory = user_data.get("inventory", [])
    if "改名卡" not in inventory:
        await rename_card.finish("你的背包里没有改名卡呢，去找美波里买一张吧？")
        
    inventory.remove("改名卡")
    update_user_data(user_id, custom_title=new_title, inventory=inventory)
    await rename_card.finish(f"改名成功！以后就叫你 {new_title} 啦~")

@send_red_packet.handle()
async def handle_send_red_packet(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    group_id = str(event.group_id)
    user_data = get_user_data(user_id)
    
    args_text = args.extract_plain_text().strip()
    parts = args_text.split()
    
    if len(parts) < 2:
        await send_red_packet.finish("笨蛋哥哥，发红包的姿势不对哦！试试这样：发红包 金额 数量 [备注]")
        
    try:
        amount = int(parts[0])
        count = int(parts[1])
    except ValueError:
        await send_red_packet.finish("金额和数量要是数字才行呢...")
    
    remark = "大吉大利，恭喜发财"
    exclusive_user = None
    
    # 检查是否at了用户
    at_list = []
    for seg in event.message:
        if seg.type == "at":
            at_list.append(seg.data["qq"])
    
    if at_list:
        exclusive_user = str(at_list[0])
        if str(exclusive_user) == str(user_id):
            await send_red_packet.finish("不能给自己发专属红包哦！")
        if count != 1:
             await send_red_packet.finish("专属红包只能发 1 个哦！")

    if len(parts) >= 3:
        remark_parts = [p for p in parts[2:] if not p.startswith("[CQ:at")]
        if remark_parts:
            remark = " ".join(remark_parts)
        
    if amount <= 0 or count <= 0:
        await send_red_packet.finish("不可以发空红包骗人哦！")
    if count > amount:
        await send_red_packet.finish("太小气啦！每个人至少要分到 1 金币吧！")
    if user_data.get("coins", 0) < amount:
        await send_red_packet.finish(f"私房钱不够了呢... (需要 {amount} 金币)")
        
    achievement_progress = user_data.get("achievement_progress", {"red_packet_total": 0, "steal_success": 0, "consecutive_fails": 0})
    achievement_progress["red_packet_total"] += amount
    
    update_user_data(user_id, coins=user_data["coins"] - amount, achievement_progress=achievement_progress)
    await check_hidden_achievements(bot, event, user_id)
    
    packet_id = str(uuid.uuid4())
    active_red_packets[packet_id] = {
        "sender_id": user_id,
        "sender_name": event.sender.nickname or user_id,
        "total_amount": amount,
        "total_count": count,
        "remain_amount": amount,
        "remain_count": count,
        "grabbed": {},
        "group_id": group_id,
        "remark": remark,
        "create_time": datetime.now(),
        "exclusive_user": exclusive_user
    }
    save_red_packets()
    
    msg = f"🧧 {event.sender.nickname or user_id} 给大家发福利啦！{amount} 金币的大红包！(共 {count} 个)\n备注: {remark}"
    if exclusive_user:
        msg = f"🧧 {event.sender.nickname or user_id} 发了一个专属红包！{amount} 金币！\n指定领取人: {MessageSegment.at(exclusive_user)}\n备注: {remark}"
    else:
        msg += "\n快发送“抢红包”来抢吧！"
    await send_red_packet.finish(msg)

@send_global_red_packet.handle()
async def handle_send_global_red_packet(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    
    if isinstance(event, GroupMessageEvent) and str(event.group_id) in GLOBAL_RED_PACKET_BLACKLIST:
         await send_global_red_packet.finish("本群已被禁止参与世界红包活动！")
    
    args_text = args.extract_plain_text().strip()
    parts = args_text.split()
    
    if len(parts) < 2:
        await send_global_red_packet.finish("笨蛋哥哥，发世界红包的姿势不对哦！试试这样：发世界红包 金额 数量 [备注]")
        
    try:
        amount = int(parts[0])
        count = int(parts[1])
    except ValueError:
        await send_global_red_packet.finish("金额和数量要是数字才行呢...")
        
    remark = "世界和平，普天同庆"
    if len(parts) >= 3:
        remark = " ".join(parts[2:])
        
    if amount <= 0 or count <= 0:
        await send_global_red_packet.finish("不可以发空红包骗人哦！")
    if count > amount:
        await send_global_red_packet.finish("太小气啦！每个人至少要分到 1 金币吧！")
    if user_data.get("coins", 0) < amount:
        await send_global_red_packet.finish(f"私房钱不够了呢... (需要 {amount} 金币)")
        
    achievement_progress = user_data.get("achievement_progress", {"red_packet_total": 0, "steal_success": 0, "consecutive_fails": 0})
    achievement_progress["red_packet_total"] += amount
    
    update_user_data(user_id, coins=user_data["coins"] - amount, achievement_progress=achievement_progress)
    await check_hidden_achievements(bot, event, user_id)
    
    packet_id = str(uuid.uuid4())
    active_red_packets[packet_id] = {
        "sender_id": user_id,
        "sender_name": event.sender.nickname or user_id,
        "total_amount": amount,
        "total_count": count,
        "remain_amount": amount,
        "remain_count": count,
        "grabbed": {},
        "group_id": "GLOBAL",
        "remark": remark,
        "create_time": datetime.now(),
        "exclusive_user": None
    }
    save_red_packets()
    
    msg = f"🌏 {event.sender.nickname or user_id} 发了一个世界红包！{amount} 金币！(共 {count} 个)\n备注: {remark}\n所有群都可以抢哦！快发送“抢红包”来抢吧！"
    await send_global_red_packet.send(msg)
    
    try:
        group_list = await bot.get_group_list()
        broadcast_msg = f"🌏 [世界红包通知] {event.sender.nickname or user_id} 发了一个世界红包！{amount} 金币！\n备注: {remark}\n快发送“抢红包”来抢吧！"
        for group in group_list:
            gid = str(group['group_id'])
            if gid in GLOBAL_RED_PACKET_BLACKLIST: continue
            if isinstance(event, GroupMessageEvent) and gid == str(event.group_id): continue
            try:
                await bot.send_group_msg(group_id=int(gid), message=broadcast_msg)
                await asyncio.sleep(0.5)
            except: continue
    except: pass

@grab_red_packet.handle()
async def handle_grab_red_packet(bot: Bot, event: GroupMessageEvent):
    user_id = event.get_user_id()
    group_id = str(event.group_id)
    can_grab_global = group_id not in GLOBAL_RED_PACKET_BLACKLIST
    
    if not active_red_packets:
        await grab_red_packet.finish("现在没有红包可以抢呢，要不要发一个？")
        
    target_packet_id = None
    target_packet = None
    
    # 优先级：专属红包 > 世界红包 > 群内红包
    for pid, packet in active_red_packets.items():
        if packet.get("exclusive_user") == user_id and packet["remain_count"] > 0:
            target_packet_id, target_packet = pid, packet
            break
    if not target_packet and can_grab_global:
        for pid, packet in active_red_packets.items():
            if packet.get("group_id") == "GLOBAL" and packet["remain_count"] > 0 and user_id not in packet["grabbed"] and not packet.get("exclusive_user"):
                target_packet_id, target_packet = pid, packet
                break
    if not target_packet:
        for pid, packet in active_red_packets.items():
            if packet.get("group_id") == group_id and packet["remain_count"] > 0 and user_id not in packet["grabbed"] and not packet.get("exclusive_user"):
                target_packet_id, target_packet = pid, packet
                break
            
    if not target_packet:
        await grab_red_packet.finish("现在没有红包可以抢呢，或者你已经抢过啦！")
            
    if target_packet.get("exclusive_user") and target_packet.get("exclusive_user") != user_id:
         await grab_red_packet.finish("这不是发给你的专属红包哦！")
        
    if target_packet["remain_count"] == 1:
        grab_amount = target_packet["remain_amount"]
    else:
        avg = target_packet["remain_amount"] / target_packet["remain_count"]
        grab_amount = random.randint(1, int(avg * 2))
        max_allowed = target_packet["remain_amount"] - (target_packet["remain_count"] - 1)
        grab_amount = min(grab_amount, max_allowed)
        
    target_packet["remain_amount"] -= grab_amount
    target_packet["remain_count"] -= 1
    target_packet["grabbed"][user_id] = grab_amount
    
    user_data = get_user_data(user_id)
    update_user_data(user_id, coins=user_data.get("coins", 0) + grab_amount)
    
    msg = f"好耶！你抢到了 {grab_amount} 金币！"
    if target_packet.get("remark"): msg += f"\n备注: {target_packet['remark']}"
    if target_packet["remain_count"] == 0:
        msg += f"\n红包已抢完！"
        del active_red_packets[target_packet_id]
    save_red_packets()
    await grab_red_packet.finish(MessageSegment.at(user_id) + msg)

@rob_user.handle()
async def handle_rob(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    target_id = None
    for seg in event.message:
        if seg.type == "at":
            target_id = str(seg.data["qq"])
            break
    if not target_id: await rob_user.finish("想对谁恶作剧呢？请艾特对方哦！")
    if target_id == user_id: await rob_user.finish("笨蛋！为什么要偷自己的东西啊...")
        
    last_rob = user_data.get("last_rob_time", 0)
    now = time.time()
    if now - last_rob < 3600:
        remain = int((3600 - (now - last_rob)) / 60)
        await rob_user.finish(f"美波里正在盯着你呢！再安分 {remain} 分钟吧...")
    if user_data.get("action_points", 0) < 1:
        await rob_user.finish("累得动不了了... 需要 1 点行动值才能恶作剧哦。")
        
    target_data = get_user_data(target_id)
    new_ap = user_data["action_points"] - 1
    update_user_data(user_id, action_points=new_ap, last_rob_time=now)
    
    target_inventory = target_data.get("inventory", [])
    if "防盗盾" in target_inventory:
        target_inventory.remove("防盗盾")
        update_user_data(target_id, inventory=target_inventory)
        await rob_user.finish(f"恶作剧失败！对方用【防盗盾】挡住了你！")
        
    fortune = user_data.get("fortune", {})
    steal_rate_bonus = 0.0
    if fortune and fortune.get("date") == datetime.now().strftime("%Y-%m-%d"):
        steal_rate_bonus = FORTUNES.get(fortune.get("type"), {}).get("steal_rate", 0.0)

    final_rate = max(0.05, min(0.95, 0.3 + steal_rate_bonus))
    achievement_progress = user_data.get("achievement_progress", {"red_packet_total": 0, "steal_success": 0, "consecutive_fails": 0})

    if random.random() < final_rate:
        steal_amount = min(random.randint(10, 50), target_data.get("coins", 0))
        if steal_amount <= 0: await rob_user.finish("对方口袋里空空如也，只好灰溜溜地回来了...")
        achievement_progress["steal_success"] += 1
        achievement_progress["consecutive_fails"] = 0
        update_user_data(user_id, coins=user_data["coins"] + steal_amount, achievement_progress=achievement_progress)
        update_user_data(target_id, coins=target_data["coins"] - steal_amount)
        await check_hidden_achievements(bot, event, user_id)
        await rob_user.finish(MessageSegment.at(user_id) + f" 嘿嘿... 你成功从 {target_id} 那里拿走了 {steal_amount} 金币！")
    else:
        penalty = min(20, user_data["coins"])
        achievement_progress["consecutive_fails"] += 1
        update_user_data(user_id, coins=user_data["coins"] - penalty, achievement_progress=achievement_progress)
        update_user_data(target_id, coins=target_data["coins"] + penalty)
        await check_hidden_achievements(bot, event, user_id)
        await rob_user.finish(MessageSegment.at(user_id) + f" 哇啊！被发现了！赔偿了 {penalty} 金币...")

@bank_cmd.handle()
async def handle_bank(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    parts = args.extract_plain_text().strip().split()
    if not parts:
        await bank_cmd.finish(f"🏦 欢迎光临真寻银行！\n当前存款: {user_data.get('bank_coins', 0)} 金币\n钱包余额: {user_data.get('coins', 0)} 金币\n指令：银行 存/取 [金额]")
    op = parts[0]
    if op in ["存", "取"]:
        if len(parts) < 2: await bank_cmd.finish("要多少钱呢？")
        try: amount = int(parts[1])
        except: await bank_cmd.finish("数字写错了啦...")
        if amount <= 0: await bank_cmd.finish("不可以操作负数哦！")
        if op == "存":
            if user_data.get("coins", 0) < amount: await bank_cmd.finish("身上没有那么多钱呢...")
            update_user_data(user_id, coins=user_data["coins"] - amount, bank_coins=user_data.get("bank_coins", 0) + amount)
            await bank_cmd.finish(f"✅ 已存入 {amount} 金币！")
        else:
            if user_data.get("bank_coins", 0) < amount: await bank_cmd.finish("存款不够啦！")
            update_user_data(user_id, coins=user_data["coins"] + amount, bank_coins=user_data.get("bank_coins", 0) - amount)
            await bank_cmd.finish(f"✅ 已取出 {amount} 金币！")

@transfer_coins.handle()
async def handle_transfer(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    target_id = None
    for seg in event.message:
        if seg.type == "at":
            target_id = str(seg.data["qq"])
            break
    if not target_id: await transfer_coins.finish("要转给谁呢？请艾特对方哦！")
    try: amount = int(args.extract_plain_text().strip())
    except: await transfer_coins.finish("请输入正确的金额！")
    if amount <= 0: await transfer_coins.finish("不可以转负数哦！")
    user_data = get_user_data(user_id)
    if user_data.get("coins", 0) < amount: await transfer_coins.finish("你的钱不够啦！")
    update_user_data(user_id, coins=user_data["coins"] - amount)
    update_user_data(target_id, coins=get_user_data(target_id).get("coins", 0) + amount)
    await transfer_coins.finish(f"成功转账 {amount} 金币！")

@wealth_rank.handle()
async def handle_wealth_rank(bot: Bot, event: MessageEvent):
    data = load_data()
    rank_data = []
    for uid, udata in data.items():
        if uid.startswith("group_"): continue
        total = udata.get("coins", 0) + udata.get("bank_coins", 0)
        if total > 0: rank_data.append({"name": udata.get("nickname", uid), "coins": total})
    rank_data.sort(key=lambda x: x["coins"], reverse=True)
    msg = "💰 绪山富豪榜 Top 10 💰\n" + "\n".join([f"{i+1}. {u['name']}: {u['coins']}" for i, u in enumerate(rank_data[:10])])
    await wealth_rank.finish(msg)

@duel_user.handle()
async def handle_duel(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    target_id = None
    for seg in event.message:
        if seg.type == "at":
            target_id = str(seg.data["qq"])
            break
    if not target_id: await duel_user.finish("要向谁发起挑战呢？请艾特对方！")
    user_data = get_user_data(user_id)
    if user_data.get("action_points", 0) < 2: await duel_user.finish("体力不足！决斗需要 2 点行动值。")
    update_user_data(user_id, action_points=user_data["action_points"] - 2)
    target_data = get_user_data(target_id)
    user_power = random.randint(50, 100) + int(user_data.get("favorability", 0) / 10)
    target_power = random.randint(50, 100) + int(target_data.get("favorability", 0) / 10)
    if user_power > target_power:
        win = min(max(int(target_data.get("coins", 0) * 0.1), 10), 200)
        update_user_data(user_id, coins=user_data.get("coins", 0) + win)
        update_user_data(target_id, coins=target_data.get("coins", 0) - win)
        await duel_user.finish(f"⚔️ {user_power} vs {target_power}\n🎉 你赢了！赢得了 {win} 金币！")
    else:
        lose = min(max(int(user_data.get("coins", 0) * 0.1), 10), 200)
        update_user_data(user_id, coins=user_data.get("coins", 0) - lose)
        update_user_data(target_id, coins=target_data.get("coins", 0) + lose)
        await duel_user.finish(f"⚔️ {user_power} vs {target_power}\n💔 你输了... 失去了 {lose} 金币。")

@play_dice.handle()
async def handle_dice(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    try: bet = int(args.extract_plain_text().strip())
    except: bet = 10
    if bet <= 0: await play_dice.finish("赌注不能是负数哦！")
    user_data = get_user_data(user_id)
    if user_data.get("coins", 0) < bet: await play_dice.finish("你的钱不够啦！")
    p, b = random.randint(2, 12), random.randint(2, 12)
    if p > b:
        update_user_data(user_id, coins=user_data["coins"] + bet)
        await play_dice.finish(f"🎲 你:{p} 🤖 真寻:{b}\n🎉 你赢了 {bet} 金币！")
    elif p < b:
        update_user_data(user_id, coins=user_data["coins"] - bet)
        await play_dice.finish(f"🎲 你:{p} 🤖 真寻:{b}\n💔 你输了 {bet} 金币。")
    else: await play_dice.finish(f"🎲 你:{p} 🤖 真寻:{b}\n🤝 平局！")

@buy_lottery.handle()
async def handle_buy_lottery(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    user_data = get_user_data(user_id)
    lottery_data = load_lottery_data()
    if user_id in lottery_data["participants"]: await buy_lottery.finish("今天已经买过啦！")
    if user_data.get("coins", 0) < 20: await buy_lottery.finish("金币不足！")
    update_user_data(user_id, coins=user_data["coins"] - 20)
    lottery_data["pool"] += 20
    lottery_data["participants"].append(user_id)
    save_lottery_data(lottery_data)
    await buy_lottery.finish(f"🎫 购买成功！当前奖池: {lottery_data['pool'] + lottery_data.get('base_pool_value', 500)} 金币")

@lottery_info.handle()
async def handle_lottery_info(bot: Bot, event: MessageEvent):
    d = load_lottery_data()
    await lottery_info.finish(f"🎰 奖池: {d['pool'] + d.get('base_pool_value', 500)} 金币\n参与人数: {len(d['participants'])}")

@scheduler.scheduled_job("cron", hour=0, minute=0, id="lottery_draw")
async def draw_lottery_daily():
    d = load_lottery_data()
    p = d.get("participants", [])
    if not p: return
    random.shuffle(p)
    total = d["pool"] + d.get("base_pool_value", 500)
    winners = p[:min(3, len(p))]
    rates = [0.6, 0.3, 0.1]
    for i, uid in enumerate(winners):
        prize = int(total * rates[i])
        update_user_data(uid, coins=get_user_data(uid).get("coins", 0) + prize)
    d["pool"], d["participants"] = 0, []
    save_lottery_data(d)

@scheduler.scheduled_job("cron", hour=4, minute=0, id="bank_interest")
async def bank_interest_job():
    data = load_data()
    for uid, ud in data.items():
        if uid.startswith("group_") or ud.get("bank_coins", 0) <= 0: continue
        ud["bank_coins"] += min(int(ud["bank_coins"] * 0.01), 50)
    save_data(data)
