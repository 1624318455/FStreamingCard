# FStreamingCard

> Fork of [baileyh8/hermes-feishu-streaming-card](https://github.com/baileyh8/hermes-feishu-streaming-card) v3.4.1, integrating [Cheerwhy/hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming) CardKit v2.0 streaming rendering.

Feishu/Lark Streaming Card Sidecar for Hermes Agent Gateway, featuring CardKit v2.0 element-level incremental updates, interactive help card, multi-profile / multi-bot support.

---

## Core Capabilities

| Capability | Status | Description |
|-----------|--------|-------------|
| CardKit v2.0 element-level update | ✅ v0.2.0 | 100ms interval, delta-only, true typewriter effect |
| IM PATCH fallback | ✅ v0.2.0 | Automatic fallback to full card replacement |
| Interactive help card | ✅ v0.2.0 | 4 Tab switch + ▶ command inject |
| Multi-profile isolation | ✅ upstream v3.3+ | Single sidecar serving multiple Hermes instances |
| Multi-bot routing | ✅ upstream v3.2+ | Per-chat bot routing |
| Streaming thinking display | ✅ upstream | Incremental thinking/answer rendering |
| Tool call tracking | ✅ upstream | Cumulative call count and status |
| Footer statistics | ✅ upstream | Duration/model/tokens/context |
| Table overflow protection | ✅ upstream | Auto-truncate beyond 5 tables |
| Cron final cards | ✅ upstream | Scheduled task terminal cards |

Full changelog: [CHANGELOG.md](CHANGELOG.md).

## Quick Install

```bash
git clone https://github.com/1624318455/FStreamingCard.git
cd FStreamingCard && pip install -e ".[test]"
export FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=xxx
python3 -m hermes_feishu_card.cli setup --hermes-dir ~/.hermes/hermes-agent --yes
```

## License

MIT License
