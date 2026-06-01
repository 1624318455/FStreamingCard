from __future__ import annotations

import os
import time
import asyncio
import json
import logging
import re
from typing import Any, Dict
from urllib.parse import quote

from aiohttp import web

from .bots import RouteResult
from .card_action import build_help_card, handle_card_action
from .events import EventValidationError, SidecarEvent
from .feishu_client import CardKitNotSupported
from .metrics import SidecarMetrics
from .render import render_card
from .session import CardSession

FEISHU_CLIENT_KEY = web.AppKey("feishu_client", Any)
SESSIONS_KEY = web.AppKey("sessions", dict)
FEISHU_MESSAGE_IDS_KEY = web.AppKey("feishu_message_ids", dict)
CARD_SUMMARIES_KEY = web.AppKey("card_summaries", dict)
MESSAGE_BOT_IDS_KEY = web.AppKey("message_bot_ids", dict)
SESSION_CARD_CONFIGS_KEY = web.AppKey("session_card_configs", dict)
BOT_ROUTER_KEY = web.AppKey("bot_router", Any)
ROUTING_DIAGNOSTICS_KEY = web.AppKey("routing_diagnostics", dict)
PROFILE_DIAGNOSTICS_KEY = web.AppKey("profile_diagnostics", dict)
PROCESS_TOKEN_KEY = web.AppKey("process_token", str)
METRICS_KEY = web.AppKey("metrics", SidecarMetrics)
LAST_UPDATE_AT_KEY = web.AppKey("last_update_at", dict)
MESSAGE_LOCKS_KEY = web.AppKey("message_locks", dict)
FOOTER_FIELDS_KEY = web.AppKey("footer_fields", Any)
CARD_TITLE_KEY = web.AppKey("card_title", str)
BASE_CARD_CONFIG_KEY = web.AppKey("base_card_config", dict)
LAST_CARD_KEY = web.AppKey("last_card", dict)
CARD_IDS_KEY = web.AppKey("card_ids", dict)  # 新增: session_key -> card_id (CardKit v2.0 卡片实体ID)
CARD_SEQUENCES_KEY = web.AppKey("card_sequences", dict)  # 新增: session_key -> int (流式更新序号)
UPDATE_MAX_ATTEMPTS = 3
UPDATE_MIN_INTERVAL_SECONDS = 0.5
UPDATE_TASKS_KEY = web.AppKey("update_tasks", dict)  # 新增: session_key -> asyncio.Queue，串行化卡片更新
TERMINAL_EVENTS = {"message.completed", "message.failed"}
DIAGNOSTICS_KEY = web.AppKey("diagnostics", dict)
PROFILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
logger = logging.getLogger(__name__)


def create_app(
    feishu_client: Any,
    process_token: str = "",
    card_config: dict[str, Any] | None = None,
    bot_router: Any = None,
) -> web.Application:
    app = web.Application()
    card_config = card_config or {}
    app[FEISHU_CLIENT_KEY] = feishu_client
    app[SESSIONS_KEY] = {}
    app[FEISHU_MESSAGE_IDS_KEY] = {}
    # TODO: replace this short-lived in-process index with bounded shared storage.
    app[CARD_SUMMARIES_KEY] = {}
    app[MESSAGE_BOT_IDS_KEY] = {}
    app[SESSION_CARD_CONFIGS_KEY] = {}
    app[BOT_ROUTER_KEY] = bot_router
    app[PROCESS_TOKEN_KEY] = process_token
    app[METRICS_KEY] = SidecarMetrics()
    app[LAST_UPDATE_AT_KEY] = {}
    app[LAST_CARD_KEY] = {}
    app[CARD_IDS_KEY] = {}  # CardKit card_id per session
    app[CARD_SEQUENCES_KEY] = {}  # CardKit sequence counter per session
    app[MESSAGE_LOCKS_KEY] = {}
    app[UPDATE_TASKS_KEY] = {}  # 新增: 卡片更新任务队列（per-session）
    app[DIAGNOSTICS_KEY] = {
        "last_update_error": "",
        "last_route_error": "",
        "last_terminal_event": {},
    }
    app[ROUTING_DIAGNOSTICS_KEY] = _initial_routing_diagnostics(feishu_client)
    app[PROFILE_DIAGNOSTICS_KEY] = {}
    app[BASE_CARD_CONFIG_KEY] = dict(card_config)
    footer_fields = card_config.get("footer_fields")
    app[FOOTER_FIELDS_KEY] = list(footer_fields) if isinstance(footer_fields, list) else None
    title = card_config.get("title")
    app[CARD_TITLE_KEY] = title if isinstance(title, str) else "Hermes Agent"
    app.router.add_get("/health", _health)
    app.router.add_get("/messages/{message_id}/summary", _message_summary)
    app.router.add_post("/events", _events)
    help_card_cfg = card_config.get("help_card", {})
    if help_card_cfg.get("enabled", False):
        app.router.add_post("/card_action", handle_card_action)
        app.router.add_post("/help", _help)
    return app


