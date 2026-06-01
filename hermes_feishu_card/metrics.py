from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class SidecarMetrics:
    events_received: int = 0
    events_applied: int = 0
    events_ignored: int = 0
    events_rejected: int = 0
    feishu_send_attempts: int = 0
    feishu_send_successes: int = 0
    feishu_send_failures: int = 0
    feishu_update_attempts: int = 0
    feishu_update_successes: int = 0
    feishu_update_failures: int = 0
    feishu_update_retries: int = 0
    cardkit_deltas_found: int = 0          # 成功计算出有变化的元素
    cardkit_update_successes: int = 0      # 元素级增量更新成功
    cardkit_unsupported: int = 0           # 飞书不支持 CardKit，降级 IM PATCH
    cardkit_update_failures: int = 0       # 元素级更新报错（非不支持），降级 IM PATCH
    cron_cards_sent: int = 0
    cron_fallbacks: int = 0

    def snapshot(self) -> dict[str, int]:
        return asdict(self)
