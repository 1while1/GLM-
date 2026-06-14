# GLM Coding Grabber Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an audited single-target GLM Coding Plan purchase assistant that uses Playwright for browser guarding and page-injected JavaScript for low-latency, controlled handoff before payment.

**Architecture:** The project is split into tested Python helper modules, a Playwright runner, and a page injector. Python owns config, state classification, redacted logging, alerts, screenshots, and browser lifecycle. The injected JavaScript owns page-local observation, target validation, request in-flight locking, and controlled click attempts.

**Tech Stack:** Python 3.10+, Playwright for Python, PyYAML, pytest, plain browser JavaScript.

---

## File Structure

- Create `src/glm_grabber/__init__.py`: package marker.
- Create `src/glm_grabber/config.py`: YAML loading, defaults, and validation.
- Create `src/glm_grabber/state.py`: page/network state classification.
- Create `src/glm_grabber/logger.py`: JSONL event logging and redaction.
- Create `src/glm_grabber/runner_core.py`: pure runner helpers.
- Create `runner.py`: Playwright browser guard and injector host.
- Create `injector.user.js`: page-local observer and controlled click logic.
- Create `config.yaml`: conservative example config.
- Create `.env.example`: optional account env var names without a password.
- Create `requirements.txt`: runtime and test dependencies.
- Create `README.md`: setup, dry run, operation, and safety notes.
- Create `tests/test_config.py`: config validation tests.
- Create `tests/test_state.py`: state priority tests.
- Create `tests/test_logger.py`: redaction tests.
- Create `tests/test_runner_core.py`: time and handoff helper tests.

## Task 1: Config Module

**Files:**
- Create: `tests/test_config.py`
- Create: `src/glm_grabber/__init__.py`
- Create: `src/glm_grabber/config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py` with tests that import `load_config`, `GrabberConfig`, and `ConfigError`, then verify defaults and validation:

```python
from pathlib import Path

import pytest

from glm_grabber.config import ConfigError, GrabberConfig, load_config


def test_load_config_applies_conservative_defaults(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: quarter
page:
  url: "https://www.bigmodel.cn/glm-coding?ic=XOJGYOGNLN"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert isinstance(config, GrabberConfig)
    assert config.target.plan == "Pro"
    assert config.target.period == "quarter"
    assert config.safety.stop_before_payment is True
    assert config.safety.force_unlock is False
    assert config.safety.replay_requests is False
    assert config.timing.normal_check_interval_ms == 200
    assert config.timing.armed_check_interval_ms == 50


@pytest.mark.parametrize("plan", ["Basic", "", "pro"])
def test_load_config_rejects_unknown_plan(tmp_path: Path, plan: str):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"""
target:
  plan: {plan!r}
  period: quarter
page:
  url: "https://www.bigmodel.cn/glm-coding"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_file)


@pytest.mark.parametrize("period", ["daily", "", "Quarter"])
def test_load_config_rejects_unknown_period(tmp_path: Path, period: str):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"""
target:
  plan: Pro
  period: {period!r}
page:
  url: "https://www.bigmodel.cn/glm-coding"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_file)
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_config.py -q`

Expected: FAIL because `glm_grabber.config` does not exist yet.

- [ ] **Step 3: Implement config module**

Create `src/glm_grabber/__init__.py` as an empty file.

Create `src/glm_grabber/config.py`:

```python
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


@dataclass(frozen=True)
class PageConfig:
    url: str


@dataclass(frozen=True)
class TimingConfig:
    start_at: str | None = None
    normal_check_interval_ms: int = 200
    armed_check_interval_ms: int = 50
    armed_before_seconds: int = 30
    armed_after_seconds: int = 120
    click_cooldown_ms: int = 700
    max_click_attempts: int = 5
    recovery_reload_interval_ms: int = 5000


@dataclass(frozen=True)
class SafetyConfig:
    stop_before_payment: bool = True
    auto_continue_notice: bool = True
    force_unlock: bool = False
    replay_requests: bool = False
    screenshot_on_handoff: bool = True
    beep_on_handoff: bool = True
    pause_on_unknown: bool = True


@dataclass(frozen=True)
class BrowserConfig:
    user_data_dir: str = ".browser-profile"
    headless: bool = False
    slow_mo_ms: int = 0


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
    if value is None:
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
        "armed_before_seconds",
        "armed_after_seconds",
        "click_cooldown_ms",
        "max_click_attempts",
        "recovery_reload_interval_ms",
    ]
    for field_name in positive_fields:
        value = getattr(timing, field_name)
        if not isinstance(value, int) or value <= 0:
            raise ConfigError(f"timing.{field_name} must be a positive integer")
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_config.py -q`

