# FStreamingCard — Hermes 飞书流式卡片 Sidecar

- GitHub: https://github.com/1624318455/hermes-feishu-streaming-card

基于 baileyh8/hermes-feishu-streaming-card 的 fork，融合 Cheerwhy CardKit v2.0 渲染。

## 技术栈

Python 3.12+ | aiohttp | pip + setuptools | lark-oapi >= 1.4.0 (CardKit v2.0) | pyyaml

## 架构

```
Sidecar (aiohttp, :8765)
├── server.py          # HTTP 路由 (/events, /health, /card_action, /help)
├── session.py         # CardSession 状态机
├── render.py          # 卡片渲染 (CardKit + Legacy)
├── cardkit.py         # CardKit v2.0 卡片构建
├── card_action.py     # 交互帮助卡片按钮回调（可选）
├── feishu_client.py   # Feishu API 封装
├── hook_runtime.py    # run.py hook 运行时
├── text.py            # 流式文本处理
├── bots.py            # 多 Bot 路由
├── config.py          # 配置加载
└── cli.py             # CLI (setup/doctor/install/start/stop)
```

核心: CardKit v2.0 流式渲染（降级 IM PATCH）、多 Profile/Bot。可选: 交互帮助卡片（4 Tab + ▶ 命令执行，需 `help_card.enabled: true`）。

## 常用命令

- 安装: `/c/Users/memeflyfly/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe -m pip install -e ".[test]"`
- 启动: `python -m hermes_feishu_card.runner --config ~/.hermes_feishu_card/config.yaml`
- 健康检查: `curl http://127.0.0.1:8765/health`

## 踩坑记录

1. feishu.py `global lark` 声明必须在 import 之前（upstream bug）
2. CardKit v2.0 需 lark-oapi >= 1.4.0，旧版必须有 IM PATCH 降级
3. 更新间隔: CardKit 100ms / IM PATCH 500ms / 终态卡片指数退避
4. 飞书卡片最多 5 个表格，需截断
5. Session key = `profile_id:message_id`（有 profile）或 `message_id`（无 profile）
6. Help card 默认关闭，启用需 config + gateway 补丁（见 patches/README.md）
