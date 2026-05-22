# FStreamingCard - Hermes Feishu 流式卡片 Sidecar

## 技术栈
- 语言: Python 3.12+
- Web 框架: aiohttp
- 包管理器: pip + setuptools (editable install: `pip install -e ".[test]"`)
- 运行环境: Hermes venv (`/c/Users/memeflyfly/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`)
- 依赖: lark-oapi >= 1.4.0 (CardKit v2.0), pyyaml
- 测试框架: pytest (待配置)
- Lint/Format: 待配置
- 数据库: 无

## 项目架构

基于 baileyh8/hermes-feishu-streaming-card 的 fork，融合 Cheerwhy 的 CardKit v2.0 渲染。

```
Hermes Gateway (run.py, feishu.py)
    ↕ HTTP POST /events
Sidecar (aiohttp, :8765)
    ├── server.py          — HTTP 路由 (/events, /health, /card_action, /help)
    ├── session.py         — CardSession 状态机
    ├── render.py          — 卡片渲染 (CardKit 模式 + Legacy 模式)
    ├── cardkit.py         — CardKit v2.0 卡片构建
    ├── card_action.py     — 交互帮助卡片按钮回调 (可选，需 help_card.enabled: true)
    ├── feishu_client.py   — Feishu API 封装 (+ update_card_element)
    ├── hook_runtime.py    — run.py hook 运行时
    ├── text.py            — 流式文本处理
    ├── bots.py            — 多 Bot 路由
    ├── config.py          — 配置加载
    └── cli.py             — CLI (setup/doctor/install/start/stop)
```

核心能力：CardKit v2.0 流式渲染（降级 IM PATCH）、多 Profile/Bot。

可选功能：交互帮助卡片（4 Tab + ▶ 命令执行），需配置 `help_card.enabled: true` 并应用 gateway 补丁。

## 开发流程（自动执行）
1. 理解 → 2. 规划 → 3. 执行 → 4. 测试验证 → 5. 提交推送 → 6. 通知 Hermes
- 不询问"要提交吗"等问题，自动执行全流程。
- 测试验证：sidecar 用 curl /health + 飞书群发消息测试；帮助卡片用 lark-cli 发测试卡片。

## 编码规范
- 文件命名: snake_case (Python 标准)
- 变量/函数: snake_case
- 类: PascalCase
- 通用原则: 不写解释型注释（除非 WHY 不明显），三次原则，优先编辑现有文件，安全优先。

## 常用命令
- 安装: `/c/Users/memeflyfly/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe -m pip install -e ".[test]"`
- 启动 sidecar: `python -m hermes_feishu_card.runner --config ~/.hermes_feishu_card/config.yaml`
- 安装 hook: `python -m hermes_feishu_card.cli install --hermes-dir ~/.hermes/hermes-agent --yes`
- 健康检查: `curl http://127.0.0.1:8765/health`
- 测试: `pytest` [待配置]

## 关键路径
- Sidecar 配置: `~/.hermes_feishu_card/config.yaml`
- Hermes 配置: `~/.hermes/config.yaml`
- 网关日志: `~/AppData/Local/hermes/logs/gateway.log`
- Sidecar 日志: `~/.hermes_feishu_card/logs/`

## 测试策略
- [待配置] pytest + 单元测试 + 集成测试
- 提交前检查: lint, 类型检查, 单元测试, 无调试代码, 无硬编码密钥。

## 安全护栏
- 人工确认: 修改 feishu.py 集成代码、配置文件、安装脚本。
- 禁止: rm -rf /, DROP TABLE, git push --force main。
- 发布命令前展示摘要。
- Sidecar 故障隔离: fail-open（sidecar 挂了回退文字回复，不拖垮网关）。

## 已知坑点
1. feishu.py 的 `global lark` 声明必须在 import 之前（upstream bug，见 AGENTS.md §1）
2. CardKit v2.0 需要 lark-oapi >= 1.4.0，旧版必须有 IM PATCH 降级
3. 更新间隔: CardKit 100ms / IM PATCH 500ms / 终态卡片指数退避
4. 飞书卡片最多 5 个表格，需截断处理
5. Session key = `profile_id:message_id`（有 profile）或 `message_id`（无 profile）
6. Help card 功能默认关闭，启用需 config `help_card.enabled: true` + gateway 补丁（见 patches/README.md）

## 决策权限矩阵
- 局部: 单文件内部 → 自主
- 模块内: server.py 路由 / cardkit.py 构建逻辑 → 自主
- 跨模块: render.py ↔ feishu_client.py 接口变更 → 知会
- 全局: 架构变更 / feishu.py 集成修改 → 必须确认

## 协作规则 (Hermes)
- 完成任务后通过飞书通知 Hermes（bot open_id: ou_bcb48e73ca7890a12ac93b588437167b）
- API: http://127.0.0.1:8642（OpenAI 兼容格式）
- 消息内容：项目路径、GitHub URL（https://github.com/1624318455/hermes-feishu-streaming-card）、commit hashes、变更摘要、待办事项
- 使用 Node.js 发送飞书消息（避免 Windows curl 中文乱码）
- 飞书群 FStreamingCard: oc_6b9d514e9cb66aec2f9d6d64cfbea2b9
- 飞书 @ 提及必须使用富文本格式 (msg_type: "post")，纯文本 `@名字` 不会触发通知：
  ```json
  {
    "msg_type": "post",
    "content": {
      "zh_cn": {
        "title": "",
        "content": [[
          {"tag": "at", "user_id": "ou_xxx"},
          {"tag": "text", "text": " 消息内容"}
        ]]
      }
    }
  }
  ```
- 注意：不同应用下同一个用户的 open_id 不同，需要使用当前应用识别到的 ID

## 记忆维护
- 本 CLAUDE.md 只放静态知识，过程记忆由 claude-mem 负责。
- 发现坑点、特殊用法立即更新；milestone 后精简合并。

## 参考
- 上游: baileyh8/hermes-feishu-streaming-card, Cheerwhy/hermes-lark-streaming
- 设计文档: AGENTS.md（完整实施路线、代码示例、已知坑点）