async def _health(request: web.Request) -> web.Response:
    sessions: Dict[str, CardSession] = request.app[SESSIONS_KEY]
    metrics: SidecarMetrics = request.app[METRICS_KEY]
    diagnostics = request.app[DIAGNOSTICS_KEY]
    response = {
        "status": "healthy",
        "active_sessions": len(sessions),
        "process_pid": os.getpid(),
        "metrics": metrics.snapshot(),
        "reply_index": {
            "entries": len(request.app[CARD_SUMMARIES_KEY]),
            "last_lookup": diagnostics.get("last_reply_lookup", {}),
        },
        "cron": {
            "cards_sent": metrics.cron_cards_sent,
            "fallbacks": metrics.cron_fallbacks,
        },
        "sessions": {
            message_id: {
                "status": session.status,
                "last_sequence": session.last_sequence,
                "answer_chars": len(session.answer_text),
                "thinking_chars": len(session.thinking_text),
                "tool_count": session.tool_count,
            }
            for message_id, session in sessions.items()
        },
        "diagnostics": diagnostics,
        "routing": request.app[ROUTING_DIAGNOSTICS_KEY],
        "profile_diagnostics": request.app[PROFILE_DIAGNOSTICS_KEY],
    }
    process_token = request.app[PROCESS_TOKEN_KEY]
    if process_token:
        response["process_token"] = process_token

    # Multi-profile stats
    boundary = request.app.get(FEISHU_CLIENT_KEY)
    if isinstance(boundary, dict):
        profile_stats = {}
        for profile_id, factory in boundary.items():
            profile_sessions = {
                k: v for k, v in sessions.items() if k.startswith(f"{profile_id}:")
            }
            profile_stats[profile_id] = {
                "active_sessions": len(profile_sessions),
                "sessions": {
                    key.replace(f"{profile_id}:", ""): {
                        "status": s.status,
                        "last_sequence": s.last_sequence,
                    }
                    for key, s in profile_sessions.items()
                },
            }
        response["profiles"] = profile_stats

    return web.json_response(response)


async def _message_summary(request: web.Request) -> web.Response:
    summaries: Dict[str, dict[str, Any]] = request.app[CARD_SUMMARIES_KEY]
    summary = summaries.get(request.match_info["message_id"])
    if summary is None:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    return web.json_response({"ok": True, **summary})


async def _help(request: web.Request) -> web.Response:
    """处理 /help：构建交互卡片并发送到指定群聊。"""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    chat_id = data.get("chat_id", "")
    tab = data.get("tab", "session")

    if not isinstance(chat_id, str) or not chat_id.strip():
        return web.json_response({"ok": False, "error": "chat_id required"}, status=400)

    card = build_help_card(tab=tab)
    bot_id = _resolve_default_bot_id(request.app)
    message_id = await _send_card(request, chat_id, card, bot_id)
    if message_id is None:
        return web.json_response({"ok": False, "error": "feishu send failed"}, status=502)

    return web.json_response({"ok": True, "card_message_id": message_id})


