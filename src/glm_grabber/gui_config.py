from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml


STATUS_PREFIXES = (
    ("等待手动验证码", "等待手动验证码"),
    ("等待手动登录", "等待手动登录"),
    ("已找到灰色补货按钮，尝试解灰点击", "正在解灰点击"),
    ("已找到灰色补货按钮，等待开抢时间", "等待开抢时间"),
    ("页面拥挤，准备刷新重试", "刷新重试中"),
    ("正在刷新页面重试", "刷新重试中"),
    ("已识别目标，等待开抢时间", "等待开抢时间"),
    ("目标可点击，正在尝试订阅", "正在尝试订阅"),
    ("点击尝试", "正在点击订阅"),
    ("已滚动到目标区域", "已定位目标区域"),
    ("已到支付/最终确认页面", "请手动接管支付"),
    ("浏览器已打开", "运行中"),
    ("页面脚本已注入", "监控已注入"),
)


def update_config_file(
    path: str | Path,
    *,
    plan: str,
    period: str,
    button_selector: str | None,
    start_at: str | None,
    force_unlock: bool,
    parallel_pages: int,
    armed_before_seconds: int,
    armed_after_seconds: int,
    click_cooldown_ms: int,
    max_click_attempts: int,
    crowd_retry_clicks_before_reload: int,
    recovery_reload_interval_ms: int,
    server_time_sync: bool,
    server_time_samples: int,
    t0_reload: bool,
) -> None:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        data = {}

    target = _section(data, "target")
    timing = _section(data, "timing")
    safety = _section(data, "safety")
    browser = _section(data, "browser")

    target["plan"] = plan
    target["period"] = period
    target["button_selector"] = _normalize_optional_text(button_selector)
    timing["start_at"] = _normalize_start_time(start_at)
    timing["armed_before_seconds"] = int(armed_before_seconds)
    timing["armed_after_seconds"] = int(armed_after_seconds)
    timing["click_cooldown_ms"] = int(click_cooldown_ms)
    timing["max_click_attempts"] = int(max_click_attempts)
    timing["crowd_retry_clicks_before_reload"] = int(crowd_retry_clicks_before_reload)
    timing["recovery_reload_interval_ms"] = int(recovery_reload_interval_ms)
    timing["server_time_sync"] = bool(server_time_sync)
    timing["server_time_samples"] = int(server_time_samples)
    timing["t0_reload"] = bool(t0_reload)
    safety["force_unlock"] = bool(force_unlock)
    browser["parallel_pages"] = int(parallel_pages)

    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        value = {}
        data[key] = value
    return value


def _normalize_start_time(start_at: str | None) -> str | None:
    return _normalize_optional_text(start_at)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def status_from_runner_line(line: str) -> str | None:
    line = _strip_page_prefix(line)
    for prefix, status in STATUS_PREFIXES:
        if line.startswith(prefix):
            return status
    return None


def _strip_page_prefix(line: str) -> str:
    if not line.startswith("[页面"):
        return line
    end = line.find("]")
    if end == -1:
        return line
    return line[end + 1 :].lstrip()


def build_runner_environment(base_env: Mapping[str, str], root: str | Path) -> dict[str, str]:
    root_path = Path(root)
    env = dict(base_env)
    env["PYTHONPATH"] = str(root_path / "src")
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(root_path / ".ms-playwright")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env
