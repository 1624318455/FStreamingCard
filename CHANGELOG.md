# Changelog

## [0.3.0] — 2026-05-27

### Added
- `feishu_client.py`: `create_card_entity()`, `send_card_entity()`, `streaming_update_text()`, `update_card_entity()` — CardKit v2.0 正确 API（`/cardkit/v1/cards/*`）
- `render.py`: `streaming_config` (70ms frequency, step=1, fast strategy) 控制打字机效果
- `server.py`: `CARD_IDS_KEY`, `CARD_SEQUENCES_KEY` 跟踪卡片实体和流式序号
- `hook_runtime.py`: `_SEQUENCE_LOCK` 线程安全锁，防止多线程重复序号
- FStreamingCard.vbs 开机自启脚本

### Changed
- `server.py/_send_card()`: 优先走 CardKit 实体创建+发送，降级到旧方式
- `server.py/_update_card_for_app()`: 三级降级 — 流式文本更新 → 整卡实体更新 → IM PATCH
- `server.py/_do_update()`: 运行时重新渲染卡片，消除闭包捕获过期快照导致的竞态
- `server.py`: 新增 `import json`, `from urllib.parse import quote`

### Fixed
- `server.py`: `update_card_element` 使用错误 API 路径的问题（旧: `/im/v1/.../update_card_element` → 新: `/cardkit/v1/cards/{id}/elements/{id}/content`）
- `hook_runtime.py`: `_next_sequence()` 非线程安全的读写竞争

## [0.2.0] — 2026-05-19

### Added
- `feishu_client.py`: `update_card_element()` method for CardKit v2.0 element-level incremental updates
  - Raises `CardKitNotSupported` when the API indicates the target doesn't support element updates
  - Falls back gracefully to full card PATCH via existing `update_card_message()`
- `card_action.py`: Interactive help card module with 4 Tab categories (对话命令 / CLI 配置 / 技能与扩展 / 平台与自动化)
  - Tab switching via button clicks, returning new card JSON
  - Command execution (▶ button) via gateway API `/inject`
- `server.py`: `/card_action` route wired to `handle_card_action`
- `server.py`: Element-level update optimization in `_update_card_for_app`
  - Computes element deltas via `_compute_element_deltas()` comparing old vs new card
  - Sends only changed elements via CardKit API; falls back to full PATCH on failure or unsupported
  - `LAST_CARD_KEY` tracks the last card state per session for delta computation
- `CLAUDE.md`: Project memory file for AI agent collaboration

### Fixed
- `server.py`: `_render_session_card()` result captured as `initial_card` variable before being passed to both `_send_card` and `LAST_CARD_KEY` storage

## [0.1.0] — 2026-05-19

Fork from [baileyh8/hermes-feishu-streaming-card](https://github.com/baileyh8/hermes-feishu-streaming-card) v3.4.1.

- Upstream merge: multi-bot routing, CardKit v2.0 table truncation, braille spinner, profile support, cron card support
- AGENTS.md design doc outlining the fork's three core capabilities (CardKit streaming, interactive help card, multi-bot multi-profile)

## [0.0.1] — 2026-05-19

- Initial project scaffold with AGENTS.md implementation plan