Expected: PASS.

## Task 2: State Classification

**Files:**
- Create: `tests/test_state.py`
- Create: `src/glm_grabber/state.py`

- [ ] **Step 1: Write failing state tests**

Create `tests/test_state.py`:

```python
from glm_grabber.state import GrabberState, classify_signals


def test_payment_handoff_has_highest_priority():
    state = classify_signals(
        {
            "payment": True,
            "captcha": True,
            "login": True,
            "request_in_flight": True,
        }
    )

    assert state == GrabberState.PAYMENT_HANDOFF


def test_captcha_pauses_before_login_and_ready():
    state = classify_signals({"captcha": True, "login": True, "target_ready": True})

    assert state == GrabberState.CAPTCHA_REQUIRED


def test_target_mismatch_blocks_clicking():
    state = classify_signals({"target_mismatch": True, "target_ready": True})

    assert state == GrabberState.TARGET_MISMATCH


def test_ready_requires_confirmed_target_without_inflight():
    state = classify_signals({"target_ready": True, "button_enabled": True})

    assert state == GrabberState.READY


def test_unknown_when_no_decisive_signal():
    state = classify_signals({"button_enabled": True})

    assert state == GrabberState.UNKNOWN
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_state.py -q`

Expected: FAIL because `glm_grabber.state` does not exist yet.

- [ ] **Step 3: Implement state module**

Create `src/glm_grabber/state.py`:

```python
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
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_state.py -q`

Expected: PASS.

## Task 3: Redacted JSONL Logger

**Files:**
- Create: `tests/test_logger.py`
- Create: `src/glm_grabber/logger.py`

- [ ] **Step 1: Write failing logger tests**

Create `tests/test_logger.py`:

```python
import json
from pathlib import Path

from glm_grabber.logger import JsonlLogger, redact_sensitive


def test_redact_sensitive_removes_nested_secret_values():
    data = {
        "phone": "18821363158",
        "headers": {"Authorization": "Bearer secret", "Cookie": "sid=secret"},
        "body": {"password": "plain", "safe": "ok"},
    }

    redacted = redact_sensitive(data)

    assert redacted["phone"] == "<redacted>"
    assert redacted["headers"]["Authorization"] == "<redacted>"
    assert redacted["headers"]["Cookie"] == "<redacted>"
    assert redacted["body"]["password"] == "<redacted>"
    assert redacted["body"]["safe"] == "ok"


def test_jsonl_logger_writes_redacted_event(tmp_path: Path):
    logger = JsonlLogger(tmp_path / "events.jsonl")

    logger.write("login_required", {"password": "secret", "status": "paused"})

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    assert event["event"] == "login_required"
    assert event["data"]["password"] == "<redacted>"
    assert event["data"]["status"] == "paused"
    assert "ts" in event
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_logger.py -q`

Expected: FAIL because `glm_grabber.logger` does not exist yet.

- [ ] **Step 3: Implement logger module**

Create `src/glm_grabber/logger.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "cookie",
    "authorization",
    "secret",
    "credential",
    "phone",
    "account",
)


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


class JsonlLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, data: dict[str, Any] | None = None) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "data": redact_sensitive(data or {}),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_logger.py -q`

Expected: PASS.

## Task 4: Runner Core Helpers

**Files:**
- Create: `tests/test_runner_core.py`
- Create: `src/glm_grabber/runner_core.py`

- [ ] **Step 1: Write failing runner helper tests**