async def _events(request: web.Request) -> web.Response:
    metrics: SidecarMetrics = request.app[METRICS_KEY]
    try:
        payload = await request.json()
        event = SidecarEvent.from_dict(payload)
    except (EventValidationError, ValueError) as exc:
        metrics.events_rejected += 1
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    metrics.events_received += 1
    message_locks: Dict[str, asyncio.Lock] = request.app[MESSAGE_LOCKS_KEY]
    lock = message_locks.setdefault(_session_key(event), asyncio.Lock())
    async with lock:
        response, post_lock_task = await _apply_event_locked(request, event)
    if post_lock_task is not None:
        await post_lock_task
    return response


def _session_key(event: SidecarEvent) -> str:
    """Return the session key for an event.

    When profiles are active, uses composite key profile_id:message_id.
    Otherwise uses message_id directly (backward compatible).
    """
    has_profile_id = isinstance(event.data, dict) and "profile_id" in event.data
    profile_id = _safe_profile_id(event.data.get("profile_id") if has_profile_id else None)
    if has_profile_id:
        return f"{profile_id}:{event.message_id}"
    return event.message_id


async def _apply_event_locked(request: web.Request, event: SidecarEvent) -> tuple[web.Response, Any]:
    """Process event state inside the lock. Returns (response, post_lock_task).

    post_lock_task is a coroutine that performs Feishu API calls outside the lock
    to avoid blocking subsequent event processing.
    """
    metrics: SidecarMetrics = request.app[METRICS_KEY]
    sessions: Dict[str, CardSession] = request.app[SESSIONS_KEY]
    feishu_message_ids: Dict[str, str] = request.app[FEISHU_MESSAGE_IDS_KEY]
    message_bot_ids: Dict[str, str] = request.app[MESSAGE_BOT_IDS_KEY]
    last_update_at: Dict[str, float] = request.app[LAST_UPDATE_AT_KEY]
    _record_profile_diagnostics(request.app, event)
    session = sessions.get(_session_key(event))

    if event.event == "message.started":
        if session is not None:
            metrics.events_ignored += 1
            return web.json_response({"ok": True, "applied": False}), None
        session = CardSession(
            conversation_id=event.conversation_id,
            message_id=event.message_id,
            chat_id=event.chat_id,
            show_reasoning=False,
        )
        sessions[_session_key(event)] = session
        applied = session.apply(event)
        if applied and _session_key(event) not in feishu_message_ids:
            route = _resolve_route(request, event)
            if route is None:
                sessions.pop(_session_key(event), None)
                metrics.events_rejected += 1
                return web.json_response(
                    {"ok": False, "error": "bot route failed"},
                    status=502,
                ), None
            request.app[SESSION_CARD_CONFIGS_KEY][_session_key(event)] = (
                _resolve_session_card_config(request.app, route.bot_id, event)
            )
            initial_card = _render_session_card(request, session)
            message_id = await _send_card(
                request,
                event.chat_id,
                initial_card,
                route.bot_id,
                session_key=_session_key(event),
            )
            if message_id is None:
                sessions.pop(_session_key(event), None)
                request.app[SESSION_CARD_CONFIGS_KEY].pop(_session_key(event), None)
                metrics.events_rejected += 1
                return web.json_response(
                    {"ok": False, "error": "feishu send failed"},
                    status=502,
                ), None
            feishu_message_ids[_session_key(event)] = message_id
            message_bot_ids[_session_key(event)] = route.bot_id
            request.app[LAST_CARD_KEY][_session_key(event)] = initial_card
            request.app[CARD_SEQUENCES_KEY][_session_key(event)] = 0  # CardKit 序号从 0 开始
        if applied:
            metrics.events_applied += 1
        else:
            metrics.events_ignored += 1
        return web.json_response({"ok": True, "applied": applied}), None

    if session is None:
        if event.event == "message.completed" and _delivery_kind(event) == "cron":
            session = CardSession(
                conversation_id=event.conversation_id,
                message_id=event.message_id,
                chat_id=event.chat_id,
            )
            sessions[_session_key(event)] = session
            applied = session.apply(event)
            if applied:
                route = _resolve_route(request, event)
                if route is None:
                    sessions.pop(_session_key(event), None)
                    metrics.cron_fallbacks += 1
                    metrics.events_rejected += 1
                    return web.json_response(
                        {"ok": False, "error": "bot route failed"},
                        status=502,
                    ), None
                request.app[SESSION_CARD_CONFIGS_KEY][_session_key(event)] = (
                    _resolve_session_card_config(request.app, route.bot_id, event)
                )
                cron_card = _render_session_card(request, session)
                message_id = await _send_card(
                    request,
                    event.chat_id,
                    cron_card,
                    route.bot_id,
                    session_key=_session_key(event),
                )
                if message_id is None:
                    sessions.pop(_session_key(event), None)
                    request.app[SESSION_CARD_CONFIGS_KEY].pop(_session_key(event), None)
                    metrics.cron_fallbacks += 1
                    metrics.events_rejected += 1
                    return web.json_response(
                        {"ok": False, "error": "feishu send failed"},
                        status=502,
                    ), None
                feishu_message_ids[_session_key(event)] = message_id
                message_bot_ids[_session_key(event)] = route.bot_id
                request.app[LAST_CARD_KEY][_session_key(event)] = cron_card
                request.app[CARD_SEQUENCES_KEY][_session_key(event)] = 0
                _store_card_summary(request.app, event, session, message_id)
                request.app[DIAGNOSTICS_KEY]["last_terminal_event"] = {
                    "message_id": event.message_id,
                    "event": event.event,
                    "sequence": event.sequence,
                    "applied": applied,
                    "session_status": session.status,
                    "answer_chars": len(session.answer_text),
                }
                metrics.events_applied += 1
                metrics.cron_cards_sent += 1
            else:
                metrics.events_ignored += 1
            return web.json_response({"ok": True, "applied": applied}), None
        metrics.events_ignored += 1
        return web.json_response({"ok": True, "applied": False}), None

    feishu_message_id = feishu_message_ids.get(_session_key(event))
    if _would_apply(session, event) and feishu_message_id is None:
        metrics.events_rejected += 1
        return web.json_response(
            {"ok": False, "error": "feishu_message_id missing"},
            status=409,
        ), None

    applied = session.apply(event)
    if event.event in TERMINAL_EVENTS:
        request.app[DIAGNOSTICS_KEY]["last_terminal_event"] = {
            "message_id": event.message_id,
            "event": event.event,
            "sequence": event.sequence,
            "applied": applied,
            "session_status": session.status,
            "answer_chars": len(session.answer_text),
        }
    post_lock_task = None
    if applied and feishu_message_id is not None:
        if event.event in TERMINAL_EVENTS:
            _store_card_summary(request.app, event, session, feishu_message_id)
        should_update = _should_update_card(last_update_at, event)
        if should_update:
            # 锁内立即标记，防止后续事件在API完成前重复触发更新
            last_update_at[_session_key(event)] = time.monotonic()
            bot_id = message_bot_ids.get(_session_key(event))
            is_terminal = event.event in TERMINAL_EVENTS
            _session_key_str = _session_key(event)  # 缓存避免重复调用

            async def _do_update():
                if is_terminal:
                    delay = _update_delay_seconds(last_update_at, event)
                    if delay > 0:
                        await asyncio.sleep(delay)
                # 运行时重新渲染卡片，避免闭包捕获过期快照导致的竞态
                current_card = _render_session_card(request, session)
                updated = await _update_card_for_app(
                    request.app, feishu_message_id, current_card, bot_id,
                    session_key=_session_key_str,
                )
                if not updated and is_terminal:
                    await _retry_terminal_update(
                        request.app, feishu_message_id, current_card, bot_id,
                        session_key=_session_key_str,
                    )

            post_lock_task = _do_update()
    if applied:
        metrics.events_applied += 1
    else:
        metrics.events_ignored += 1
    return web.json_response({"ok": True, "applied": applied}), post_lock_task


