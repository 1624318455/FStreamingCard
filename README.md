# FStreamingCard

Hermes Agent Gateway 的飞书流式卡片 Sidecar。

在 [baileyh8/hermes-feishu-streaming-card](https://github.com/baileyh8/hermes-feishu-streaming-card) 基础上改进，融合 [Cheerwhy/hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming) 的 CardKit v2.0 流式渲染，实现真打字机效果。

### 三大能力

- **CardKit v2.0 流式渲染** — 增量更新元素，100ms 间隔，真打字机效果（降级 IM PATCH 整卡替换）
- **交互帮助卡片** — Tab 切换 + ▶ 命令执行
- **多 Profile / 多 Bot** — 一个 sidecar 服务多个 Hermes 实例

### 架构

```
Hermes Gateway ← HTTP POST → Sidecar (:8765)
                                  ├── CardKit v2.0 增量更新
                                  ├── IM PATCH 降级
                                  └── 交互帮助卡片
```

详细设计见 [AGENTS.md](./AGENTS.md)。
