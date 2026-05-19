# FStreamingCard — 项目开发指南

## 项目概述

FStreamingCard 是一个 Hermes Agent Gateway 的 **Feishu/Lark 流式卡片 Sidecar**，在 [baileyh8/hermes-feishu-streaming-card](https://github.com/baileyh8/hermes-feishu-streaming-card) 的基础上改进，核心目标：

### 三大能力

```
┌─ FStreamingCard (Sidecar, 端口 8765) ──────────────────┐
│                                                         │
│  1️⃣  CardKit v2.0 流式渲染  (← Cheerwhy 的技术方案)    │
│     增量更新元素，100ms 间隔，真打字机效果               │
│     ↓ 降级                                              │
│     IM PATCH 整卡替换 (500ms)                           │
│                                                         │
│  2️⃣  交互帮助卡片          (← 本次新增)                 │
│     Tab 切换 + ▶ 命令执行                               │
│     用户点按钮 → sidecar 处理 → 返回新卡片              │
│                                                         │
│  3️⃣  多 Profile / 多 Bot   (← baileyh8 已有)           │
│     一个 sidecar 服务多个 Hermes 实例                    │
└─────────────────────────────────────────────────────────┘
```

### 和两个上游项目的关系

| 项目 | 拿来什么 | 改什么 |
|------|---------|--------|
| [baileyh8/hermes-feishu-streaming-card](https://github.com/baileyh8/hermes-feishu-streaming-card) | Sidecar 架构、多 Profile、多 Bot、会话管理、安装脚本 | 渲染层从 IM PATCH 升级到 CardKit v2.0 |
| [Cheerwhy/hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming) | CardKit v2.0 卡片构建、流式渲染逻辑、降级策略 | 把它从进程内插件搬到 sidecar 里 |
| 本项目的 feishu-interactive-help-card (SKILL) | 交互帮助卡片的构建 + 按钮回调处理 | 从 feishu.py 搬到 sidecar 的 HTTP API |

---

## 架构总览

```
┌─ Hermes Gateway ───────────────────────────────┐
│  run.py (6 个最小 hook 点)                       │
│    message.started  ─┐                          │
│    thinking.delta    │  HTTP POST /events       │
│    answer.delta      │  → sidecar:8765          │
│    tool.updated      │                          │
│    message.completed │                          │
│    message.failed    ┘                          │
│                                                 │
│  feishu.py (1 个最小 hook)                      │
│    card.action.trigger                          │
│    → help_action → POST /card_action            │
│    → sidecar 返回新卡片 JSON 替换原卡片          │
└───────────────────────┬─────────────────────────┘
                        │
┌─ Sidecar (aiohttp, :8765) ─────────────────────┐
│                                                  │
│  POST /events                                    │
│  ├─ CardSession 状态机 (沿用 baileyh8 的)         │
│  ├─ CardKitRenderer (新增，移植 Cheerwhy 的)      │
│  │   └─ FeishuClient.update_card_element()        │
│  ├─ IM PATCH 降级 (保留 baileyh8 的)              │
│  │   └─ FeishuClient.update_card_message()        │
│                                                   │
│  POST /card_action                                │
│  ├─ help_tab → 构建新卡片 JSON → 返回             │
│  ├─ help_cmd → 转发命令到 Hermes gateway           │
│                                                   │
│  POST /alerts                                     │
│  └─ 监控告警 / 健康检查                            │
│                                                   │
│  GET /health                                      │
│  └─ 活跃会话、指标、诊断                          │
└──────────────────────────────────────────────────┘
```

---

## 文件结构（基于 baileyh8 的代码库）

```
hermes_feishu_card/
├── __init__.py
├── __main__.py          # CLI 入口
├── cli.py               # setup/doctor/install/start/stop
├── config.py            # 配置加载
├── server.py            # AIOHTTP server 主路由 ← 加 /card_action
├── events.py            # SidecarEvent 数据类
├── session.py           # CardSession 状态机
├── process.py           # 进程管理 (start/stop/restart)
├── hook_runtime.py      # run.py hook 运行时 (HTTP POST → sidecar)
├── feishu_client.py     # Feishu API 封装 ← 加 update_card_element()
│
├── render.py            # 卡片渲染器 ← 重写为 CardKit 模式
├── cardkit.py           # [新增] CardKit v2.0 卡片构建逻辑
│                        # 移植自 Cheerwhy 的 cardkit.py
│
├── card_action.py       # [新增] 帮助卡片交互处理
│                        # 移植自 feishu-interactive-help-card SKILL
│
├── text.py              # 流式文本处理 (保留)
├── bots.py              # 多 Bot 路由 (保留)
├── metrics.py           # 指标收集 (保留)
├── runner.py            # 启动器 (保留)
├── image.py             # 图片上传 (保留)
│
└── install/             # Hook 注入工具
    ├── hook_013_plus.py
    └── hook_legacy.py
```

---

## 实施路线

### Phase 1 — 基础设施 + CardKit v2.0

#### 1.1 Fork baileyh8 仓库
```
git clone <你 fork 的仓库> D:\Work\ForAI\FStreamingCard
git remote add upstream https://github.com/baileyh8/hermes-feishu-streaming-card
```

#### 1.2 扩展 FeishuClient（`feishu_client.py`）

新增方法：

```python
async def update_card_element(
    self, message_id: str, element_id: str, content: str
) -> None:
    """CardKit v2.0 增量更新：更新卡片中的某个元素。
    
    POST /open-apis/im/v1/messages/{message_id}/update_card_element
    
    这是 IM PATCH 的替代方案——只传变化的元素，不是整卡。
    如果飞书返回不支持（如旧版本），降级到 update_card_message()。
    """
    url = f"{self._config.base_url}/im/v1/messages/{message_id}/update_card_element"
    payload = {
        "element_id": element_id,
        "content": content,
    }
    ...
```

保留 `update_card_message()` 作为 CardKit 降级方案。

#### 1.3 CardKit 卡片构建（`cardkit.py`，新增）

移植 Cheerwhy 的 `cardkit.py` 核心逻辑。关键区别：

```python
# CardKit v2.0 卡片结构
card = {
    "schema": "2.0",
    "config": {
        "streaming_mode": True,      # 启用流式
        "wide_screen_mode": True,
        "update_multi": True,        # 多元素增量更新
    },
    "body": {
        "elements": [
            {
                "tag": "markdown",
                "element_id": "streaming_content",  # ← 关键：element_id
                "content": initial_text,
            },
            {
                "tag": "markdown", 
                "element_id": "tool_panel",
                "content": tool_status,
            },
        ],
    },
}
```

流式更新时只发变化的元素：

```python
# 100ms 间隔增量更新
await client.update_card_element(
    message_id=msg_id,
    element_id="streaming_content", 
    content=new_text_delta,
)
```

**降级策略**（直接从 Cheerwhy 搬）：
| 策略 | 间隔 | 触发条件 |
|------|------|---------|
| CardKit 流式 | 100ms | 默认 |
| IM PATCH | 1.5s | CardKit 创建/更新失败 |
| 最终卡片失败 | — | 回退文字回复 |

#### 1.4 修改渲染器（`render.py`）

从目前整卡替换改为 CardKit 模式：

```python
def render_card(session, use_cardkit=True) -> dict:
    """渲染卡片。use_cardkit=True → CardKit v2.0 结构，False → IM PATCH 兼容结构。"""
    if use_cardkit and cardkit_available(session):
        return build_cardkit_card(session)
    return build_legacy_card(session)
```

#### 1.5 修改 server.py 的更新逻辑

目前 `_apply_event_locked` 更新后直接 `update_card_message`。改为：

```python
async def _apply_event_locked(app, session_key, event, session):
    """处理事件并更新卡片。优先用 CardKit 增量。"""
    changed = session.apply(event)
    if not changed:
        return
    
    # 检查是否支持 CardKit
    feishu_client = _client_for_event(app, event)
    use_cardkit = _supports_cardkit(event, session)
    
    if use_cardkit:
        # CardKit 增量更新
        element_updates = compute_cardkit_deltas(session, event)
        for element_id, content in element_updates.items():
            try:
                await feishu_client.update_card_element(
                    message_id=feishu_msg_id,
                    element_id=element_id,
                    content=content,
                )
            except CardKitNotSupported:
                use_cardkit = False
                break  # 降级到整卡
        
        if use_cardkit:
            return
    
    # 降级：整卡替换
    card = render_card(session, use_cardkit=False)
    await feishu_client.update_card_message(message_id=feishu_msg_id, card=card)
```

---

### Phase 2 — 交互帮助卡片

#### 2.1 完整命令数据和 Tab 分类

`card_action.py` 中定义：

```python
_HELP_TABS_CN = {
    "chat": "💬 对话命令",
    "cli": "⚙️ CLI 配置",
    "ext": "🧩 技能与扩展",
    "infra": "🌐 平台与自动化",
}

_HELP_COMMANDS = {
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
```

#### 2.2 构建帮助卡片（`card_action.py`）

```python
def build_help_card(*, tab: str) -> dict:
    """Build an interactive help card showing commands for *tab*.
    
    卡片结构：
      header (蓝色, "🤖 Hermes Agent 帮助 — {Tab名}")
      ├── action (4 个 Tab 按钮, current=primary, others=default)
      ├── hr
      ├── column_set × N (每条命令: 左=markdown text, 右=▶ button)
      ├── hr
      └── note ("点击 ▶ 执行命令…")
    """
    tab_labels = _HELP_TABS_CN
    all_commands = _HELP_COMMANDS
    label = tab_labels.get(tab, tab_labels["chat"])
    commands = all_commands.get(tab, all_commands["chat"])

    # Tab buttons row
    tab_actions = [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": lbl},
            "type": "primary" if key == tab else "default",
            "value": {"help_action": "help_tab", "tab": key},
        }
        for key, lbl in tab_labels.items()
    ]

    # Per-command rows: text column + ▶ button column
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


def build_help_loading_response(*, cmd: str) -> dict:
    """Show a brief 'executing' card while the command runs."""
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
```

#### 2.3 server.py 加路由

```python
# 在 create_app() 中添加
app.router.add_post("/card_action", handle_card_action)
```

#### 2.4 card_action HTTP handler（`card_action.py`）

```python
async def handle_card_action(request: web.Request) -> web.Response:
    """处理帮助卡片的按钮点击。
    
    两种 action:
      help_tab  → 构建新卡片 JSON 返回 → sidecar 返回给 feishu.py
      help_cmd  → 触发命令注入 → 返回"执行中"卡片
    """
    payload = await request.json()
    action_value = payload.get("value", {})
    help_action = action_value.get("help_action")

    if help_action == "help_tab":
        tab_name = action_value.get("tab", "chat")
        card = build_help_card(tab=tab_name)
        return web.json_response({
            "action": "replace",
            "card": card,
        })

    elif help_action == "help_cmd":
        cmd = str(action_value.get("cmd", "") or "")
        if cmd:
            # 异步触发命令注入（不阻塞卡片响应）
            asyncio.ensure_future(inject_command_to_gateway(request, cmd))
        loading_card = build_help_loading_response(cmd=cmd)
        return web.json_response({
            "action": "replace",
            "card": loading_card,
        })

    return web.json_response({"action": "none"})
```

#### 2.5 命令注入（`card_action.py`）

```python
async def inject_command_to_gateway(request: web.Request, command: str) -> None:
    """将帮助卡片上的命令注入到 Hermes Gateway agent 会话中。
    
    通过 gateway 内部 API 或 lark-cli 将命令作为用户消息发送。
    """
    # 方案 A: 如果 sidecar 知道 chat_id，直接发消息
    chat_id = request.app.get("_card_action_chat_id")
    if chat_id:
        feishu_client = request.app.get(FEISHU_CLIENT_KEY)
        if feishu_client:
            # 发送命令文本到群聊，等价于用户输入
            await feishu_client.send_card(chat_id, {
                "config": {"wide_screen_mode": True},
                "header": {"title": {"tag": "plain_text", "content": "⚡ 执行命令"}, "template": "blue"},
                "elements": [
                    {"tag": "markdown", "content": f"执行: **`{command}`**"},
                ],
            })
    
    # 方案 B: 调用 gateway 的 inject API（如果 Hermes 暴露了）
    # POST http://localhost:9090/inject-message
    # 需要 Hermes gateway 插件支持
```

#### 2.6 feishu.py 的 hook（最小改动）

在 `_on_card_action_trigger` 中，在 `update_prompt_action` 之后、`_handle_card_action_event` 之前插入：

```python
help_action = action_value.get("help_action") if isinstance(action_value, dict) else None
if help_action:
    return self._handle_help_card_action(
        event=event,
        action_value=action_value,
        loop=loop,
    )
```

#### 2.7 feishu.py `_handle_help_card_action`（同步 handler）

```python
def _handle_help_card_action(self, *, event: Any, action_value: Dict[str, Any], loop: Any) -> Any:
    """Handle help card tab switch and command execution button clicks."""
    help_action = action_value.get("help_action")
    
    if help_action == "help_tab":
        tab_name = action_value.get("tab", "chat")
        if P2CardActionTriggerResponse is None:
            return None
        response = P2CardActionTriggerResponse()
        if CallBackCard is not None:
            card = CallBackCard()
            card.type = "raw"
            card.data = self._build_help_card(tab=tab_name)
            response.card = card
        return response

    elif help_action == "help_cmd":
        cmd = str(action_value.get("cmd", "") or "")
        if cmd:
            self._submit_on_loop(loop, self._execute_help_command(command=cmd, event=event))
        if P2CardActionTriggerResponse is None:
            return None
        response = P2CardActionTriggerResponse()
        if CallBackCard is not None:
            card = CallBackCard()
            card.type = "raw"
            card.data = self._build_help_loading_response(cmd=cmd)
            response.card = card
        return response

    if P2CardActionTriggerResponse is None:
        return None
    return P2CardActionTriggerResponse()
```

#### 2.8 feishu.py `_execute_help_command`（async 路由）

```python
async def _execute_help_command(self, *, command: str, event: Any) -> None:
    """Route a help card command button click as a synthetic user message.
    
    关键机制：将命令文本包装成 MessageEvent(TEXT) 注入 agent pipeline。
    使用 TEXT 类型而非 COMMAND 类型，因为 pipeline 会自动检测 / 前缀
    并转为 COMMAND 处理。
    """
    context = getattr(event, "context", None)
    chat_id = str(getattr(context, "open_chat_id", "") or "")
    operator = getattr(event, "operator", None)
    open_id = str(getattr(operator, "open_id", "") or "")
    if not chat_id or not open_id:
        logger.debug("[Feishu] Help cmd missing chat_id or operator open_id, dropping")
        return

    # 构造发送者 profile
    sender_id = SimpleNamespace(open_id=open_id, user_id=None, union_id=None)
    sender_profile = await self._resolve_sender_profile(sender_id)
    chat_info = await self.get_chat_info(chat_id)
    source = self.build_source(
        chat_id=chat_id,
        chat_name=chat_info.get("name") or chat_id or "Feishu Chat",
        chat_type=self._resolve_source_chat_type(chat_info=chat_info, event_chat_type="group"),
        user_id=sender_profile["user_id"],
        user_name=sender_profile["user_name"],
        thread_id=None,
        user_id_alt=sender_profile["user_id_alt"],
    )
    
    # Use TEXT type so the message pipeline properly detects /prefix → COMMAND
    synthetic_event = MessageEvent(
        text=command,
        message_type=MessageType.TEXT,
        source=source,
        message_id=str(uuid.uuid4()),
        timestamp=datetime.now(),
    )
    logger.info("[Feishu] Routing help cmd %r from %s in %s", command, open_id, chat_id)
    await self._handle_message_with_guards(synthetic_event)
```

### Phase 3 — 帮助卡片与网关对接

---

## 开发环境搭建

```bash
# 1. 克隆仓库
cd /d/Work/ForAI/FStreamingCard
git init
# (后续关联你的 GitHub 仓库)

# 2. 安装依赖
# 使用 Hermes venv 里的 Python（与 Hermes 一致的依赖）
/c/Users/memeflyfly/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe -m pip install -e ".[test]"

# 3. 运行 sidecar（开发模式）
$env:HERMES_FEISHU_CARD_EVENT_URL = "http://127.0.0.1:8765/events"
python -m hermes_feishu_card.runner --config ~/.hermes_feishu_card/config.yaml

# 4. 安装 hook
python -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes

# 5. 重启网关
hermes gateway restart
```

**关键路径速查：**
- Sidecar 配置：`~/.hermes_feishu_card/config.yaml`
- Hermes 配置：`~/.hermes/config.yaml`
- 网关日志：`~/AppData/Local/hermes/logs/gateway.log`
- Sidecar 日志：`~/.hermes_feishu_card/logs/`

---

## 已知坑点和注意事项

### ⚠️ 1. `global lark` 声明顺序（upstream bug）

`hermes-agent/gateway/platforms/feishu.py` 中的 `_build_lark_client`：

```python
# ❌ 错误（upstream 现有代码）
def _build_lark_client(self, domain):
    if lark is None:
        import lark_oapi
    global lark          # ← SyntaxError: global 在使用变量之后
    lark = lark_oapi

# ✅ 正确
def _build_lark_client(self, domain):
    global lark          # ← 必须先声明
    if lark is None:
        import lark_oapi
        lark = lark_oapi
```

### ⚠️ 2. Sidecar 故障隔离

Sidecar 挂了 → 回退到文字回复（fail-open）。这是 sidecar 架构的核心优势——不要改成 fail-close，否则 sidecar 崩了网关跟着崩。

### ⚠️ 3. CardKit 兼容性

CardKit v2.0 需要飞书 SDK `lark-oapi >= 1.4.0`。旧版本飞书客户端可能不支持 CardKit 流式，必须有 IM PATCH 降级。

### ⚠️ 4. 更新间隔

| 模式 | 最小间隔 | 说明 |
|------|---------|------|
| CardKit 流式 | 100ms | 元素级增量更新 |
| IM PATCH | 500ms | 整卡替换，太快会被限频 |
| 终态卡片 | 1s / 2s / 4s 指数退避 | 重试最多 3 次 |

### ⚠️ 5. 表格数量限制

飞书卡片最多 5 个表格。render.py 已有截断逻辑（`_render_main_content_elements`），CardKit 模式下也需要处理。

### ⚠️ 6. 多 Profile 下的 session key

```python
# session key = profile_id:message_id（有 profile 时）
# session key = message_id（无 profile 时）
# 改渲染逻辑时注意不要破坏这个隔离
```

---

## 测试流程

```bash
# 1. 启动 sidecar
python -m hermes_feishu_card.runner --config ~/.hermes_feishu_card/config.yaml

# 2. 检查健康
curl http://127.0.0.1:8765/health

# 3. 在飞书 FStreamingCard 群 @爱马仕 发消息
# → 观察 sidecar 日志是否有流式更新

# 4. 测试帮助卡片
# 用 lark-cli 发测试卡片：
export PATH="/c/home/agent/.hermes/npm-global:$PATH"
content=$(cat ~/test_help_card.json)
lark-cli im +messages-send --chat-id oc_6b9d514e9cb66aec2f9d6d64cfbea2b9 --msg-type interactive --content "$content"

# 5. 点击 Tab / ▶ 按钮
# → 检查 sidecar /card_action 是否收到请求
```

---

## 关键参考链接

| 项目 | 地址 |
|------|------|
| baileyh8 源码 | https://github.com/baileyh8/hermes-feishu-streaming-card |
| Cheerwhy 源码 | https://github.com/Cheerwhy/hermes-lark-streaming |
| Hermes Agent | https://github.com/NousResearch/hermes-agent |
| 飞书卡片文档 | https://open.feishu.cn/document/server-docs/im-v1/interactive-card |
| CardKit v2.0 | https://open.feishu.cn/document/server-docs/im-v1/interactive-card/stream-card |
| 飞书 OpenAPI | https://open.feishu.cn/document/server-docs/docs |

---

## 谁是谁

| 称呼 | 身份 |
|------|------|
| 爱马仕 | Hermes Agent，当前与你对话的 Agent |
| 克劳德 | Claude Code CLI，另一位开发协作 Agent |
| 用户 | 项目发起人，在飞书群 FStreamingCard 中协调开发 |
| FStreamingCard | 项目名，也是飞书群聊名 (oc_6b9d514e9cb66aec2f9d6d64cfbea2b9) |
