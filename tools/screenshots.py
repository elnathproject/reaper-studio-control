#!/usr/bin/env python3
"""Regenerate the README screenshots from the built-in demo mode.

Usage:  python3 tools/screenshots.py [path/to/reaper-studio-control.html] [output-dir]

Requires Playwright for Python and a Chromium-based browser.
Set CHROME_PATH if the browser is not found automatically.
"""
import asyncio, os, sys, pathlib
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reaper-studio-control.html"
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "screenshots"
KEY = "reaperStudioControl.v5"
OUT.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as p:
        opts = {"args": ["--no-sandbox"]}
        if os.environ.get("CHROME_PATH"):
            opts["executable_path"] = os.environ["CHROME_PATH"]
        elif os.path.exists("/usr/bin/google-chrome"):
            opts["executable_path"] = "/usr/bin/google-chrome"
        browser = await p.chromium.launch(**opts)

        async def shot(name, w, h, cfg, scale=1, play=True, extra=None, clip=None):
            ctx = await browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale)
            page = await ctx.new_page()
            await page.goto(HTML.as_uri())
            await page.evaluate("([k,v])=>localStorage.setItem(k,v)", [KEY, cfg])
            await page.reload()
            await page.wait_for_timeout(600)
            if play:
                await page.evaluate("document.querySelector('[data-a=play],.key.big').click()")
                await page.wait_for_timeout(2200)
            if extra:
                await extra(page)
            args = {"path": str(OUT / (name + ".png"))}
            if clip:
                args["clip"] = clip
            await page.screenshot(**args)
            await ctx.close()
            print("wrote", name)

        both  = '{"ver":2,"view":"both","pan":1}'
        mixer = '{"ver":2,"view":"mixer","pan":1}'
        keys  = '{"ver":2,"view":"keys"}'

        async def settings(page):
            await page.click("#gearBtn")
            await page.wait_for_timeout(300)

        await shot("hero-tablet", 1024, 768, both)
        await shot("keypad", 1024, 768, keys)
        await shot("mixer", 1024, 768, mixer)
        await shot("pan-modes", 1024, 768, mixer, scale=2, clip={"x": 10, "y": 130, "width": 740, "height": 130})
        await shot("theme-graphite", 1024, 768, '{"ver":2,"view":"mixer","pan":1,"theme":"grafite"}')
        await shot("theme-light", 1024, 768, '{"ver":2,"view":"mixer","pan":1,"theme":"chiaro"}')
        await shot("settings", 1024, 768, both, extra=settings)
        await shot("phone-mixer", 390, 780, mixer, scale=2)
        await browser.close()

asyncio.run(main())
