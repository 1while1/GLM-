from __future__ import annotations

from enum import Enum
from typing import Mapping


class GrabberState(str, Enum):
    PAYMENT_HANDOFF = "PAYMENT_HANDOFF"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    REQUEST_IN_FLIGHT = "REQUEST_IN_FLIGHT"
    CONFIRM_NOTICE = "CONFIRM_NOTICE"
    READY = "READY"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    UNKNOWN = "UNKNOWN"


def classify_signals(signals: Mapping[str, object]) -> GrabberState:
    if _truthy(signals, "payment"):
        return GrabberState.PAYMENT_HANDOFF
    if _truthy(signals, "captcha"):
        return GrabberState.CAPTCHA_REQUIRED
    if _truthy(signals, "login"):
        return GrabberState.LOGIN_REQUIRED
    if _truthy(signals, "target_mismatch"):
        return GrabberState.TARGET_MISMATCH
    if _truthy(signals, "request_in_flight"):
        return GrabberState.REQUEST_IN_FLIGHT
    if _truthy(signals, "confirm_notice"):
        return GrabberState.CONFIRM_NOTICE
    if _truthy(signals, "target_ready") and _truthy(signals, "button_enabled"):
        return GrabberState.READY
    if _truthy(signals, "retryable_failure"):
        return GrabberState.RETRYABLE_FAILURE
    return GrabberState.UNKNOWN


def _truthy(signals: Mapping[str, object], key: str) -> bool:
    return bool(signals.get(key))