Create `tests/test_runner_core.py`:

```python
from datetime import datetime, time

from glm_grabber.runner_core import seconds_until_time_today, should_handoff


def test_seconds_until_time_today_returns_zero_after_target_time():
    now = datetime(2026, 6, 14, 10, 0, 1)

    assert seconds_until_time_today("10:00:00", now) == 0


def test_seconds_until_time_today_calculates_same_day_wait():
    now = datetime(2026, 6, 14, 9, 59, 58)

    assert seconds_until_time_today("10:00:00", now) == 2


def test_seconds_until_time_today_accepts_hh_mm_format():
    now = datetime(2026, 6, 14, 9, 59, 0)

    assert seconds_until_time_today("10:00", now) == 60


def test_should_handoff_detects_payment_state_and_text():
    assert should_handoff({"state": "PAYMENT_HANDOFF"}) is True
    assert should_handoff({"text": "微信支付二维码"}) is True
    assert should_handoff({"url": "https://www.bigmodel.cn/pay/checkout"}) is True
    assert should_handoff({"state": "READY", "text": "特惠订阅"}) is False
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest tests/test_runner_core.py -q`

Expected: FAIL because `glm_grabber.runner_core` does not exist yet.

- [ ] **Step 3: Implement runner core module**

Create `src/glm_grabber/runner_core.py`:

```python
from __future__ import annotations

from datetime import datetime, time
from typing import Mapping


PAYMENT_MARKERS = (
    "支付",
    "二维码",
    "收银台",
    "订单号",
    "确认支付",
    "pay",
    "checkout",
)


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
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_runner_core.py -q`

Expected: PASS.

## Task 5: Browser Runner and Injector

**Files:**
- Create: `runner.py`
- Create: `injector.user.js`
- Create: `config.yaml`
- Create: `.env.example`
- Create: `requirements.txt`

- [ ] **Step 1: Create runtime files**

Create `requirements.txt`:

```text
playwright>=1.45
PyYAML>=6.0
pytest>=8.0
```

Create `.env.example`:

```text
GLM_ACCOUNT=18821363158
GLM_PASSWORD=
```

Create `config.yaml`:

```yaml
target:
  plan: Pro
  period: quarter
  expected_price_text: ""

page:
  url: "https://www.bigmodel.cn/glm-coding?ic=XOJGYOGNLN"

timing:
  start_at: "09:59:58"
  normal_check_interval_ms: 200
  armed_check_interval_ms: 50
  armed_before_seconds: 30
  armed_after_seconds: 120
  click_cooldown_ms: 700
  max_click_attempts: 5
  recovery_reload_interval_ms: 5000

safety:
  stop_before_payment: true
  auto_continue_notice: true
  force_unlock: false
  replay_requests: false
  screenshot_on_handoff: true
  beep_on_handoff: true
  pause_on_unknown: true

browser:
  user_data_dir: ".browser-profile"
  headless: false
  slow_mo_ms: 0

logging:
  dir: "logs"
  screenshots_dir: "screenshots"
```

- [ ] **Step 2: Implement `injector.user.js`**

Create `injector.user.js` with page-local observation, target validation, in-flight locking, and handoff detection:

