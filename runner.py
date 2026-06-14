from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright
from playwright.async_api import Error as PlaywrightError

from glm_grabber.config import GrabberConfig, load_config
from glm_grabber.logger import JsonlLogger
from glm_grabber.runner_core import (
    describe_page_event,
    estimate_server_offset_ms,
    public_config_dict,
    seconds_until_time_today,
    should_handoff,
)


ROOT = Path(__file__).resolve().parent
INJECTOR = ROOT / "injector.user.js"


async def main() -> int:
    args = parse_args()
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".ms-playwright"))
    config = load_config(args.config)
    logger = JsonlLogger(Path(config.logging.dir) / "events.jsonl")
    logger.write("runner_start", {"config": public_config(config)})

    wait_seconds = 0 if args.ignore_start_time else seconds_until_time_today(config.timing.start_at)
    if wait_seconds:
        logger.write("arming_later", {"seconds": wait_seconds, "start_at": config.timing.start_at})
        print(f"Opening page now; injector will arm in {wait_seconds}s at {config.timing.start_at}.")

    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=config.browser.user_data_dir,
                headless=config.browser.headless,
                slow_mo=config.browser.slow_mo_ms,
                viewport={"width": 1440, "height": 900},
            )
        except PlaywrightError as exc:
            message = str(exc)
            if "ProcessSingleton" in message or "profile directory" in message:
                print(
                    "浏览器配置目录正在被占用。请先关闭已经打开的抢购浏览器窗口，"
                    "或在 GUI 里点“停止”后再启动。"
                )
                logger.write("profile_in_use", {"user_data_dir": config.browser.user_data_dir})
                return 2
            raise
        stop_event = asyncio.Event()
        reload_state: dict[int, Any] = {"last": {}, "locks": {}}
        server_time_offset_ms = await calibrate_server_time(context, config, logger)
        pages = await prepare_pages(
            context,
            config,
            logger,
            args.ignore_start_time,
            stop_event,
            reload_state,
            server_time_offset_ms,
        )

        if args.ignore_start_time:
            print(f"浏览器已打开：立即测试模式已启用，{len(pages)} 个页面会同时抢购；登录/验证码请手动完成。")
        else:
            print(f"浏览器已打开：{len(pages)} 个页面会提前监控，到开抢窗口才会点击；登录/验证码请手动完成。")
        try:
            started_at = asyncio.get_running_loop().time()
            while True:
                await asyncio.sleep(1)
                if stop_event.is_set():
                    logger.write("parallel_stop_event", {})
                    break
                if all(page.is_closed() for page in pages):
                    logger.write("all_pages_closed", {})
                    break
                if args.run_seconds and asyncio.get_running_loop().time() - started_at >= args.run_seconds:
                    logger.write("run_seconds_elapsed", {"run_seconds": args.run_seconds})
                    break
        finally:
            await context.close()
    return 0


async def prepare_pages(
    context: Any,
    config: GrabberConfig,
    logger: JsonlLogger,
    ignore_start_time: bool,
    stop_event: asyncio.Event,
    reload_state: dict[int, Any],
    server_time_offset_ms: int,
) -> list[Page]:
    page_count = max(1, int(config.browser.parallel_pages))
    pages: list[Page] = []
    for index in range(1, page_count + 1):
        page = context.pages[index - 1] if index <= len(context.pages) else await context.new_page()
        pages.append(page)
        await expose_reporter(
            page,
            config,
            logger,
            page_index=index,
            ignore_start_time=ignore_start_time,
            server_time_offset_ms=server_time_offset_ms,
            stop_event=stop_event,
            reload_state=reload_state,
        )
        await inject_config(page, config, ignore_start_time=ignore_start_time, server_time_offset_ms=server_time_offset_ms)
        page.on("console", lambda msg, page_index=index: logger.write("browser_console", {"page_index": page_index, "type": msg.type, "text": msg.text}))

    print(f"Opening GLM Coding Plan page in {page_count} page(s)...")
    await asyncio.gather(*(
        open_and_inject_page(page, config, logger, ignore_start_time, index, server_time_offset_ms)
        for index, page in enumerate(pages, start=1)
    ))
    return pages


async def open_and_inject_page(
    page: Page,
    config: GrabberConfig,
    logger: JsonlLogger,
    ignore_start_time: bool,
    page_index: int,
    server_time_offset_ms: int,
) -> None:
    await page.goto(config.page.url, wait_until="domcontentloaded", timeout=60000)
    await inject_config(page, config, ignore_start_time=ignore_start_time, server_time_offset_ms=server_time_offset_ms)
    await ensure_injector(page, logger, page_index=page_index)
    logger.write("page_opened", {"page_index": page_index, "url": page.url})


async def expose_reporter(
    page: Page,
    config: GrabberConfig,
    logger: JsonlLogger,
    *,
    page_index: int,
    ignore_start_time: bool,
    server_time_offset_ms: int,
    stop_event: asyncio.Event,
    reload_state: dict[int, Any],
) -> None:
    async def report(payload: dict[str, Any]) -> None:
        payload["page_index"] = page_index
        logger.write(str(payload.get("event", "page_event")), payload)
        description = describe_page_event(payload)
        if description:
            print(description, flush=True)
        if _payload_state(payload) == "RECOVERY_RELOAD" or payload.get("event") == "t0_reload_requested":
            asyncio.create_task(
                recover_page_reload(
                    page,
                    config,
                    logger,
                    page_index=page_index,
                    ignore_start_time=ignore_start_time,
                    server_time_offset_ms=server_time_offset_ms,
                    reload_state=reload_state,
                )
            )
            return
        handoff_event = payload.get("data", {}) | {
            "url": payload.get("url", ""),
            "title": payload.get("title", ""),
        }
        if should_handoff(handoff_event):
            await handle_handoff(page, config, logger, payload)
            stop_event.set()
        elif payload.get("event") in {"paused", "stopped"}:
            print(f"[{payload.get('event')}] {json.dumps(payload.get('data', {}), ensure_ascii=False)}")

    await page.expose_function("__GLM_GRABBER_REPORT__", report)


