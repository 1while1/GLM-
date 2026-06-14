from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, time
from typing import Mapping, Sequence

from glm_grabber.config import GrabberConfig


PAYMENT_MARKERS = (
    "支付",
    "二维码",
    "收银台",
    "订单号",
    "确认支付",
    "pay",
    "checkout",
)

PERIOD_LABELS = {
    "month": "连续包月",
    "quarter": "连续包季",
    "year": "连续包年",
}

STATE_LABELS = {
    "READY": "目标可点击，正在尝试订阅",
    "WAITING_FOR_TIME": "已识别目标，等待开抢时间",
    "TARGET_CARD_FOUND": "已找到目标套餐卡片，等待订阅按钮出现",
    "LOGIN_REQUIRED": "等待手动登录",
    "CAPTCHA_REQUIRED": "等待手动验证码",
    "CONFIRM_NOTICE": "检测到订阅提示，准备继续",
    "REQUEST_IN_FLIGHT": "订阅请求处理中",
    "PAYMENT_HANDOFF": "已到支付/最终确认页面，请手动接管",
    "TARGET_MISMATCH": "目标套餐或价格不匹配，已暂停",
    "RECOVERY_RELOAD": "页面拥挤，准备刷新重试",
    "UNKNOWN": "暂未识别到可操作状态",
}

WAIT_REASON_LABELS = {
    "login_required": "等待手动登录",
    "captcha_required": "等待手动验证码",
}


def seconds_until_time_today(start_at: str | None, now: datetime | None = None) -> int:
    if not start_at:
        return 0
    now = now or datetime.now()
    target_time = _parse_time(start_at)
    target = datetime.combine(now.date(), target_time)
    delta = int((target - now).total_seconds())
    return max(0, delta)


def should_handoff(event: Mapping[str, object]) -> bool:
    if str(event.get("state", "")).upper() == "PAYMENT_HANDOFF":
        return True
    haystack = " ".join(str(event.get(key, "")) for key in ("url", "title", "text"))
    lowered = haystack.lower()
    return any(marker.lower() in lowered for marker in PAYMENT_MARKERS)


def describe_page_event(payload: Mapping[str, object]) -> str | None:
    prefix = _page_prefix(payload)
    message: str | None = None
    event = str(payload.get("event", ""))
    data = _as_mapping(payload.get("data"))
    if event == "injector_ready":
        target = _as_mapping(data.get("target"))
        message = "页面脚本已注入；目标：" + _describe_target(target)
    elif event == "state":
        state = str(data.get("state", ""))
        signals = _as_mapping(data.get("signals"))
        label = STATE_LABELS.get(state, f"页面状态：{state}")
        if state == "READY" and _target_has_locked_button(signals):
            message = _append_target_details("已找到灰色补货按钮，尝试解灰点击", signals, separator="：")
        elif state == "RECOVERY_RELOAD":
            message = _append_target_details("页面拥挤，准备刷新重试", signals, separator="：")
        elif state == "WAITING_FOR_TIME" and _target_has_locked_button(signals):
            message = _append_target_details("已找到灰色补货按钮，等待开抢时间", signals, separator="：")
        elif state == "WAITING_FOR_TIME":
            message = _append_target_details("已识别目标，等待开抢时间", signals, separator="：")
        elif state in {"WAITING_FOR_TIME", "READY", "LOGIN_REQUIRED", "CAPTCHA_REQUIRED", "TARGET_CARD_FOUND"}:
            message = _append_target_summary(label, signals)
        else:
            message = label
    elif event == "waiting_manual_action":
        reason = str(data.get("reason", ""))
        signals = _as_mapping(data.get("signals"))
        label = WAIT_REASON_LABELS.get(reason, f"等待手动处理：{reason}")
        message = _append_target_summary(label, signals)
    elif event == "click_attempt":
        attempts = data.get("attempts", "")
        text = str(data.get("text", "")).strip()
        suffix = f"：{text}" if text else ""
        message = f"点击尝试 #{attempts}{suffix}"
    elif event == "period_select_attempt":
        period = PERIOD_LABELS.get(str(data.get("period", "")), str(data.get("period", "")))
        text = str(data.get("text", "")).strip()
        message = f"正在选择周期：{period or text}"
    elif event == "scroll_to_target":
        text = str(data.get("text", "")).strip()
        message = f"已滚动到目标区域：{text}" if text else "已滚动到目标区域"
    elif event == "purchase_request_start":
        message = "已发起订阅相关请求，等待页面响应"
    elif event == "purchase_request_end":
        message = f"订阅相关请求结束，状态码：{data.get('status', '')}"
    if message and prefix:
        return prefix + message
    return message


def public_config_dict(
    config: GrabberConfig,
    *,
    ignore_start_time: bool = False,
    server_time_offset_ms: int = 0,
) -> dict[str, object]:
    data = asdict(config)
    if ignore_start_time:
        data["timing"]["start_at"] = None
    data["timing"]["server_time_offset_ms"] = int(server_time_offset_ms)
    return data


def estimate_server_offset_ms(samples: Sequence[Mapping[str, float | int]]) -> int:
    if not samples:
        return 0
    best = min(samples, key=lambda sample: float(sample["ended_ms"]) - float(sample["started_ms"]))
    midpoint = (float(best["started_ms"]) + float(best["ended_ms"])) / 2
    return int(round(float(best["server_ms"]) - midpoint))


def _parse_time(value: str) -> time:
    parts = value.split(":")
    if len(parts) == 2:
        hour, minute = parts
        second = "0"
    elif len(parts) == 3:
        hour, minute, second = parts
    else:
        raise ValueError("start_at must use HH:MM or HH:MM:SS")
    return time(int(hour), int(minute), int(second))


def _append_target_summary(prefix: str, signals: Mapping[str, object]) -> str:
    return _append_target_details(prefix, signals, separator="；已识别目标：")


def _append_target_details(prefix: str, signals: Mapping[str, object], *, separator: str) -> str:
    summary = _as_mapping(signals.get("targetSummary"))
    if signals.get("targetReady") or summary:
        return f"{prefix}{separator}{_describe_target(summary)}"
    return prefix


def _describe_target(target: Mapping[str, object]) -> str:
    plan = str(target.get("plan", "")).strip()
    period = PERIOD_LABELS.get(str(target.get("period", "")).strip(), str(target.get("period", "")).strip())
    button_text = str(target.get("buttonText", "")).strip()
    parts = [part for part in (plan, period, button_text) if part]
    return " / ".join(parts) if parts else "未配置"


def _target_has_locked_button(signals: Mapping[str, object]) -> bool:
    summary = _as_mapping(signals.get("targetSummary"))
    return bool(summary.get("buttonLocked"))


def _page_prefix(payload: Mapping[str, object]) -> str:
    page_index = payload.get("page_index")
    if not isinstance(page_index, int) or page_index <= 0:
        return ""
    return f"[页面{page_index}] "


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}