```javascript
(() => {
  "use strict";

  const DEFAULT_CONFIG = {
    target: { plan: "Pro", period: "quarter", expected_price_text: "" },
    timing: {
      normal_check_interval_ms: 200,
      armed_check_interval_ms: 50,
      click_cooldown_ms: 700,
      max_click_attempts: 5
    },
    safety: {
      auto_continue_notice: true,
      force_unlock: false,
      stop_before_payment: true,
      pause_on_unknown: true
    }
  };

  const config = merge(DEFAULT_CONFIG, window.__GLM_GRABBER_CONFIG__ || {});
  const state = {
    stopped: false,
    paused: false,
    requestInFlight: false,
    clickAttempts: 0,
    lastClickAt: 0,
    lastState: "INIT",
    observerScheduled: false
  };

  const PERIOD_TEXT = {
    month: "连续包月",
    quarter: "连续包季",
    year: "连续包年"
  };

  installNetworkHooks();
  installObserver();
  setInterval(tick, config.timing.normal_check_interval_ms);
  report("injector_ready", { target: config.target });
  tick();

  function tick() {
    if (state.stopped || state.paused) return;
    const signals = collectSignals();
    const nextState = classify(signals);
    if (nextState !== state.lastState) {
      state.lastState = nextState;
      report("state", { state: nextState, signals: summarizeSignals(signals) });
    }
    act(nextState, signals);
  }

  function act(nextState, signals) {
    if (nextState === "PAYMENT_HANDOFF") {
      stop("payment_handoff", signals);
      return;
    }
    if (nextState === "CAPTCHA_REQUIRED" || nextState === "LOGIN_REQUIRED" || nextState === "TARGET_MISMATCH") {
      pause(nextState.toLowerCase(), signals);
      return;
    }
    if (nextState === "CONFIRM_NOTICE" && config.safety.auto_continue_notice) {
      clickControlled(signals.confirmButton, "confirm_notice");
      return;
    }
    if (nextState === "READY") {
      clickControlled(signals.buyButton, "target_ready");
    }
  }

  function collectSignals() {
    const text = document.body ? document.body.innerText || "" : "";
    const target = findTargetCard();
    const payment = /支付|二维码|收银台|订单号|确认支付/i.test(text) || /pay|checkout/i.test(location.href);
    const captcha = /拖动下方拼图|安全验证|验证码|captcha|verify/i.test(text);
    const login = /登录\s*\/\s*注册|账号密码登录|手机号登录/i.test(text) && !target.card;
    const confirmButton = findVisibleButton(/已知悉，继续订阅|继续订阅|我知道了/);
    const confirmNotice = Boolean(confirmButton) && !payment && !captcha;

    return {
      text,
      payment,
      captcha,
      login,
      confirmNotice,
      confirmButton,
      requestInFlight: state.requestInFlight,
      targetReady: Boolean(target.card && target.periodSelected && target.buyButton && !target.mismatch),
      targetMismatch: target.mismatch,
      buyButton: target.buyButton,
      targetSummary: target.summary
    };
  }

  function classify(signals) {
    if (signals.payment) return "PAYMENT_HANDOFF";
    if (signals.captcha) return "CAPTCHA_REQUIRED";
    if (signals.login) return "LOGIN_REQUIRED";
    if (signals.targetMismatch) return "TARGET_MISMATCH";
    if (signals.requestInFlight) return "REQUEST_IN_FLIGHT";
    if (signals.confirmNotice) return "CONFIRM_NOTICE";
    if (signals.targetReady) return "READY";
    return "UNKNOWN";
  }

  function findTargetCard() {
    const plan = config.target.plan;
    const periodText = PERIOD_TEXT[config.target.period] || config.target.period;
    const candidates = Array.from(document.querySelectorAll("section, div, article, li"))
      .filter((el) => visible(el) && includesOwnText(el, plan));

    let best = null;
    for (const candidate of candidates) {
      const text = candidate.innerText || "";
      if (!text.includes(plan)) continue;
      if (!/特惠订阅|订阅/.test(text)) continue;
      const button = findButtonIn(candidate, /特惠订阅|订阅/);
      if (!button) continue;
      if (!best || text.length < (best.innerText || "").length) {
        best = candidate;
      }
    }

    const selectedPeriod = findSelectedPeriod(periodText);
    const mismatch = Boolean(best && config.target.expected_price_text && !(best.innerText || "").includes(config.target.expected_price_text));

    return {
      card: best,
      buyButton: best ? findButtonIn(best, /特惠订阅|订阅/) : null,
      periodSelected: selectedPeriod,
      mismatch,
      summary: best ? {
        plan,
        period: config.target.period,
        cardText: compact((best.innerText || "").slice(0, 300)),
        periodSelected: selectedPeriod
      } : { plan, period: config.target.period, found: false }
    };
  }

  function findSelectedPeriod(periodText) {
    const nodes = Array.from(document.querySelectorAll("button, [role='button'], div, span"))
      .filter((el) => visible(el) && (el.innerText || "").includes(periodText));
    if (nodes.length === 0) return false;
    return nodes.some((el) => {
      const className = String(el.className || "");
      const aria = el.getAttribute("aria-selected") || el.getAttribute("aria-pressed");
      return aria === "true" || /active|selected|current|is-active/.test(className) || nodes.length === 1;
    });
  }

  function clickControlled(button, reason) {
    if (!button || state.stopped || state.paused || state.requestInFlight) return;
    const now = Date.now();
    if (state.clickAttempts >= config.timing.max_click_attempts) {
      pause("max_click_attempts", { attempts: state.clickAttempts });
      return;
    }
    if (now - state.lastClickAt < config.timing.click_cooldown_ms) return;

    state.lastClickAt = now;
    state.clickAttempts += 1;
    report("click_attempt", { reason, attempts: state.clickAttempts, text: compact(button.innerText || "") });

    if (config.safety.force_unlock) unlockButton(button);
    button.click();
  }

  function installNetworkHooks() {
    const originalFetch = window.fetch;
    window.fetch = async function patchedFetch(input, init) {
      const requestInfo = describeRequest(input, init);
      markIfPurchaseRequestStart(requestInfo);
      try {
        const response = await originalFetch.apply(this, arguments);
        reportNetworkResponse(requestInfo, response.status);
        markIfPurchaseRequestEnd(requestInfo, response.status);
        return response;
      } catch (error) {
        markIfPurchaseRequestEnd(requestInfo, 0);
        report("network_error", { request: requestInfo, message: String(error && error.message || error) });
        throw error;
      }
    };

    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function patchedOpen(method, url) {
      this.__glmGrabberRequest = { method, url: String(url) };
      return originalOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function patchedSend(body) {
      const requestInfo = Object.assign({}, this.__glmGrabberRequest || {}, { body: safeBody(body) });
      markIfPurchaseRequestStart(requestInfo);
      this.addEventListener("loadend", () => {
        reportNetworkResponse(requestInfo, this.status);
        markIfPurchaseRequestEnd(requestInfo, this.status);
      });
      return originalSend.apply(this, arguments);
    };
  }

  function markIfPurchaseRequestStart(requestInfo) {
    if (!isPurchaseLike(requestInfo.url)) return;
    state.requestInFlight = true;
    report("purchase_request_start", { request: requestInfo });
  }

  function markIfPurchaseRequestEnd(requestInfo, status) {
    if (!isPurchaseLike(requestInfo.url)) return;
    state.requestInFlight = false;
    report("purchase_request_end", { request: requestInfo, status });
  }

  function isPurchaseLike(url) {
    return /order|subscribe|subscription|purchase|buy|pay|coding-plan|tokenResPack/i.test(String(url || ""));
  }

  function reportNetworkResponse(requestInfo, status) {
    if (isPurchaseLike(requestInfo.url)) {
      report("network_response", { request: requestInfo, status });
    }
  }

  function describeRequest(input, init) {
    const url = typeof input === "string" ? input : input && input.url;
    const method = init && init.method || input && input.method || "GET";
    return { method, url: String(url || ""), body: safeBody(init && init.body) };
  }

  function safeBody(body) {
    if (!body) return "";
    const text = typeof body === "string" ? body : "[non-string-body]";
    return text.slice(0, 500);
  }

  function installObserver() {
    const observer = new MutationObserver(() => {
      if (state.observerScheduled) return;
      state.observerScheduled = true;
      requestAnimationFrame(() => {
        state.observerScheduled = false;
        tick();
      });
    });
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "disabled", "aria-disabled", "style"]
    });
  }

  function pause(reason, details) {
    state.paused = true;
    report("paused", { reason, details: summarizeSignals(details || {}) });
  }

  function stop(reason, details) {
    state.stopped = true;
    report("stopped", { reason, details: summarizeSignals(details || {}) });
  }

  function unlockButton(button) {
    button.disabled = false;
    button.removeAttribute("disabled");
    button.removeAttribute("aria-disabled");
    button.style.pointerEvents = "auto";
  }

  function findVisibleButton(pattern) {
    return Array.from(document.querySelectorAll("button, [role='button']"))
      .find((el) => visible(el) && pattern.test(el.innerText || el.textContent || ""));
  }

  function findButtonIn(root, pattern) {
    return Array.from(root.querySelectorAll("button, [role='button']"))
      .find((el) => visible(el) && pattern.test(el.innerText || el.textContent || ""));
  }

  function includesOwnText(el, text) {
    return (el.innerText || "").includes(text);
  }

  function visible(el) {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  }

  function summarizeSignals(signals) {
    return {
      payment: Boolean(signals.payment),
      captcha: Boolean(signals.captcha),
      login: Boolean(signals.login),
      requestInFlight: Boolean(signals.requestInFlight),
      targetReady: Boolean(signals.targetReady),
      targetMismatch: Boolean(signals.targetMismatch),
      targetSummary: signals.targetSummary || undefined
    };
  }

  function report(event, data) {
    const payload = {
      source: "glm-grabber",
      event,
      data: data || {},
      url: location.href,
      title: document.title,
      ts: new Date().toISOString()
    };
    window.postMessage(payload, "*");
    if (window.__GLM_GRABBER_REPORT__) {
      window.__GLM_GRABBER_REPORT__(payload);
    }
  }

  function compact(text) {
    return String(text).replace(/\s+/g, " ").trim();
  }

  function merge(base, override) {
    const output = Array.isArray(base) ? base.slice() : Object.assign({}, base);
    for (const [key, value] of Object.entries(override || {})) {
      if (value && typeof value === "object" && !Array.isArray(value) && base[key]) {
        output[key] = merge(base[key], value);
      } else {
        output[key] = value;
      }
    }
    return output;
  }
})();
```

