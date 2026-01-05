# nonebot-plugin-shiro-signin

✨ 基于 NoneBot2 的签到与好感度系统插件 ✨

<p align="center">
  <a href="https://raw.githubusercontent.com/username/nonebot-plugin-shiro-signin/master/LICENSE">
    <img src="https://img.shields.io/github/license/username/nonebot-plugin-shiro-signin.svg" alt="license">
  </a>
  <a href="https://pypi.python.org/pypi/nonebot-plugin-shiro-signin">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-shiro-signin.svg" alt="pypi">
  </a>
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="python">
  <img src="https://img.shields.io/badge/nonebot-2.2.0+-red.svg" alt="nonebot">
</p>

## 📖 介绍

这是一个 NoneBot2 插件。
包含签到、好感度系统、行动系统、商店系统等功能。

## 💿 安装

### 使用 nb-cli 安装 (推荐)
```bash
nb plugin install nonebot-plugin-shiro-signin
```

### 使用 pip 安装
```bash
pip install nonebot-plugin-shiro-signin
```
并在 `bot.py` 中添加：
```python
nonebot.load_plugin("nonebot_plugin_shiro_signin")
```

## ⚙️ 配置

在 `.env` 文件中可以配置以下项（可选）：

| 配置项 | 类型 | 默认值 | 说明 |
|:-----:|:----:|:----:|:----:|
| sign_in_data_path | Path | plugin_dir/data/user_data.json | 数据存储路径 |
| hitokoto_api_url | str | ... | 一言 API 地址 |

## 🎮 使用

| 指令 | 别名 | 说明 |
|:-----:|:----:|:----:|
| 签到 | - | 每日签到，增加好感度、金币和行动值 |
| 查询好感度 | 好感度, 我的好感度, 个人信息 | 查看当前等级和属性 |
| 商店 | 绪山商店, 绪山百货 | 打开道具商店 |
| 购买 [ID] | - | 购买指定道具 |
| 背包 | 我的背包, 仓库 | 查看已拥有道具 |
| 使用 [名称] | 使用道具, 吃, 穿, 玩 | 使用背包里的道具 |
| 行动 | 进行行动, 互动 | 消耗行动值与真寻互动，增加好感度 |

## 🛠️ TODO

- [ ] 增加更多互动事件
- [ ] 完善成就系统
- [ ] 支持更多适配器

## 📄 开源许可

本项目使用 [MIT](LICENSE) 许可证开源。
