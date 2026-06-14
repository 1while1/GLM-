import os
from pathlib import Path

import pytest
from playwright.sync_api import Error, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("button_text", "attributes"),
    [
        ("暂时售罄 ｜06月14日 10:00 补货", 'class="package-card-btn disabled" disabled aria-disabled="true"'),
        ("06月14日 10:00", 'class="package-card-btn disabled" disabled aria-disabled="true"'),
        ("06月14日 10:00", 'class="package-card-btn" style="background:#d8d8d8;color:#8a8a8a;border-color:#c8c8c8"'),
    ],
)
def test_force_unlock_clicks_target_card_locked_button(button_text, attributes):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    injector = (ROOT / "injector.user.js").read_text(encoding="utf-8")
    html = f"""
    <html>
      <body>
        <button class="active">连续包月</button>
        <section class="package-card" style="width:456px;height:430px">
          <h2>Pro</h2>
          <p>最受欢迎 ￥149/月 下个月度续费金额：￥149</p>
          <button {attributes} onclick="window.__soldOutClicked = (window.__soldOutClicked || 0) + 1">{button_text}</button>
        </section>
      </body>
    </html>
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not available: {exc}")

        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.set_content(html)
        page.evaluate(
            """() => {
                window.__events = [];
                window.__GLM_GRABBER_CONFIG__ = {
                  target: { plan: "Pro", period: "month", expected_price_text: "" },
                  timing: {
                    start_at: null,
                    normal_check_interval_ms: 200,
                    armed_check_interval_ms: 50,
                    armed_before_seconds: 30,
                    armed_after_seconds: 120,
                    click_cooldown_ms: 0,
                    max_click_attempts: 1
                  },
                  safety: {
                    auto_continue_notice: true,
                    force_unlock: true,
                    stop_before_payment: true,
                    pause_on_unknown: true
                  }
                };
                window.__GLM_GRABBER_REPORT__ = (payload) => window.__events.push(payload);
              }"""
        )
        page.evaluate(injector)

        page.wait_for_function("window.__soldOutClicked === 1", timeout=2000)
        events = page.evaluate("window.__events")
        browser.close()

    click_events = [event for event in events if event["event"] == "click_attempt"]
    assert click_events
    assert click_events[0]["data"]["reason"] == "target_ready"
    assert click_events[0]["data"]["text"] == button_text


def test_ready_click_forces_scroll_to_button_after_period_scroll():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    injector = (ROOT / "injector.user.js").read_text(encoding="utf-8")
    html = """
    <html>
      <body style="margin:0;height:2600px">
        <div style="height:700px"></div>
        <button class="period">连续包月</button>
        <div role="button">连续包月</div>
        <div style="height:700px"></div>
        <div id="card-mount"></div>
      </body>
    </html>
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not available: {exc}")

        page = browser.new_page(viewport={"width": 1200, "height": 500})
        page.set_content(html)
        page.evaluate(
            """() => {
                window.__events = [];
                const period = document.querySelector(".period");
                const mount = document.querySelector("#card-mount");
                period.addEventListener("click", () => {
                  period.classList.add("active");
                  if (mount.querySelector(".package-card")) return;
                  mount.insertAdjacentHTML("beforeend", `
                    <section class="package-card" style="width:456px;height:430px">
                      <h2>Pro</h2>
                      <p>最受欢迎 ￥149/月 下个月度续费金额：￥149</p>
                      <button
                        class="package-card-btn disabled"
                        disabled
                        aria-disabled="true"
                        onclick="window.__soldOutClicked = (window.__soldOutClicked || 0) + 1"
                      >06月14日 10:00</button>
                    </section>
                  `);
                });
                window.__GLM_GRABBER_CONFIG__ = {
                  target: { plan: "Pro", period: "month", expected_price_text: "" },
                  timing: {
                    start_at: null,
                    normal_check_interval_ms: 200,
                    armed_check_interval_ms: 50,
                    armed_before_seconds: 30,
                    armed_after_seconds: 120,
                    click_cooldown_ms: 0,
                    max_click_attempts: 1
                  },
                  safety: {
                    auto_continue_notice: true,
                    force_unlock: true,
                    stop_before_payment: true,
                    pause_on_unknown: true
                  }
                };
                window.__GLM_GRABBER_REPORT__ = (payload) => window.__events.push(payload);
              }"""
        )
        page.evaluate(injector)
        page.wait_for_function("window.__soldOutClicked === 1", timeout=2500)
        events = page.evaluate("window.__events")
        rect = page.locator(".package-card-btn").bounding_box()
        browser.close()

    scroll_events = [event for event in events if event["event"] == "scroll_to_target"]
    assert any(event["data"]["text"] == "连续包月" for event in scroll_events)
    assert any(event["data"]["text"] == "06月14日 10:00" for event in scroll_events)
    assert rect is not None
    assert 120 <= rect["y"] <= 300