- [ ] **Step 3: Implement `runner.py`**

Create `runner.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

from glm_grabber.config import GrabberConfig, load_config
from glm_grabber.logger import JsonlLogger
from glm_grabber.runner_core import seconds_until_time_today, should_handoff


ROOT = Path(__file__).resolve().parent
INJECTOR = ROOT / "injector.user.js"


async def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    logger = JsonlLogger(Path(config.logging.dir) / "events.jsonl")
    logger.write("runner_start", {"config": public_config(config)})

    wait_seconds = seconds_until_time_today(config.timing.start_at)
    if wait_seconds:
        logger.write("waiting_for_start", {"seconds": wait_seconds, "start_at": config.timing.start_at})
        print(f"Waiting {wait_seconds}s until {config.timing.start_at}...")
        await asyncio.sleep(wait_seconds)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=config.browser.user_data_dir,
            headless=config.browser.headless,
            slow_mo=config.browser.slow_mo_ms,
            viewport={"width": 1440, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await expose_reporter(page, config, logger)
        await inject_config(page, config)
        await page.add_init_script(path=str(INJECTOR))
        page.on("console", lambda msg: logger.write("browser_console", {"type": msg.type, "text": msg.text}))

        print("Opening GLM Coding Plan page...")
        await page.goto(config.page.url, wait_until="domcontentloaded", timeout=60000)
        await inject_config(page, config)
        await page.add_script_tag(path=str(INJECTOR))
        logger.write("page_opened", {"url": page.url})

        print("Browser is armed. Complete login/captcha manually if prompted.")
        try:
          while True:
              await asyncio.sleep(1)
              if page.is_closed():
                  logger.write("page_closed", {})
                  break
        finally:
            await context.close()
    return 0


async def expose_reporter(page: Page, config: GrabberConfig, logger: JsonlLogger) -> None:
    async def report(payload: dict[str, Any]) -> None:
        logger.write(str(payload.get("event", "page_event")), payload)
        if should_handoff(payload.get("data", {}) | {"url": payload.get("url", ""), "title": payload.get("title", "")}):
            await handle_handoff(page, config, logger, payload)
        elif payload.get("event") in {"paused", "stopped"}:
            print(f"[{payload.get('event')}] {json.dumps(payload.get('data', {}), ensure_ascii=False)}")

    await page.expose_function("__GLM_GRABBER_REPORT__", report)


async def handle_handoff(page: Page, config: GrabberConfig, logger: JsonlLogger, payload: dict[str, Any]) -> None:
    logger.write("handoff_detected", payload)
    if config.safety.screenshot_on_handoff:
        screenshot_dir = Path(config.logging.screenshots_dir)
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"handoff-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        logger.write("handoff_screenshot", {"path": str(screenshot_path)})
    if config.safety.beep_on_handoff:
        print("\a", end="", flush=True)
    print("Payment/final confirmation handoff detected. Automation stopped; please take over in the browser.")


async def inject_config(page: Page, config: GrabberConfig) -> None:
    await page.add_init_script(
        "window.__GLM_GRABBER_CONFIG__ = %s;" % json.dumps(public_config(config), ensure_ascii=False)
    )
    await page.evaluate(
        "config => { window.__GLM_GRABBER_CONFIG__ = config; }",
        public_config(config),
    )


def public_config(config: GrabberConfig) -> dict[str, Any]:
    return asdict(config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GLM Coding Plan guarded purchase assistant")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("Stopped by user.")
        raise SystemExit(130)
```

