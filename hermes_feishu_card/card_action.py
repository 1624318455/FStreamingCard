from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from aiohttp import web

logger = logging.getLogger(__name__)

_HELP_TABS_CN: Dict[str, str] = {
    "chat": "💬 对话命令",
    "cli": "⚙️ CLI 配置",
    "ext": "🧩 技能与扩展",
    "infra": "🌐 平台与自动化",
}

_HELP_COMMANDS: Dict[str, list[tuple[str, str]]] = {
    "chat": [
        ("/new [名称]", "创建新会话"),
        ("/list", "列出所有会话"),
        ("/switch <序号>", "切换会话"),
        ("/current", "查看当前会话"),
        ("/search <关键词>", "搜索会话"),
        ("/history [n]", "最近 n 条消息"),
        ("/delete <序号>", "删除会话"),
        ("/name [序号] <名称>", "会话命名"),
        ("/title [名称]", "设定标题"),
        ("/resume [名称]", "恢复会话"),
        ("/agents", "活跃 Agent / 任务"),
        ("/branch", "分支会话"),
        ("/retry", "重发上一条"),
        ("/undo", "撤销上一条"),
        ("/compress", "手动压缩上下文"),
        ("/rollback [N]", "恢复检查点"),
        ("/background <prompt>", "后台执行"),
        ("/help", "显示命令"),
        ("/usage", "Token 用量"),
        ("/status", "会话信息"),
        ("/profile", "当前 Profile"),
        ("/debug", "上传调试报告"),
    ],
    "cli": [
        ("hermes config", "查看配置"),
        ("hermes config set KEY VAL", "设置配置"),
        ("hermes config path", "配置路径"),
        ("hermes model", "选择模型/提供商"),
        ("hermes setup [section]", "设置向导"),
        ("hermes doctor [--fix]", "检查依赖"),
        ("hermes login [--provider P]", "OAuth 登录"),
        ("/model [名称]", "切换模型"),
        ("/reasoning [级别]", "推理深度"),
        ("/voice [on|off|tts]", "语音模式"),
        ("/yolo", "跳过审批"),
        ("/personality [名称]", "人格设置"),
        ("/verbose", "详细输出"),
        ("/config", "显示配置"),
        ("hermes profile list", "Profile 管理"),
        ("hermes sessions list", "会话管理"),
    ],
    "ext": [
        ("/skill <名称>", "加载 Skill"),
        ("hermes skills list", "列出 Skills"),
        ("hermes skills install ID", "安装 Skill"),
        ("hermes skills search QUERY", "搜索 Skill"),
        ("/tools", "工具管理"),
        ("hermes tools", "交互式工具开关"),
        ("/toolsets", "列出工具集"),
        ("/reload-skills", "重扫 Skills"),
        ("/reload-mcp", "重载 MCP"),
        ("/plugins", "插件列表"),
        ("/curator", "Skill 维护"),
        ("hermes mcp list", "MCP 管理"),
        ("hermes plugins list", "插件管理"),
    ],
    "infra": [
        ("hermes gateway run", "启动网关"),
        ("hermes gateway start", "启动服务"),
        ("hermes gateway stop", "停止服务"),
        ("hermes gateway restart", "重启网关"),
        ("hermes gateway status", "状态"),
        ("/platforms", "平台连接"),
        ("/restart", "重启 (会话内)"),
        ("/sethome", "设为主频道"),
        ("/approve", "审批命令"),
        ("/deny", "拒绝命令"),
        ("/cron", "定时任务"),
        ("hermes cron list", "列出定时任务"),
        ("hermes webhook list", "Webhook"),
        ("/kanban", "协作看板"),
        ("hermes update", "更新版本"),
    ],
}


def build_help_card(*, tab: str = "chat") -> dict[str, Any]:
    """构建交互帮助卡片。"""
    if tab not in _HELP_TABS_CN:
        tab = "chat"
    label = _HELP_TABS_CN[tab]
    commands = _HELP_COMMANDS.get(tab, [])

    tab_actions = [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": lbl},
            "type": "primary" if key == tab else "default",
            "value": {"help_action": "help_tab", "tab": key},
        }
        for key, lbl in _HELP_TABS_CN.items()
    ]

    command_elements = []
    for cmd_name, cmd_desc in commands:
        command_elements.append({
            "tag": "column_set",
            "flex_mode": "none",
            "background_style": "default",
            "columns": [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        {"tag": "markdown", "content": f"**`{cmd_name}`**  {cmd_desc}"},
                    ],
                },
                {
                    "tag": "column",
                    "width": "auto",
                    "elements": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "▶"},
                            "type": "default",
                            "value": {"help_action": "help_cmd", "cmd": cmd_name.split()[0]},
                        },
                    ],
                },
            ],
        })

    elements = [
        {"tag": "action", "actions": tab_actions},
        {"tag": "hr"},
        *command_elements,
        {"tag": "hr"},
        {"tag": "note", "text": {"tag": "plain_text", "content": "💡 提示: 命令支持前缀匹配，如 /pro l = /provider list。点击 ▶ 执行命令，点击 Tab 切换板块。"}},
    ]

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"🤖 Hermes Agent 帮助 — {label}"},
            "template": "blue",
        },
        "elements": elements,
    }


def build_help_loading_response(*, cmd: str) -> dict[str, Any]:
    """显示命令执行中的加载卡片。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"⚡ 执行: {cmd}"},
            "template": "blue",
        },
        "elements": [
            {"tag": "markdown", "content": f"正在执行 **`{cmd}`** … 结果将出现在对话中。"},
        ],
    }


async def handle_card_action(request: web.Request) -> web.Response:
    """处理帮助卡片的按钮点击（Tab 切换 + ▶ 命令执行）。"""
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"action": "none"}, status=400)

    action_value = payload.get("value", {})
    if not isinstance(action_value, dict):
        return web.json_response({"action": "none"})

    help_action = action_value.get("help_action")

    if help_action == "help_tab":
        tab_name = action_value.get("tab", "chat")
        card = build_help_card(tab=tab_name)
        return web.json_response({"card": card, "action": "replace"})

    if help_action == "help_cmd":
        cmd = str(action_value.get("cmd", "") or "")
        if cmd:
            asyncio.ensure_future(_inject_command(request, cmd))
        loading_card = build_help_loading_response(cmd=cmd)
        return web.json_response({"card": loading_card, "action": "replace"})

    return web.json_response({"action": "none"})


async def _inject_command(request: web.Request, cmd: str) -> None:
    """异步注入命令到 gateway，不阻塞卡片响应。失败时静默降级。"""
    gateway_url = request.app.get("gateway_url", "http://127.0.0.1:8080")
    try:
        import aiohttp as _aiohttp
        async with _aiohttp.ClientSession() as session:
            async with session.post(
                f"{gateway_url}/inject",
                json={"command": cmd},
                timeout=_aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Gateway inject returned HTTP %d", resp.status)
    except Exception as exc:
        logger.warning("Failed to inject command '%s': %s", cmd, exc)