def _store_card_summary(
    app: web.Application,
    event: SidecarEvent,
    session: CardSession,
    feishu_message_id: str,
) -> None:
    summary = session.answer_text.strip()
    if not summary:
        return
    data = event.data if isinstance(event.data, dict) else {}
    profile_id = _safe_profile_id(data.get("profile_id"))
    app[CARD_SUMMARIES_KEY][feishu_message_id] = {
        "summary": summary[:4000],
        "profile_id": profile_id,
        "chat_id": event.chat_id,
        "message_id": feishu_message_id,
    }


def _record_profile_diagnostics(app: web.Application, event: SidecarEvent) -> None:
    data = event.data if isinstance(event.data, dict) else {}
    profile_id = _safe_profile_id(data.get("profile_id"))
    source = str(data.get("profile_source") or "")
    diagnostics = app[PROFILE_DIAGNOSTICS_KEY].setdefault(
        profile_id,
        {"events": 0, "last_profile_source": "", "last_message_id": ""},
    )
    diagnostics["events"] += 1
    diagnostics["last_profile_source"] = source
    diagnostics["last_message_id"] = event.message_id


def _delivery_kind(event: SidecarEvent) -> str:
    data = event.data if isinstance(event.data, dict) else {}
    return str(data.get("delivery_kind") or "").strip().lower()