- [ ] **Step 4: Run syntax checks**

Run: `python -m py_compile runner.py src/glm_grabber/config.py src/glm_grabber/state.py src/glm_grabber/logger.py src/glm_grabber/runner_core.py`

Expected: no output and exit code 0.

## Task 6: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README**

Create `README.md`:

```markdown
# GLM Coding Plan Grabber

Single-target GLM Coding Plan purchase assistant.

This tool opens a persistent Chromium session, injects a page-local observer, watches one configured plan and billing period, and stops before payment or final confirmation.

## Safety Boundary

- It does not bypass captcha.
- It does not auto-pay.
- It does not rotate through multiple plans.
- It does not replay captured purchase requests in v1.
- It pauses on login, captcha, target mismatch, and unknown states.
- It uses an in-flight lock to avoid repeated purchase attempts.

## Setup

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Configure

Edit `config.yaml`:

```yaml
target:
  plan: Pro
  period: quarter
```

Allowed plans: `Lite`, `Pro`, `Max`.

Allowed periods:

- `month`: 连续包月
- `quarter`: 连续包季
- `year`: 连续包年

Do not put your password in source files. Use the persistent browser profile and log in manually on first run.

## Run

```powershell
$env:PYTHONPATH = ".\\src"
python runner.py --config config.yaml
```

On first run:

1. Browser opens.
2. Log in manually if needed.
3. Complete captcha manually if shown.
4. Leave the browser open.
5. The script monitors the configured target.

When payment or final confirmation is detected, the script beeps, saves a screenshot, writes logs, and stops clicking. You must take over manually.

## Logs

- `logs/events.jsonl`: structured redacted event log
- `screenshots/`: handoff screenshots

Sensitive keys such as password, token, cookie, authorization, phone, and account are redacted.

## Notes

This tool can reduce the delay between page state changes and a controlled click. It cannot create stock, bypass account eligibility, bypass captcha, bypass server-side limits, or bypass payment.
```

- [ ] **Step 2: Run all tests**

Run: `python -m pytest -q`

Expected: PASS.

## Task 7: Final Verification

**Files:**
- Read/verify all created files.

- [ ] **Step 1: Run full Python syntax check**

Run: `python -m py_compile runner.py src/glm_grabber/*.py`

Expected: no output and exit code 0.

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Optional dry run**

Run only after dependencies and Playwright browser are installed:

```powershell
$env:PYTHONPATH = ".\\src"
python runner.py --config config.yaml
```

Expected: browser opens the GLM Coding Plan page, logs `injector_ready`, and pauses for manual login/captcha when needed.

---

## Self-Review

- Spec coverage: config, state priority, logging redaction, Playwright guard, injector, handoff, docs, and verification are covered.
- Placeholder scan: no implementation placeholders remain in task steps.
- Type consistency: Python module names and function names are consistent across tests and implementation steps.
