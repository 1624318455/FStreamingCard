# FStreamingCard

> Fork of [baileyh8/hermes-feishu-streaming-card](https://github.com/baileyh8/hermes-feishu-streaming-card) v3.4.1，融合 [Cheerwhy/hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming) 的 CardKit v2.0 流式渲染。

Hermes Agent Gateway 的飞书/Lark 流式卡片 Sidecar，提供 CardKit v2.0 增量更新、交互帮助卡片、多 Profile / 多 Bot 支持。

---

## 核心能力

| 能力 | 状态 | 说明 |
|------|------|------|
| CardKit v2.0 元素级增量更新 | ✅ v0.2.0 | 100ms 间隔，只传变化元素，真打字机效果 |
| IM PATCH 降级 | ✅ v0.2.0 | CardKit 不支持时自动降级整卡替换 |
| 交互帮助卡片 | ✅ v0.2.0 | 4 Tab 切换 + ▶ 命令注入（对话/CLI/技能/平台） |
| 多 Profile 进程隔离 | ✅ upstream v3.3+ | 一个 sidecar 服务多个 Hermes 实例 |
| 多 Bot 路由 | ✅ upstream v3.2+ | `bots.items` + `bindings.chats` 按群路由 |
| 流式思考展示 | ✅ upstream | thinking/answer 增量渲染 |
| 工具调用跟踪 | ✅ upstream | 累计调用次数和状态 |
| Footer 统计 | ✅ upstream | 耗时/模型/token/上下文占比 |
| 表格超限保护 | ✅ upstream | 超 5 表自动截断 |
| Cron 最终卡片 | ✅ upstream | 定时任务终态卡片 |

---

## 快速安装

```bash
git clone https://github.com/1624318455/FStreamingCard.git
cd FStreamingCard && pip install -e ".[test]"
export FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=xxx
python3 -m hermes_feishu_card.cli setup --hermes-dir ~/.hermes/hermes-agent --yes
```

## 架构

```
Hermes Gateway
  └─ minimal hook in gateway/run.py
       └─ HTTP POST /events ──→  Sidecar (:8765)
                                  ├─ CardSession 状态机
                                  ├─ CardKitRenderer (增量更新元素)
                                  │   └─ FeishuClient.update_card_element()
                                  ├─ IM PATCH 降级
                                  │   └─ FeishuClient.update_card_message()
                                  ├─ /card_action (交互帮助卡片)
                                  │   ├─ Tab 切换 → 新卡片 JSON
                                  │   └─ ▶ 命令执行 → gateway /inject
                                  └─ /health (指标/诊断)
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `setup --hermes-dir ... --yes` | 一键安装（配置 + hook + sidecar） |
| `doctor --config ... --hermes-dir ...` | 诊断 Hermes 兼容性 |
| `install --hermes-dir ... --yes` | 安装 hook |
| `restore --hermes-dir ... --yes` | 恢复原始文件 |
| `start --config ...` | 启动 sidecar |
| `stop --config ...` | 停止 sidecar |
| `status --config ...` | 查看状态和 metrics |
| `bots list\|show\|add\|remove --config ...` | 管理 Bot 注册 |
| `bots bind-chat\|unbind-chat --config ...` | 群聊绑定 |

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| [v0.2.0](https://github.com/1624318455/FStreamingCard/releases/tag/v0.2.0) | 2026-05-19 | CardKit v2.0 元素级更新 + 交互帮助卡片 |
| [v0.1.0](https://github.com/1624318455/FStreamingCard/releases/tag/v0.1.0) | 2026-05-19 | Fork upstream v3.4.1 |
| [upstream v3.4.1](https://github.com/baileyh8/hermes-feishu-streaming-card) | 2026-05 | 原始上游 Sidecar 架构 |

完整更新日志：[CHANGELOG.md](CHANGELOG.md)。

## 与上游的关系

| 项目 | 拿来什么 | 改了什么 |
|------|---------|---------|
| [baileyh8/hermes-feishu-streaming-card](https://github.com/baileyh8/hermes-feishu-streaming-card) | Sidecar 架构、多 Profile、多 Bot、CLI | 渲染层从 IM PATCH 升级到 CardKit v2.0 |
| [Cheerwhy/hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming) | CardKit 卡片构建、流式渲染逻辑 | 从进程内插件搬到 sidecar |
| [feishu-interactive-help-card (Skill)](https://hermes-agent.nousresearch.com) | 交互帮助卡片的构建 + 按钮回调 | 从 feishu.py 搬到 sidecar HTTP API |

## 许可

MIT License