def _safe_profile_id(value: Any) -> str:
    candidate = str(value or "").strip()
    if PROFILE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return "default"


def _render_session_card(request: web.Request, session: CardSession) -> dict[str, Any]:
    card_config = request.app[SESSION_CARD_CONFIGS_KEY].get(
        _session_key_for_session(request.app, session),
        {},
    )
    footer_fields = card_config.get("footer_fields", request.app[FOOTER_FIELDS_KEY])
    if isinstance(footer_fields, list):
        footer_fields = list(footer_fields)
    elif footer_fields is not None:
        footer_fields = request.app[FOOTER_FIELDS_KEY]
    title = card_config.get("title", request.app[CARD_TITLE_KEY])
    if not isinstance(title, str):
        title = request.app[CARD_TITLE_KEY]
    return render_card(
        session,
        footer_fields=footer_fields,
        title=title,
    )


def _session_key_for_session(app: web.Application, session: CardSession) -> str:
    for key, candidate in app[SESSIONS_KEY].items():
        if candidate is session:
            return key
    return session.message_id


def _resolve_session_card_config(
    app: web.Application, bot_id: str | None, event: SidecarEvent
) -> dict[str, Any]:
    base_card = app[BASE_CARD_CONFIG_KEY]
    profile_card = event.data.get("card", {}) if isinstance(event.data, dict) else {}
    actual_bot_id = bot_id
    feishu_client = app[FEISHU_CLIENT_KEY]
    if isinstance(feishu_client, dict):
        profile_id = "default"
        if isinstance(bot_id, str) and ":" in bot_id:
            profile_id, actual_bot_id = bot_id.split(":", 1)
        factory = feishu_client.get(profile_id) or feishu_client.get("default")
        if factory is not None:
            return _card_config_for_client(factory, actual_bot_id, base_card, profile_card)
        return dict(base_card)
    return _card_config_for_client(feishu_client, actual_bot_id, base_card, profile_card)


def _card_config_for_client(
    feishu_client: Any,
    bot_id: str | None,
    base_card: dict[str, Any],
    profile_card: dict[str, Any],
) -> dict[str, Any]:
    resolver = getattr(feishu_client, "card_config_for_bot", None)
    if callable(resolver) and bot_id:
        try:
            return resolver(bot_id, base_card=base_card, profile_card=profile_card)
        except Exception:
            return dict(base_card)
    resolved = dict(base_card)
    if isinstance(profile_card, dict):
        resolved.update(profile_card)
    return resolved


