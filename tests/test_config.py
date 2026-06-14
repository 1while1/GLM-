from pathlib import Path

import pytest

from glm_grabber.config import ConfigError, GrabberConfig, load_config


def test_load_config_applies_runtime_defaults(tmp_path: Path):
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
    assert config.safety.force_unlock is True
    assert config.safety.replay_requests is False
    assert config.timing.normal_check_interval_ms == 200
    assert config.timing.armed_check_interval_ms == 20
    assert config.timing.armed_before_seconds == 0
    assert config.timing.click_cooldown_ms == 80
    assert config.timing.max_click_attempts == 0
    assert config.timing.crowd_retry_clicks_before_reload == 15
    assert config.timing.recovery_reload_interval_ms == 1500


def test_optional_expected_price_text_accepts_empty_string(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: quarter
  expected_price_text: ""
page:
  url: "https://www.bigmodel.cn/glm-coding"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.target.expected_price_text is None


def test_optional_button_selector_accepts_empty_string(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: quarter
  button_selector: ""
page:
  url: "https://www.bigmodel.cn/glm-coding"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.target.button_selector is None


def test_load_config_accepts_selector_and_timing_boost_options(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: month
  button_selector: ".package-card-btn"
page:
  url: "https://www.bigmodel.cn/glm-coding"
timing:
  server_time_sync: false
  server_time_samples: 3
  t0_reload: true
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.target.button_selector == ".package-card-btn"
    assert config.timing.server_time_sync is False
    assert config.timing.server_time_samples == 3
    assert config.timing.t0_reload is True


def test_max_click_attempts_zero_means_unlimited(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: month
page:
  url: "https://www.bigmodel.cn/glm-coding"
timing:
  max_click_attempts: 0
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.timing.max_click_attempts == 0


def test_crowd_retry_clicks_before_reload_can_be_configured(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: month
page:
  url: "https://www.bigmodel.cn/glm-coding"
timing:
  crowd_retry_clicks_before_reload: 12
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.timing.crowd_retry_clicks_before_reload == 12


def test_armed_before_seconds_accepts_zero_for_exact_start(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: month
page:
  url: "https://www.bigmodel.cn/glm-coding"
timing:
  armed_before_seconds: 0
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.timing.armed_before_seconds == 0


def test_browser_parallel_pages_accepts_small_positive_integer(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
target:
  plan: Pro
  period: month
page:
  url: "https://www.bigmodel.cn/glm-coding"
browser:
  parallel_pages: 3
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.browser.parallel_pages == 3


@pytest.mark.parametrize("parallel_pages", [0, -1, 9])
def test_browser_parallel_pages_rejects_out_of_range_values(tmp_path: Path, parallel_pages: int):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"""
target:
  plan: Pro
  period: month
page:
  url: "https://www.bigmodel.cn/glm-coding"
browser:
  parallel_pages: {parallel_pages}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_file)


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
