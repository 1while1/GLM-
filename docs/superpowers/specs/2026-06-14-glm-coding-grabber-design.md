# GLM Coding Plan Grabber Design

## Goal

Build a single-target GLM Coding Plan purchase assistant that keeps a browser session warm, watches one configured plan and billing period, and advances only to the payment handoff point. It must not bypass captcha, must not auto-pay, and must stop on unknown or high-risk states.

## Audited Direction

The first design used aggressive button unlocking and high-frequency clicking. Two independent audits found that approach too risky because a gray button can reflect server-side stock, account eligibility, captcha, risk control, pending requests, or frontend state. The revised design keeps the fast browser-injected architecture but changes the strategy:

- Use page-injected JavaScript for low-latency DOM and network observation.
- Use Playwright only for browser lifecycle, injection, screenshots, logging, recovery, and handoff alerts.
- Prefer state confirmation over forced DOM mutation.
- Use high-frequency detection only in the start window, and use low-frequency controlled clicking.
- Never issue a second purchase attempt while a purchase-related request is in flight.
- Stop immediately on payment, final confirmation, captcha, login, target mismatch, or unknown state.

## Scope

The tool supports one configured target at a time:

- Plan: `Lite`, `Pro`, or `Max`
- Period: `month`, `quarter`, or `year`
- URL: GLM Coding Plan page
- Optional start time

It does not rotate through multiple plans, does not replay captured purchase requests by default, and does not attempt to defeat verification or payment controls.

## Architecture

### `src/glm_grabber/config.py`

Loads and validates YAML configuration. The config defines the target, timing, safety, logging, and browser profile settings. Defaults are conservative: no forced unlocks, no request replay, payment handoff enabled, screenshots enabled.

### `src/glm_grabber/state.py`

Classifies page signals and network signals into states. High-risk states take priority:

1. `PAYMENT_HANDOFF`
2. `CAPTCHA_REQUIRED`
3. `LOGIN_REQUIRED`
4. `TARGET_MISMATCH`
5. `REQUEST_IN_FLIGHT`
6. `CONFIRM_NOTICE`
7. `READY`
8. `RETRYABLE_FAILURE`
9. `UNKNOWN`

### `src/glm_grabber/logger.py`

Writes JSONL event logs without storing passwords, cookies, authorization headers, or full request bodies. Sensitive keys are redacted recursively.

### `src/glm_grabber/runner_core.py`

Contains pure helper logic used by the Playwright runner: start time parsing, wait calculation, and handoff detection summaries.

### `runner.py`

Starts a persistent Playwright Chromium context, opens the target page, injects `injector.user.js`, receives page events, handles screenshots and alerts, and performs page recovery only when safe. It does not do the fast polling loop itself.

### `injector.user.js`

Runs inside the target page. It observes DOM and network activity, validates the target plan and period at the container level, triggers controlled clicks, and sends structured events to the runner. It does not auto-pay.

## Behavior

1. Load config and open a persistent browser profile.
2. Navigate to the GLM Coding Plan URL.
3. Inject the page script before or immediately after page load.
4. If login is required, pause and ask the user to log in manually.
5. If captcha appears, pause and ask the user to solve it manually.
6. Before the configured start window, observe passively.
7. During the start window, increase local target-container checks.
8. When target plan and period are both confirmed, click once if no purchase request is in flight.
9. If a known notice or non-payment subscription confirmation appears and still matches the configured target, click once to continue.
10. If a purchase-related request is pending, hold the in-flight lock until a success or retryable failure is classified.
11. If payment or final confirmation is detected, stop automation, save screenshot, alert the user, and leave the page open.
12. If an unknown or target-mismatch state appears, stop or pause without further clicks.

## Safety Rules

- Never store the user's password in source files or logs.
- Prefer existing browser session cookies over auto-login.
- Redact cookie, token, authorization, password, account, phone, and credential values in logs.
- Do not click buttons whose target plan, period, and price cannot be confirmed.
- Do not click global buttons by index.
- Do not remove generic overlays. Captcha, login, notice, payment, and error overlays are states, not obstacles.
- Do not replay captured purchase requests in v1.
- Use an in-flight lock for purchase requests.
- Stop at payment handoff.

## Timing Defaults

- Normal DOM check interval: `200ms`
- Armed DOM check interval: `50ms`
- Armed window before start: `30s`
- Armed window after start: `120s`
- Click cooldown: `700ms`
- Max click attempts per page session: `5`
- Recovery reload interval: `5s`

## Verification

The implementation should include tests for:

- Config validation and conservative defaults.
- State classification priority.
- Sensitive data redaction.
- Start time wait calculations.

Manual dry-run verification should confirm:

- The browser opens with a persistent profile.
- The injector reports target detection without final payment action.
- Login and captcha states pause automation.
- Payment handoff detection stops automation and saves a screenshot.
