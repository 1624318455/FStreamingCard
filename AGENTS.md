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

#### 2.1 server.py 加路由

```python
app.router.add_post("/card_action", handle_card_action)
```

#### 2.2 card_action.py（新增）

移植 `feishu-interactive-help-card` SKILL 中的逻辑：

```python
async def handle_card_action(request: web.Request) -> web.Response:
    """处理帮助卡片的按钮点击（Tab 切换 + ▶ 命令执行）。"""
    payload = await request.json()
    action_value = payload.get("value", {})
    help_action = action_value.get("help_action")
    
    if help_action == "help_tab":
        tab_name = action_value.get("tab", "chat")
        card = build_help_card(tab=tab_name)
        return web.json_response({"card": card, "action": "replace"})
    
    elif help_action == "help_cmd":
        cmd = action_value.get("cmd", "")
        # 通过 gateway API 注入命令
        await inject_command(request, cmd)
        loading_card = build_help_loading_response(cmd=cmd)
        return web.json_response({"card": loading_card, "action": "replace"})
    
    return web.json_response({"action": "none"})
```

#### 2.3 Tab 分类

| Key | 标签 | 命令数 | 内容 |
|-----|------|--------|------|
| `chat` | 💬 对话命令 | 22 | `/new`, `/list`, `/switch`, `/retry`, `/help`… |
| `cli` | ⚙️ CLI 配置 | 16 | `hermes config`, `hermes setup`, `/model`… |
| `ext` | 🧩 技能与扩展 | 13 | `/skill`, `hermes skills`, `/reload-mcp`… |
| `infra` | 🌐 平台与自动化 | 15 | `hermes gateway`, `/cron`, `/platforms`… |

#### 2.4 卡片模板

```python
_HELP_TABS_CN = {
    "chat": "💬 对话命令",
    "cli": "⚙️ CLI 配置",
    "ext": "🧩 技能与扩展",
    "infra": "🌐 平台与自动化",
}

def build_help_card(*, tab: str) -> dict:
    """构建交互帮助卡片。"""
    label = _HELP_TABS_CN[tab]
    commands = _HELP_COMMANDS[tab]
    
    elements = [
        # Tab 切换按钮行
        {"tag": "action", "actions": [
            {"tag": "button", "text": lbl, "type": "primary" if k == tab else "default",
             "value": {"help_action": "help_tab", "tab": k}}
            for k, lbl in _HELP_TABS_CN.items()
        ]},
        {"tag": "hr"},
        # 命令列表（每行：文本 + ▶ 按钮）
        *[_build_command_row(name, desc) for name, desc in commands],
        {"tag": "hr"},
        {"tag": "note", "text": {"tag": "plain_text", "content": "💡 点击 ▶ 执行命令，点击 Tab 切换"}},
    ]
    
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"🤖 Hermes Agent 帮助 — {label}"}, "template": "blue"},
        "elements": elements,
    }
```

---

### Phase 3 — 帮助卡片与网关对接

#### 3.1 feishu.py 追加最小 hook

在 `_on_card_action_trigger` 中，在 `update_prompt_action` 之后、`_handle_card_action_event` 之前加：

```python
help_action = action_value.get("help_action") if isinstance(action_value, dict) else None
if help_action:
    # 转发到 sidecar /card_action
    card_response = await self._forward_to_sidecar(action_value)
    if card_response and P2CardActionTriggerResponse is not None:
        response = P2CardActionTriggerResponse()
        if CallBackCard is not None:
            card = CallBackCard()
            card.type = "raw"
            card.data = card_response.get("card", build_help_card(tab="chat"))
            response.card = card
        return response
```

需要新增 `_forward_to_sidecar` 异步方法：

```python
async def _forward_to_sidecar(self, action_value: dict) -> dict | None:
    """转发卡片动作到 sidecar /card_action。失败时静默降级。"""
    sidecar_url = os.getenv("HERMES_FEISHU_CARD_EVENT_URL", "http://127.0.0.1:8765")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{sidecar_url}/card_action",
                json={"value": action_value},
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                return await resp.json()
    except Exception:
        logger.warning("[Feishu] Sidecar /card_action unreachable, skipping")
        return None
```

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
