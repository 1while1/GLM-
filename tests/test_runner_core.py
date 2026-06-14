from datetime import datetime

from glm_grabber.config import BrowserConfig, GrabberConfig, PageConfig, TargetConfig, TimingConfig
from glm_grabber.runner_core import describe_page_event, estimate_server_offset_ms, seconds_until_time_today, should_handoff
from glm_grabber.runner_core import public_config_dict


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


def test_public_config_dict_can_ignore_start_time_for_test_mode():
    config = GrabberConfig(
        target=TargetConfig(plan="Pro", period="quarter"),
        page=PageConfig(url="https://www.bigmodel.cn/glm-coding"),
        timing=TimingConfig(start_at="09:59:58"),
        browser=BrowserConfig(headless=False),
    )

    data = public_config_dict(config, ignore_start_time=True)

    assert data["timing"]["start_at"] is None


def test_public_config_dict_includes_runtime_server_offset():
    config = GrabberConfig(
        target=TargetConfig(plan="Pro", period="quarter"),
        page=PageConfig(url="https://www.bigmodel.cn/glm-coding"),
        timing=TimingConfig(start_at="09:59:58"),
        browser=BrowserConfig(headless=False),
    )

    data = public_config_dict(config, server_time_offset_ms=123)

    assert data["timing"]["server_time_offset_ms"] == 123


def test_estimate_server_offset_prefers_lowest_rtt_sample():
    samples = [
        {"started_ms": 1000, "ended_ms": 1300, "server_ms": 2000},
        {"started_ms": 1000, "ended_ms": 1100, "server_ms": 1900},
    ]

    assert estimate_server_offset_ms(samples) == 850


def test_describe_page_event_reports_manual_login_wait():
    message = describe_page_event(
        {
            "event": "waiting_manual_action",
            "data": {
                "reason": "login_required",
                "signals": {
                    "targetReady": True,
                    "targetSummary": {
                        "plan": "Pro",
                        "period": "quarter",
                        "buttonText": "特惠订阅",
                    },
                },
            },
        }
    )

    assert message == "等待手动登录；已识别目标：Pro / 连续包季 / 特惠订阅"


def test_describe_page_event_reports_waiting_for_armed_window():
    message = describe_page_event(
        {
            "event": "state",
            "data": {
                "state": "WAITING_FOR_TIME",
                "signals": {
                    "targetReady": True,
                    "targetSummary": {
                        "plan": "Max",
                        "period": "month",
                        "buttonText": "订阅",
                    },
                },
            },
        }
    )

    assert message == "已识别目标，等待开抢时间：Max / 连续包月 / 订阅"


def test_describe_page_event_reports_locked_restock_button_ready():
    message = describe_page_event(
        {
            "event": "state",
            "data": {
                "state": "READY",
                "signals": {
                    "targetReady": True,
                    "targetSummary": {
                        "plan": "Pro",
                        "period": "month",
                        "buttonText": "暂时售罄 ｜06月14日 10:00 补货",
                        "buttonLocked": True,
                    },
                },
            },
        }
    )

    assert message == "已找到灰色补货按钮，尝试解灰点击：Pro / 连续包月 / 暂时售罄 ｜06月14日 10:00 补货"


def test_describe_page_event_reports_scroll_to_target():
    message = describe_page_event(
        {
            "event": "scroll_to_target",
            "data": {"text": "Pro 最受欢迎"},
        }
    )

    assert message == "已滚动到目标区域：Pro 最受欢迎"


def test_describe_page_event_prefixes_parallel_page_index():
    message = describe_page_event(
        {
            "event": "click_attempt",
            "page_index": 2,
            "data": {"attempts": 8, "text": "暂时售罄"},
        }
    )

    assert message == "[页面2] 点击尝试 #8：暂时售罄"


def test_describe_page_event_reports_recovery_reload():
    message = describe_page_event(
        {
            "event": "state",
            "page_index": 3,
            "data": {
                "state": "RECOVERY_RELOAD",
                "signals": {
                    "targetSummary": {
                        "plan": "Pro",
                        "period": "month",
                        "buttonText": "抢购人数过多，请刷新再试",
                    },
                },
            },
        }
    )

    assert message == "[页面3] 页面拥挤，准备刷新重试：Pro / 连续包月 / 抢购人数过多，请刷新再试"
