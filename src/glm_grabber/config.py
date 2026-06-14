from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


VALID_PLANS = {"Lite", "Pro", "Max"}
VALID_PERIODS = {"month", "quarter", "year"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TargetConfig:
    plan: str
    period: str
    expected_price_text: str | None = None
    button_selector: str | None = None


@dataclass(frozen=True)
class PageConfig:
    url: str


@dataclass(frozen=True)
class TimingConfig:
    start_at: str | None = None
    normal_check_interval_ms: int = 200
    armed_check_interval_ms: int = 20
    armed_before_seconds: int = 0
    armed_after_seconds: int = 120
    click_cooldown_ms: int = 80
    max_click_attempts: int = 0
    crowd_retry_clicks_before_reload: int = 15
    recovery_reload_interval_ms: int = 1500
    server_time_sync: bool = True
    server_time_samples: int = 5
    t0_reload: bool = False


@dataclass(frozen=True)
class SafetyConfig:
    stop_before_payment: bool = True
    auto_continue_notice: bool = True
    force_unlock: bool = True
    replay_requests: bool = False
    screenshot_on_handoff: bool = True
    beep_on_handoff: bool = True
    pause_on_unknown: bool = True


@dataclass(frozen=True)
class BrowserConfig:
    user_data_dir: str = ".browser-profile"
    headless: bool = False
    slow_mo_ms: int = 0
    parallel_pages: int = 3


@dataclass(frozen=True)
class LoggingConfig:
    dir: str = "logs"
    screenshots_dir: str = "screenshots"


@dataclass(frozen=True)
class GrabberConfig:
    target: TargetConfig
    page: PageConfig
    timing: TimingConfig = field(default_factory=TimingConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(path: str | Path) -> GrabberConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Config must be a YAML mapping")

    target_raw = _section(raw, "target")
    page_raw = _section(raw, "page")
    timing_raw = _optional_section(raw, "timing")
    safety_raw = _optional_section(raw, "safety")
    browser_raw = _optional_section(raw, "browser")
    logging_raw = _optional_section(raw, "logging")

    target = TargetConfig(
        plan=_required_str(target_raw, "plan"),
        period=_required_str(target_raw, "period"),
        expected_price_text=_optional_str(target_raw, "expected_price_text"),
        button_selector=_optional_str(target_raw, "button_selector"),
    )
    if target.plan not in VALID_PLANS:
        raise ConfigError(f"target.plan must be one of {sorted(VALID_PLANS)}")
    if target.period not in VALID_PERIODS:
        raise ConfigError(f"target.period must be one of {sorted(VALID_PERIODS)}")

    page = PageConfig(url=_required_str(page_raw, "url"))
    timing = TimingConfig(**_filter_keys(timing_raw, TimingConfig))
    safety = SafetyConfig(**_filter_keys(safety_raw, SafetyConfig))
    browser = BrowserConfig(**_filter_keys(browser_raw, BrowserConfig))
    logging = LoggingConfig(**_filter_keys(logging_raw, LoggingConfig))

    _validate_timing(timing)
    _validate_browser(browser)
    if safety.replay_requests:
        raise ConfigError("safety.replay_requests is disabled in v1")

    return GrabberConfig(
        target=target,
        page=page,
        timing=timing,
        safety=safety,
        browser=browser,
        logging=logging,
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing required section: {name}")
    return value


def _optional_section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Section {name} must be a mapping")
    return value


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"Missing required string: {key}")
    return value


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{key} must be a non-empty string")
    return value


def _filter_keys(raw: dict[str, Any], cls: type) -> dict[str, Any]:
    allowed = cls.__dataclass_fields__.keys()
    unknown = set(raw) - set(allowed)
    if unknown:
        raise ConfigError(f"Unknown keys for {cls.__name__}: {sorted(unknown)}")
    return dict(raw)


def _validate_timing(timing: TimingConfig) -> None:
    positive_fields = [
        "normal_check_interval_ms",
        "armed_check_interval_ms",
        "armed_after_seconds",
        "click_cooldown_ms",
        "crowd_retry_clicks_before_reload",
        "recovery_reload_interval_ms",
        "server_time_samples",
    ]
    for field_name in positive_fields:
        value = getattr(timing, field_name)
        if not isinstance(value, int) or value <= 0:
            raise ConfigError(f"timing.{field_name} must be a positive integer")
    if not isinstance(timing.armed_before_seconds, int) or timing.armed_before_seconds < 0:
        raise ConfigError("timing.armed_before_seconds must be zero or a positive integer")
    if not isinstance(timing.max_click_attempts, int) or timing.max_click_attempts < 0:
        raise ConfigError("timing.max_click_attempts must be zero or a positive integer")


def _validate_browser(browser: BrowserConfig) -> None:
    if not isinstance(browser.parallel_pages, int) or not 1 <= browser.parallel_pages <= 8:
        raise ConfigError("browser.parallel_pages must be an integer from 1 to 8")