def test_zero_max_click_attempts_keeps_retrying_without_pausing():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    injector = (ROOT / "injector.user.js").read_text(encoding="utf-8")
    html = """
    <html>
      <body>
        <button class="active">连续包月</button>
        <section class="package-card" style="width:456px;height:430px">
          <h2>Pro</h2>
          <p>最受欢迎 ￥149/月 下个月度续费金额：￥149</p>
          <button
            class="package-card-btn disabled"
            disabled
            aria-disabled="true"
            onclick="window.__retryClicks = (window.__retryClicks || 0) + 1"
          >06月14日 10:00</button>
        </section>
      </body>
    </html>
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not available: {exc}")

        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.set_content(html)
        page.evaluate(
            """() => {
                window.__events = [];
                window.__GLM_GRABBER_CONFIG__ = {
                  target: { plan: "Pro", period: "month", expected_price_text: "" },
                  timing: {
                    start_at: null,
                    normal_check_interval_ms: 20,
                    armed_check_interval_ms: 20,
                    armed_before_seconds: 30,
                    armed_after_seconds: 120,
                    click_cooldown_ms: 20,
                    max_click_attempts: 0
                  },
                  safety: {
                    auto_continue_notice: true,
                    force_unlock: true,
                    stop_before_payment: true,
                    pause_on_unknown: true
                  }
                };
                window.__GLM_GRABBER_REPORT__ = (payload) => window.__events.push(payload);
              }"""
        )
        page.evaluate(injector)
        page.wait_for_function("window.__retryClicks >= 7", timeout=2500)
        events = page.evaluate("window.__events")
        browser.close()

    click_events = [event for event in events if event["event"] == "click_attempt"]
    paused_events = [event for event in events if event["event"] == "paused"]
    assert len(click_events) >= 7
    assert not paused_events


def test_manual_button_selector_overrides_auto_detection():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    injector = (ROOT / "injector.user.js").read_text(encoding="utf-8")
    html = """
    <html>
      <body>
        <button class="active">连续包月</button>
        <section class="package-card" style="width:456px;height:430px">
          <h2>Pro</h2>
          <p>最受欢迎 ￥149/月 下个月度续费金额：￥149</p>
          <button class="package-card-btn" onclick="window.__autoClicked = true">订阅</button>
          <button class="manual-target" onclick="window.__manualClicked = true">立即订阅</button>
        </section>
      </body>
    </html>
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not available: {exc}")

        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.set_content(html)
        page.evaluate(
            """() => {
                window.__events = [];
                window.__GLM_GRABBER_CONFIG__ = {
                  target: {
                    plan: "Pro",
                    period: "month",
                    expected_price_text: "",
                    button_selector: ".manual-target"
                  },
                  timing: {
                    start_at: null,
                    normal_check_interval_ms: 20,
                    armed_check_interval_ms: 20,
                    click_cooldown_ms: 0,
                    max_click_attempts: 1
                  },
                  safety: {
                    auto_continue_notice: true,
                    force_unlock: true,
                    stop_before_payment: true,
                    pause_on_unknown: true
                  }
                };
                window.__GLM_GRABBER_REPORT__ = (payload) => window.__events.push(payload);
              }"""
        )
        page.evaluate(injector)
        page.wait_for_function("window.__manualClicked === true", timeout=2000)
        auto_clicked = page.evaluate("Boolean(window.__autoClicked)")
        events = page.evaluate("window.__events")
        browser.close()

    assert auto_clicked is False
    click_events = [event for event in events if event["event"] == "click_attempt"]
    assert click_events[0]["data"]["text"] == "立即订阅"


