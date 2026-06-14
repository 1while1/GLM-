from pathlib import Path

import yaml

from glm_grabber.gui_config import build_runner_environment, status_from_runner_line, update_config_file


def test_update_config_file_preserves_unrelated_sections(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: quarter
page:
  url: "https://www.bigmodel.cn/glm-coding?ic=XOJGYOGNLN"
safety:
  force_unlock: false
logging:
  dir: logs
""".strip(),
        encoding="utf-8",
    )

    update_config_file(
        config_file,
        plan="Max",
        period="year",
        button_selector="",
        start_at="10:00:00",
        force_unlock=True,
        parallel_pages=3,
        armed_before_seconds=0,
        armed_after_seconds=120,
        click_cooldown_ms=80,
        max_click_attempts=0,
        crowd_retry_clicks_before_reload=15,
        recovery_reload_interval_ms=1500,
        server_time_sync=True,
        server_time_samples=5,
        t0_reload=False,
    )

    data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert data["target"]["plan"] == "Max"
    assert data["target"]["period"] == "year"
    assert data["timing"]["start_at"] == "10:00:00"
    assert data["safety"]["force_unlock"] is True
    assert data["browser"]["parallel_pages"] == 3
    assert data["logging"]["dir"] == "logs"


def test_update_config_file_writes_timing_strategy(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: quarter
page:
  url: "https://www.bigmodel.cn/glm-coding?ic=XOJGYOGNLN"
timing:
  start_at: "09:59:58"
""".strip(),
        encoding="utf-8",
    )

    update_config_file(
        config_file,
        plan="Pro",
        period="month",
        button_selector=".package-card-btn",
        start_at="10:00:00",
        force_unlock=True,
        parallel_pages=4,
        armed_before_seconds=2,
        armed_after_seconds=180,
        click_cooldown_ms=60,
        max_click_attempts=120,
        crowd_retry_clicks_before_reload=20,
        recovery_reload_interval_ms=1000,
        server_time_sync=False,
        server_time_samples=3,
        t0_reload=True,
    )

    data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert data["target"]["button_selector"] == ".package-card-btn"
    assert data["timing"]["armed_before_seconds"] == 2
    assert data["timing"]["armed_after_seconds"] == 180
    assert data["timing"]["click_cooldown_ms"] == 60
    assert data["timing"]["max_click_attempts"] == 120
    assert data["timing"]["crowd_retry_clicks_before_reload"] == 20
    assert data["timing"]["recovery_reload_interval_ms"] == 1000
    assert data["timing"]["server_time_sync"] is False
    assert data["timing"]["server_time_samples"] == 3
    assert data["timing"]["t0_reload"] is True


def test_update_config_file_normalizes_empty_start_time(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: quarter
page:
  url: "https://www.bigmodel.cn/glm-coding"
""".strip(),
        encoding="utf-8",
    )

    update_config_file(
        config_file,
        plan="Lite",
        period="month",
        button_selector=None,
        start_at="",
        force_unlock=False,
        parallel_pages=1,
        armed_before_seconds=0,
        armed_after_seconds=120,
        click_cooldown_ms=80,
        max_click_attempts=0,
        crowd_retry_clicks_before_reload=15,
        recovery_reload_interval_ms=1500,
        server_time_sync=True,
        server_time_samples=5,
        t0_reload=False,
    )

    data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert data["timing"]["start_at"] is None


def test_status_from_runner_line_detects_manual_wait():
    assert status_from_runner_line("等待手动验证码；已识别目标：Pro / 连续包季 / 特惠订阅") == "等待手动验证码"


def test_status_from_runner_line_ignores_parallel_page_prefix():
    assert status_from_runner_line("[页面2] 点击尝试 #8：暂时售罄") == "正在点击订阅"


def test_status_from_runner_line_detects_recovery_reload_with_page_prefix():
    assert status_from_runner_line("[页面2] 页面拥挤，准备刷新重试：Pro / 连续包月") == "刷新重试中"


def test_status_from_runner_line_detects_waiting_for_time():
    assert status_from_runner_line("已识别目标，等待开抢时间：Max / 连续包月 / 订阅") == "等待开抢时间"


def test_build_runner_environment_forces_utf8_subprocess_output(tmp_path: Path):
    env = build_runner_environment({"PATH": "base"}, tmp_path)

    assert env["PYTHONPATH"] == str(tmp_path / "src")
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == str(tmp_path / ".ms-playwright")
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"
    assert env["PATH"] == "base"