async def _send_card(
    request: web.Request, chat_id: str, card: dict[str, Any], bot_id: str | None,
    session_key: str | None = None,
) -> str | None:
    """发送卡片。优先使用 CardKit v2.0 实体创建+发送，降级到旧方式。"""
    metrics: SidecarMetrics = request.app[METRICS_KEY]
    metrics.feishu_send_attempts += 1
    try:
        client = _client_for_bot(request.app, bot_id)
        # CardKit v2.0: 创建卡片实体
        card_id = await client.create_card_entity(card)
        # 通过 card_id 发送消息
        message_id = await client.send_card_entity(chat_id, card_id)
        # 保存 card_id 到 session (如果有 session_key)
        if session_key:
            request.app[CARD_IDS_KEY][session_key] = card_id
        metrics.feishu_send_successes += 1
        return message_id
    except Exception:
        # 降级：旧方式直接发送卡片 JSON
        try:
            client = _client_for_bot(request.app, bot_id)
            message_id = await client.send_card(chat_id, card)
            metrics.feishu_send_successes += 1
            return message_id
        except Exception:
            metrics.feishu_send_failures += 1
            return None


async def _update_card(
    request: web.Request, message_id: str, card: dict[str, Any], bot_id: str | None
) -> bool:
    return await _update_card_for_app(request.app, message_id, card, bot_id)


async def _update_card_for_app(
    app: web.Application, message_id: str, card: dict[str, Any], bot_id: str | None,
    session_key: str | None = None,
) -> bool:
    metrics: SidecarMetrics = app[METRICS_KEY]
    card_id = app[CARD_IDS_KEY].get(session_key) if session_key else None
    cardkit_ok = False

    # CardKit v2.0: 流式更新文本元素（打字机效果）
    if card_id and session_key:
        last_card = app[LAST_CARD_KEY].get(session_key)
        if last_card is not None:
            deltas = _compute_element_deltas(last_card, card)
            if deltas:
                metrics.cardkit_deltas_found += 1
                try:
                    client = _client_for_bot(app, bot_id)
                    seq = app[CARD_SEQUENCES_KEY].get(session_key, 0) + 1
                    for element_id, content in deltas.items():
                        if element_id in ("tool_summary", "footer", "main_divider", "attachment_summary"):
                            # content-only 更新用 put content；非文本元素跳过流式
                            continue
                        await client.streaming_update_text(card_id, element_id, content, seq)
                        seq += 1
                    app[CARD_SEQUENCES_KEY][session_key] = seq - 1
                    app[LAST_CARD_KEY][session_key] = card
                    metrics.cardkit_update_successes += 1
                    cardkit_ok = True
                except Exception as exc:
                    metrics.cardkit_update_failures += 1
                    logger.warning("CardKit streaming update failed: %s", exc)

    # CardKit 整卡更新（PUT /cardkit/v1/cards/:card_id）
    if not cardkit_ok and card_id:
        try:
            client = _client_for_bot(app, bot_id)
            seq = app[CARD_SEQUENCES_KEY].get(session_key, 0) + 1
            await client.update_card_entity(card_id, card, seq)
            app[CARD_SEQUENCES_KEY][session_key] = seq
            app[LAST_CARD_KEY][session_key] = card
            metrics.feishu_update_successes += 1
            return True
        except Exception as exc:
            logger.warning("CardKit full update failed, falling back to IM PATCH: %s", exc)

    # 最终降级：IM PATCH 整卡替换
    for attempt in range(UPDATE_MAX_ATTEMPTS):
        if attempt > 0:
            metrics.feishu_update_retries += 1
        metrics.feishu_update_attempts += 1
        try:
            await _client_for_bot(app, bot_id).update_card_message(message_id, card)
        except Exception as exc:
            message = _safe_update_error_message(bot_id, exc)
            app[DIAGNOSTICS_KEY]["last_update_error"] = message[:500]
            logger.warning("Feishu card update failed: %s", message)
            metrics.feishu_update_failures += 1
            continue
        metrics.feishu_update_successes += 1
        if session_key:
            app[LAST_CARD_KEY][session_key] = card
        return True
    return False