def test_manual_button_selector_stays_inside_target_plan_card():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    injector = (ROOT / "injector.user.js").read_text(encoding="utf-8")
    html = """
    <html>
      <body>
        <button class="active">连续包月</button>
        <section class="package-card" style="width:456px;height:430px">
          <h2>Lite</h2>
          <p>￥19/月</p>
          <button class="package-card-btn" onclick="window.__liteClicked = true">订阅</button>
        </section>
        <section class="package-card" style="width:456px;height:430px">
          <h2>Pro</h2>
          <p>最受欢迎 ￥149/月 下个月度续费金额：￥149</p>
          <button class="package-card-btn" onclick="window.__proClicked = true">订阅</button>
        </section>
      </body>
    </html>
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not available: {exc}")

        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.set_content(html)
        page.evaluate(
            """() => {
                window.__events = [];
                window.__GLM_GRABBER_CONFIG__ = {
                  target: {
                    plan: "Pro",
                    period: "month",
                    expected_price_text: "",
                    button_selector: ".package-card-btn"
                  },
                  timing: {
                    start_at: null,
                    normal_check_interval_ms: 20,
                    armed_check_interval_ms: 20,
                    click_cooldown_ms: 0,
                    max_click_attempts: 1
                  },
                  safety: {
                    auto_continue_notice: true,
                    force_unlock: true,
                    stop_before_payment: true,
                    pause_on_unknown: true
                  }
                };
                window.__GLM_GRABBER_REPORT__ = (payload) => window.__events.push(payload);
              }"""
        )
        page.evaluate(injector)
        page.wait_for_function("window.__proClicked === true", timeout=2000)
        lite_clicked = page.evaluate("Boolean(window.__liteClicked)")
        browser.close()

    assert lite_clicked is False


def test_t0_reload_reports_once_before_ready_clicks():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    injector = (ROOT / "injector.user.js").read_text(encoding="utf-8")
    html = """
    <html>
      <body>
        <button class="active">连续包月</button>
        <section class="package-card" style="width:456px;height:430px">
          <h2>Pro</h2>
          <p>最受欢迎 ￥149/月 下个月度续费金额：￥149</p>
          <button class="package-card-btn" onclick="window.__readyClicks = (window.__readyClicks || 0) + 1">订阅</button>
        </section>
      </body>
    </html>
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not available: {exc}")

        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.set_content(html)
        page.evaluate(
            """() => {
                const now = new Date();
                const startAt = [now.getHours(), now.getMinutes(), now.getSeconds()]
                  .map((part) => String(part).padStart(2, "0"))
                  .join(":");
                window.__events = [];
                window.__GLM_GRABBER_CONFIG__ = {
                  target: { plan: "Pro", period: "month", expected_price_text: "" },
                  timing: {
                    start_at: startAt,
                    normal_check_interval_ms: 20,
                    armed_check_interval_ms: 20,
                    armed_before_seconds: 0,
                    armed_after_seconds: 120,
                    click_cooldown_ms: 0,
                    max_click_attempts: 1,
                    t0_reload: true
                  },
                  safety: {
                    auto_continue_notice: true,
                    force_unlock: true,
                    stop_before_payment: true,
                    pause_on_unknown: true
                  }
                };
                window.__GLM_GRABBER_REPORT__ = (payload) => window.__events.push(payload);
              }"""
        )
        page.evaluate(injector)
        page.wait_for_function("window.__events.some((event) => event.event === 't0_reload_requested')", timeout=2000)
        page.wait_for_timeout(150)
        events = page.evaluate("window.__events")
        ready_clicks = page.evaluate("window.__readyClicks || 0")
        browser.close()

    reload_events = [event for event in events if event["event"] == "t0_reload_requested"]
    assert len(reload_events) == 1
    assert ready_clicks == 0


