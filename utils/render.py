import asyncio
import json
import pathlib
from playwright.async_api import async_playwright

# One browser per bot process. Starting Chromium for every passport/welcome
# was the main source of long waits and resource leaks.
_playwright = None
_browser = None
_lock = asyncio.Lock()


async def _get_browser():
    global _playwright, _browser
    async with _lock:
        if _browser and _browser.is_connected():
            return _browser
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        return _browser


async def _render_template(template_name: str, data: dict) -> bytes:
    tpl_path = pathlib.Path(__file__).parent.parent / "templates" / template_name
    browser = await _get_browser()
    context = await browser.new_context(
        viewport={"width": 720, "height": 1000},
        device_scale_factor=2,
    )
    page = await context.new_page()
    try:
        await page.goto(tpl_path.resolve().as_uri(), wait_until="domcontentloaded", timeout=5000)
        await page.evaluate(
            "window.renderData && window.renderData(%s)" % json.dumps(data, ensure_ascii=False)
        )
        # Не используем networkidle: внешние картинки/шрифты могут держать
        # сеть занятой бесконечно. Локального шаблона достаточно.
        try:
            await page.wait_for_timeout(200)
            await page.wait_for_function(
                "document.fonts ? document.fonts.status !== 'loading' : true",
                timeout=800,
            )
        except Exception:
            pass
        return await page.locator("body").screenshot(timeout=4000)
    finally:
        await context.close()


async def render_template(template_name: str, data: dict) -> bytes:
    # Жёсткий общий лимит: Discord-команда не должна зависать из-за Chromium.
    return await asyncio.wait_for(_render_template(template_name, data), timeout=12)


async def shutdown():
    global _browser, _playwright
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
    if _playwright:
        try:
            await _playwright.stop()
        except Exception:
            pass
        _playwright = None
