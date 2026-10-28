import pathlib
import json
from playwright.async_api import async_playwright

async def render_template(template_name: str, data: dict) -> bytes:
    tpl_path = pathlib.Path(__file__).parent.parent / "templates" / template_name
    
    if "passport" in template_name:
        viewport = {"width": 720, "height": 1000}
    elif "welcome" in template_name:
        viewport = {"width": 1200, "height": 520}
    elif "organization" in template_name:
        viewport = {"width": 900, "height": 500}
    else:
        viewport = {"width": 1200, "height": 800}

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        context = await browser.new_context(
            viewport=viewport,
            device_scale_factor=2
        )
        page = await context.new_page()
        
        await page.goto(f"file://{tpl_path.resolve()}")
        await page.evaluate(f"window.renderData({json.dumps(data)})")
        
        try:
            # ИСПРАВЛЕНО: для welcome даем больше времени
            timeout = 10000 if "welcome" in template_name else 5000
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except:
            pass
            
        await page.wait_for_timeout(500) 
        
        png_bytes = await page.screenshot()
        await browser.close()
        return png_bytes