def test_crowded_refresh_message_clicks_before_recovery_reload():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    injector = (ROOT / "injector.user.js").read_text(encoding="utf-8")
    html = """
    <html>
      <body>
        <button class="active">连续包月</button>
        <section class="package-card" style="width:456px;height:430px">
          <h2>Pro</h2>
          <p>最受欢迎 ￥149/月 下个月度续费金额：￥149</p>
          <button class="package-card-btn">抢购人数过多，请刷新再试</button>
        </section>
      </body>
    </html>
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not available: {exc}")

        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.set_content(html)
        page.evaluate(
            """() => {
                window.__events = [];
                window.__GLM_GRABBER_CONFIG__ = {
                  target: { plan: "Pro", period: "month", expected_price_text: "" },
                  timing: {
                    start_at: null,
                    normal_check_interval_ms: 10,
                    armed_check_interval_ms: 10,
                    armed_before_seconds: 30,
                    armed_after_seconds: 120,
                    click_cooldown_ms: 1,
                    max_click_attempts: 0,
                    crowd_retry_clicks_before_reload: 3,
                    recovery_reload_interval_ms: 5000
                  },
                  safety: {
                    auto_continue_notice: true,
                    force_unlock: true,
                    stop_before_payment: true,
                    pause_on_unknown: true
                  }
                };
                window.__GLM_GRABBER_REPORT__ = (payload) => window.__events.push(payload);
              }"""
        )
        page.evaluate(injector)
        page.wait_for_function(
            "window.__events.filter((event) => event.event === 'click_attempt').length >= 3",
            timeout=2000,
        )
        page.wait_for_function(
            "window.__events.some((event) => event.event === 'state' && event.data.state === 'RECOVERY_RELOAD')",
            timeout=2000,
        )
        events = page.evaluate("window.__events")
        browser.close()

    click_events = [event for event in events if event["event"] == "click_attempt"]
    reload_states = [
        event for event in events
        if event["event"] == "state" and event["data"]["state"] == "RECOVERY_RELOAD"
    ]
    assert len(click_events) >= 3
    assert all(event["data"]["text"] == "抢购人数过多，请刷新再试" for event in click_events[:3])
    assert click_events[0]["data"]["reason"] == "crowded_retry"
    assert reload_states


def test_crowded_refresh_message_waits_before_armed_window():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    injector = (ROOT / "injector.user.js").read_text(encoding="utf-8")
    html = """
    <html>
      <body>
        <button class="active">连续包月</button>
        <section class="package-card" style="width:456px;height:430px">
          <h2>Pro</h2>
          <p>最受欢迎 ￥149/月 下个月度续费金额：￥149</p>
          <button class="package-card-btn">抢购人数过多，请刷新再试</button>
        </section>
      </body>
    </html>
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error as exc:
            pytest.skip(f"Playwright Chromium is not available: {exc}")

        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.set_content(html)
        page.evaluate(
            """() => {
                window.__events = [];
                window.__GLM_GRABBER_CONFIG__ = {
                  target: { plan: "Pro", period: "month", expected_price_text: "" },
                  timing: {
                    start_at: "00:00:00",
                    normal_check_interval_ms: 200,
                    armed_check_interval_ms: 50,
                    armed_before_seconds: 0,
                    armed_after_seconds: 1,
                    click_cooldown_ms: 20,
                    max_click_attempts: 0,
                    recovery_reload_interval_ms: 5000
                  },
                  safety: {
                    auto_continue_notice: true,
                    force_unlock: true,
                    stop_before_payment: true,
                    pause_on_unknown: true
                  }
                };
                window.__GLM_GRABBER_REPORT__ = (payload) => window.__events.push(payload);
              }"""
        )
        page.evaluate(injector)
        page.wait_for_function("window.__events.some((event) => event.event === 'state')", timeout=2000)
        page.wait_for_timeout(300)
        events = page.evaluate("window.__events")
        browser.close()

    reload_states = [
        event for event in events
        if event["event"] == "state" and event["data"]["state"] == "RECOVERY_RELOAD"
    ]
    waiting_states = [
        event for event in events
        if event["event"] == "state" and event["data"]["state"] == "WAITING_FOR_TIME"
    ]
    assert waiting_states
    assert not reload_states