async def recover_page_reload(
    page: Page,
    config: GrabberConfig,
    logger: JsonlLogger,
    *,
    page_index: int,
    ignore_start_time: bool,
    server_time_offset_ms: int,
    reload_state: dict[int, Any],
) -> None:
    locks = reload_state.setdefault("locks", {})
    last = reload_state.setdefault("last", {})
    lock = locks.setdefault(page_index, asyncio.Lock())
    if lock.locked():
        return
    async with lock:
        loop = asyncio.get_running_loop()
        now = loop.time()
        interval_seconds = max(0.1, config.timing.recovery_reload_interval_ms / 1000)
        previous = float(last.get(page_index, 0))
        wait_seconds = interval_seconds - (now - previous)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        last[page_index] = loop.time()
        logger.write("recovery_reload_start", {"page_index": page_index, "url": page.url})
        print(f"[页面{page_index}] 正在刷新页面重试", flush=True)
        try:
            await page.reload(wait_until="domcontentloaded", timeout=60000)
            await inject_config(page, config, ignore_start_time=ignore_start_time, server_time_offset_ms=server_time_offset_ms)
            await ensure_injector(page, logger, page_index=page_index)
            logger.write("recovery_reload_done", {"page_index": page_index, "url": page.url})
        except Exception as exc:
            logger.write("recovery_reload_error", {"page_index": page_index, "message": str(exc)})
            print(f"[页面{page_index}] 刷新重试失败：{exc}", flush=True)


def _payload_state(payload: dict[str, Any]) -> str:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return ""
    return str(data.get("state", ""))


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


async def inject_config(page: Page, config: GrabberConfig, *, ignore_start_time: bool, server_time_offset_ms: int) -> None:
    public = public_config(config, ignore_start_time=ignore_start_time, server_time_offset_ms=server_time_offset_ms)
    await page.add_init_script("window.__GLM_GRABBER_CONFIG__ = %s;" % json.dumps(public, ensure_ascii=False))
    await page.evaluate("config => { window.__GLM_GRABBER_CONFIG__ = config; }", public)


async def ensure_injector(page: Page, logger: JsonlLogger, *, page_index: int) -> None:
    marker = await page.evaluate(
        "() => ({ injected: Boolean(window.__GLM_GRABBER_INJECTED__), href: location.href })"
    )
    logger.write("injector_marker_before", {"page_index": page_index, **marker})
    await page.evaluate("() => { delete window.__GLM_GRABBER_INJECTED__; }")
    await page.add_script_tag(path=str(INJECTOR))
    marker_after = await page.evaluate(
        "() => ({ injected: Boolean(window.__GLM_GRABBER_INJECTED__), href: location.href })"
    )
    logger.write("injector_marker_after", {"page_index": page_index, **marker_after})


async def calibrate_server_time(context: Any, config: GrabberConfig, logger: JsonlLogger) -> int:
    if not config.timing.server_time_sync:
        logger.write("server_time_sync_skipped", {"enabled": False})
        return 0
    samples: list[dict[str, float]] = []
    sample_count = max(1, int(config.timing.server_time_samples))
    for index in range(sample_count):
        started_ms = datetime.now().timestamp() * 1000
        try:
            response = await context.request.get(config.page.url, timeout=15000)
            ended_ms = datetime.now().timestamp() * 1000
            date_header = response.headers.get("date")
            if not date_header:
                logger.write("server_time_sample_missing_date", {"index": index + 1, "status": response.status})
                continue
            server_ms = parsedate_to_datetime(date_header).timestamp() * 1000
            samples.append({"started_ms": started_ms, "ended_ms": ended_ms, "server_ms": server_ms})
        except Exception as exc:
            logger.write("server_time_sample_error", {"index": index + 1, "message": str(exc)})
    offset = estimate_server_offset_ms(samples)
    logger.write("server_time_sync", {"offset_ms": offset, "samples": len(samples)})
    if samples:
        print(f"服务器时间校准完成：偏移 {offset}ms（{len(samples)} 个样本）", flush=True)
    else:
        print("服务器时间校准失败，使用本机时间。", flush=True)
    return offset


def public_config(
    config: GrabberConfig,
    *,
    ignore_start_time: bool = False,
    server_time_offset_ms: int = 0,
) -> dict[str, Any]:
    return public_config_dict(
        config,
        ignore_start_time=ignore_start_time,
        server_time_offset_ms=server_time_offset_ms,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GLM Coding Plan guarded purchase assistant")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    parser.add_argument("--run-seconds", type=int, default=0, help="Optional dry-run duration before automatic exit")
    parser.add_argument("--ignore-start-time", action="store_true", help="Test mode: arm immediately instead of waiting for start_at")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("Stopped by user.")
        raise SystemExit(130)
