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

## One-Click Launch

Double-click:

```text
一键启动.bat
```

The launcher creates the virtual environment, installs dependencies, installs the project-local Chromium browser, and opens the visual GUI.

## Visual Launcher

In the GUI:

1. Select plan: `Lite`, `Pro`, or `Max`.
2. Select period: `连续包月`, `连续包季`, or `连续包年`.
3. Set start time, for example `09:59:58`.
4. Optionally set `手动按钮 CSS` if automatic target detection misses the subscription button. The matched button will be highlighted in the browser.
5. Adjust `开抢窗口与点击策略` if needed:
   - `提前开始秒数`: start clicking this many seconds before `开抢时间`.
   - `持续秒数`: keep the armed click window open after `开抢时间`.
   - `点击间隔 ms`: delay between click attempts.
   - `最大点击次数`: `0` means unlimited.
   - `拥挤先点次数`: click crowded retry buttons this many times before refreshing.
   - `刷新间隔 ms`: minimum delay between recovery refreshes.
   - `服务器时间校准`: read the target page's HTTP `Date` header and use the calculated offset for the start window.
   - `校准采样数`: number of server-time samples; the lowest-latency sample is used.
   - `到点强制刷新一次`: request one page refresh at `开抢时间` before clicking.
6. Keep `强制解灰点击` enabled for the high-demand sale window.
7. For manual testing before the official time, enable `立即测试（忽略开抢时间）`.
8. Click `保存配置`.
9. Click `启动抢购`.

The GUI shows runner output, can stop the process, and can open logs or screenshots.

## Manual Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PLAYWRIGHT_BROWSERS_PATH = ".\.ms-playwright"
python -m playwright install chromium
```

## Manual Run

```powershell
$env:PYTHONPATH = ".\src"
$env:PLAYWRIGHT_BROWSERS_PATH = ".\.ms-playwright"
python runner.py --config config.yaml
```

## Configure

The GUI writes `config.yaml` for you. You can also edit it manually:

```yaml
target:
  plan: Pro
  period: quarter
  button_selector: null
timing:
  click_cooldown_ms: 80
  max_click_attempts: 0
  crowd_retry_clicks_before_reload: 15
  recovery_reload_interval_ms: 1500
  server_time_sync: true
  server_time_samples: 5
  t0_reload: false
```

Allowed plans: `Lite`, `Pro`, `Max`.

Allowed periods:

- `month`: 连续包月
- `quarter`: 连续包季
- `year`: 连续包年

Do not put your password in source files. Use the persistent browser profile and log in manually on first run.

## Runtime Notes

On first run:

1. Browser opens.
2. Log in manually if needed.
3. Complete captcha manually if shown.
4. Leave the browser open.
5. The script monitors the configured target.

`timing.start_at` does not delay opening the page. The page opens immediately so login, captcha, and frontend resources can be ready early. The injected script only performs controlled target clicks inside the configured armed window.

When the page shows a crowded retry message such as `抢购人数过多，请刷新再试`, the script now treats that message as the target button: it unlocks/clicks it repeatedly first, then asks the runner to refresh after `timing.crowd_retry_clicks_before_reload` attempts.

When `timing.server_time_sync` is enabled, the runner samples the target page's HTTP `Date` header before opening parallel pages and injects `server_time_offset_ms` into the page script. If sampling fails, it falls back to local time.

When `timing.t0_reload` is enabled, the page script requests one refresh at `timing.start_at`, then waits briefly for the runner to reload and re-inject the script before click attempts resume.

When payment or final confirmation is detected, the script beeps, saves a screenshot, writes logs, and stops clicking. You must take over manually.

## Logs

- `logs/events.jsonl`: structured redacted event log
- `screenshots/`: handoff screenshots

Sensitive keys such as password, token, cookie, authorization, phone, and account are redacted.

## Notes

This tool can reduce the delay between page state changes and a controlled click. It cannot create stock, bypass account eligibility, bypass captcha, bypass server-side limits, or bypass payment.