async def _retry_terminal_update(
    app: web.Application, message_id: str, card: dict[str, Any], bot_id: str | None,
    session_key: str | None = None,
) -> None:
    for delay in (1.0, 2.0, 4.0):
        await asyncio.sleep(delay)
        if await _update_card_for_app(app, message_id, card, bot_id, session_key=session_key):
            return


def _resolve_route(request: web.Request, event: SidecarEvent) -> RouteResult | None:
    feishu_client = request.app[FEISHU_CLIENT_KEY]
    diagnostics = request.app[ROUTING_DIAGNOSTICS_KEY]
    app_diagnostics = request.app[DIAGNOSTICS_KEY]

    # 记录当前 profile_id（多 profile 模式下需要注入到 route.bot_id）
    current_profile_id: str | None = None

    # Multi-profile: select profile-specific factory
    if isinstance(feishu_client, dict):
        raw_profile_id = event.data.get("profile_id") if isinstance(event.data, dict) else None
        current_profile_id = _safe_profile_id(raw_profile_id)
        factory = feishu_client.get(current_profile_id) or feishu_client.get("default")
        if factory is None:
            diagnostics["last_route_error"] = f"no factory for profile {current_profile_id}"
            return None
        feishu_client = factory

    if not _is_client_factory(feishu_client):
        diagnostics["last_route"] = {
            "message_id": event.message_id,
            "chat_id": event.chat_id,
            "bot_id": "",
            "reason": "legacy",
        }
        diagnostics["last_route_error"] = ""
        app_diagnostics["last_route_error"] = ""
        return RouteResult("", "legacy")

    bot_router = request.app[BOT_ROUTER_KEY]
    try:
        route = _coerce_route_result(bot_router(event))
        feishu_client.get_client(route.bot_id)
    except Exception as exc:
        safe_error = exc.__class__.__name__
        diagnostics["last_route_error"] = safe_error
        app_diagnostics["last_route_error"] = safe_error
        diagnostics["last_route"] = {}
        return None

    diagnostics["last_route"] = {
        "message_id": event.message_id,
        "chat_id": event.chat_id,
        "bot_id": route.bot_id,
        "reason": route.reason,
    }
    diagnostics["last_route_error"] = ""
    app_diagnostics["last_route_error"] = ""
    # 多 profile 模式：将 profile_id 注入 bot_id，以便 _client_for_bot 正确路由
    if current_profile_id is not None:
        route = RouteResult(f"{current_profile_id}:{route.bot_id}", route.reason)
    return route


def _coerce_route_result(value: Any) -> RouteResult:
    if isinstance(value, RouteResult):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        bot_id, reason = value
        return RouteResult(str(bot_id), str(reason))
    raise TypeError("bot_router must return RouteResult or (bot_id, reason)")


def _client_for_bot(app: web.Application, bot_id: str | None) -> Any:
    feishu_client = app[FEISHU_CLIENT_KEY]
    # Multi-profile: feishu_client is a dict keyed by profile -> factory
    if isinstance(feishu_client, dict):
        if bot_id is None:
            # Use default profile's default bot
            factory = feishu_client.get("default")
            if factory is None:
                raise RuntimeError("no default profile factory")
            return factory.get_client("default")
        # bot_id format: "profile_id:bot_id" or just "bot_id"
        if ":" in str(bot_id):
            profile_id, actual_bot_id = str(bot_id).split(":", 1)
        else:
            profile_id, actual_bot_id = "default", str(bot_id)
        factory = feishu_client.get(profile_id)
        if factory is None:
            raise RuntimeError(f"no factory for profile {profile_id}")
        return factory.get_client(actual_bot_id)

    if _is_client_factory(feishu_client):
        if bot_id is None:
            raise RuntimeError("bot id missing")
        return feishu_client.get_client(bot_id)
    return feishu_client


def _is_client_factory(feishu_client: Any) -> bool:
    return callable(getattr(feishu_client, "get_client", None))


