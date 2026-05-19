from __future__ import annotations

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
        ("/new", "开启新对话"),
        ("/list", "列出所有对话"),
        ("/switch <id>", "切换到指定对话"),
        ("/retry", "重新生成最后回复"),
        ("/help", "显示帮助信息"),
        ("/clear", "清除对话历史"),
        ("/compact", "压缩对话上下文"),
        ("/model <name>", "切换模型"),
        ("/think on|off", "开关思考模式"),
        ("/cost", "查看 token 消耗"),
        ("/export", "导出对话"),
        ("/import", "导入对话"),
        ("/share", "分享对话链接"),
        ("/pin", "固定当前对话"),
        ("/unpin", "取消固定对话"),
        ("/archive", "归档对话"),
        ("/status", "查看当前状态"),
        ("/reset", "重置会话"),
        ("/undo", "撤回上一条消息"),
        ("/diff", "查看对话差异"),
        ("/review", "代码审查模式"),
        ("/explain", "解释代码"),
    ],
    "cli": [
        ("hermes config", "查看/修改配置"),
        ("hermes setup", "初始化向导"),
        ("/model", "查看/切换模型"),
        ("hermes status", "查看运行状态"),
        ("hermes logs", "查看日志"),
        ("hermes update", "更新 Hermes"),
        ("hermes doctor", "诊断问题"),
        ("hermes profile list", "列出所有 profile"),
        ("hermes profile use <name>", "切换 profile"),
        ("/theme", "切换主题"),
        ("/locale", "切换语言"),
        ("/verbose", "详细模式开关"),
        ("/debug", "调试模式开关"),
        ("/keybindings", "查看快捷键"),
        ("/history", "查看命令历史"),
        ("/context", "查看上下文信息"),
    ],
    "ext": [
        ("/skill list", "列出可用技能"),
        ("/skill <name>", "执行指定技能"),
        ("hermes skills", "管理技能"),
        ("hermes skill install <name>", "安装技能"),
        ("hermes skill remove <name>", "卸载技能"),
        ("/reload-mcp", "重新加载 MCP 服务器"),
        ("/mcp list", "列出 MCP 服务器"),
        ("/mcp status", "查看 MCP 状态"),
        ("hermes extension list", "列出扩展"),
        ("hermes extension enable <name>", "启用扩展"),
        ("hermes extension disable <name>", "禁用扩展"),
        ("/plugin", "查看插件"),
        ("/hook", "查看钩子"),
    ],
    "infra": [
        ("hermes gateway", "管理网关"),
        ("hermes gateway start", "启动网关"),
        ("hermes gateway stop", "停止网关"),
        ("hermes gateway restart", "重启网关"),
        ("hermes gateway status", "网关状态"),
        ("/cron list", "列出定时任务"),
        ("/cron add", "添加定时任务"),
        ("/cron remove <id>", "删除定时任务"),
        ("hermes platform list", "列出平台"),
        ("hermes platform config", "配置平台"),
        ("/platforms", "查看平台"),
        ("hermes server start", "启动服务器"),
        ("hermes server stop", "停止服务器"),
        ("hermes deploy", "部署"),
        ("hermes backup", "备份"),
    ],
}


def build_help_card(*, tab: str = "chat") -> dict[str, Any]:
    """构建交互帮助卡片。"""
    if tab not in _HELP_TABS_CN:
        tab = "chat"
    label = _HELP_TABS_CN[tab]
    commands = _HELP_COMMANDS.get(tab, [])

    elements: list[dict[str, Any]] = [
        # Tab 切换按钮行
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": lbl},
                    "type": "primary" if k == tab else "default",
                    "value": {"help_action": "help_tab", "tab": k},
                }
                for k, lbl in _HELP_TABS_CN.items()
            ],
        },
        {"tag": "hr"},
    ]

    # 命令列表
    for name, desc in commands:
        elements.append(_build_command_row(name, desc))

    elements.extend([
        {"tag": "hr"},
        {
            "tag": "note",
            "text": {
                "tag": "plain_text",
                "content": "💡 点击 ▶ 执行命令，点击 Tab 切换分类",
            },
        },
    ])

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"Hermes Agent 帮助 — {label}"},
            "template": "blue",
        },
        "elements": elements,
    }


def build_help_loading_response(*, cmd: str) -> dict[str, Any]:
    """构建命令执行中的加载卡片。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "正在执行命令..."},
            "template": "indigo",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": f"⏳ 正在执行 `{cmd}`，请稍候...",
            },
        ],
    }


def _build_command_row(name: str, desc: str) -> dict[str, Any]:
    """构建单行命令：文本 + ▶ 按钮。"""
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "default",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "vertical_align": "center",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": f"**`{name}`** — {desc}",
                    }
                ],
            },
            {
                "tag": "column",
                "width": "auto",
                "vertical_align": "center",
                "elements": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "▶"},
                        "type": "default",
                        "value": {"help_action": "help_cmd", "cmd": name},
                    }
                ],
            },
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
        cmd = action_value.get("cmd", "")
        if cmd:
            await _inject_command(request, cmd)
        loading_card = build_help_loading_response(cmd=cmd)
        return web.json_response({"card": loading_card, "action": "replace"})

    return web.json_response({"action": "none"})


async def _inject_command(request: web.Request, cmd: str) -> None:
    """通过 gateway API 注入命令。失败时静默降级。"""
    gateway_url = request.app.get("gateway_url", "http://127.0.0.1:8080")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{gateway_url}/inject",
                json={"command": cmd},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Gateway inject returned HTTP %d", resp.status)
    except Exception as exc:
        logger.warning("Failed to inject command '%s': %s", cmd, exc)