def _resolve_default_bot_id(app: web.Application) -> str | None:
    """Resolve the default bot_id from the bot registry."""
    feishu_client = app[FEISHU_CLIENT_KEY]
    if isinstance(feishu_client, dict):
        factory = feishu_client.get("default")
        if factory is not None:
            registry = getattr(factory, "registry", None)
            if registry is not None:
                default_bot = getattr(registry, "default_bot_id", "")
                if default_bot:
                    return f"default:{default_bot}"
        return "default:default"
    if _is_client_factory(feishu_client):
        registry = getattr(feishu_client, "registry", None)
        if registry is not None:
            default_bot = getattr(registry, "default_bot_id", "")
            if default_bot:
                return default_bot
    return None


def _safe_update_error_message(bot_id: str | None, exc: Exception) -> str:
    return f"bot_id={bot_id or ''} {exc.__class__.__name__}"


def _initial_routing_diagnostics(feishu_client: Any) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "default_bot": "",
        "bot_count": 0,
        "chat_binding_count": 0,
        "last_route": {},
        "last_route_error": "",
    }
    registry = getattr(feishu_client, "registry", None)
    safe_diagnostics = getattr(registry, "safe_diagnostics", None)
    if callable(safe_diagnostics):
        try:
            diagnostics.update(_sanitize_routing_diagnostics(safe_diagnostics()))
        except Exception as exc:
            diagnostics["last_route_error"] = exc.__class__.__name__
    for key in ("default_bot", "bot_count", "chat_binding_count"):
        diagnostics.setdefault(key, "" if key == "default_bot" else 0)
    diagnostics.setdefault("last_route", {})
    diagnostics.setdefault("last_route_error", "")
    return diagnostics


def _sanitize_routing_diagnostics(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                continue
            sanitized[key_text] = _sanitize_routing_diagnostics(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_routing_diagnostics(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in ("secret", "token", "password", "key"))


def _would_apply(session: CardSession, event: SidecarEvent) -> bool:
    return (
        event.conversation_id == session.conversation_id
        and event.message_id == session.message_id
        and event.chat_id == session.chat_id
        and event.sequence > session.last_sequence
        and session.status not in {"completed", "failed"}
    )


def _should_update_card(last_update_at: Dict[str, float], event: SidecarEvent) -> bool:
    if event.event in TERMINAL_EVENTS:
        return True
    previous = last_update_at.get(_session_key(event))
    if previous is None:
        return True
    return time.monotonic() - previous >= UPDATE_MIN_INTERVAL_SECONDS


def _compute_element_deltas(old_card: dict[str, Any], new_card: dict[str, Any]) -> dict[str, str]:
    """Compute changed elements between old and new CardKit v2.0 cards.

    Returns a dict of element_id → new_content for elements that changed.
    Returns empty dict if no changes or if card structure is incompatible.
    """
    old_body = old_card.get("body")
    new_body = new_card.get("body")
    if not isinstance(old_body, dict) or not isinstance(new_body, dict):
        return {}
    old_elements = old_body.get("elements", [])
    new_elements = new_body.get("elements", [])
    if not isinstance(old_elements, list) or not isinstance(new_elements, list):
        return {}
    old_map: dict[str, str] = {}
    for el in old_elements:
        if isinstance(el, dict) and el.get("element_id") and isinstance(el.get("content"), str):
            old_map[el["element_id"]] = el["content"]
    deltas: dict[str, str] = {}
    for el in new_elements:
        if not isinstance(el, dict):
            continue
        eid = el.get("element_id")
        content = el.get("content")
        if not eid or not isinstance(content, str):
            continue
        if old_map.get(eid) != content:
            deltas[eid] = content
    return deltas


def _update_delay_seconds(last_update_at: Dict[str, float], event: SidecarEvent) -> float:
    if event.event not in TERMINAL_EVENTS:
        return 0.0
    previous = last_update_at.get(_session_key(event))
    if previous is None:
        return 0.0
    return max(0.0, UPDATE_MIN_INTERVAL_SECONDS - (time.monotonic() - previous))
