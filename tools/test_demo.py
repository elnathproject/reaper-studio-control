#!/usr/bin/env python3
"""Drive the page in demo mode with real touch events and check the pan controls.

The demo mimics REAPER's rule that a SET/TRACK/.../PAN or WIDTH value starting with
"+" or "-" is a relative change, so a bug that sends negative absolute values shows up here.

Usage:  python3 tools/test_demo.py [path/to/reaper-studio-control.html]
"""
import asyncio, os, sys, pathlib
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reaper-studio-control.html"
KEY = "reaperStudioControl.v5"

async def main():
    async with async_playwright() as p:
        opts = {"args": ["--no-sandbox"]}
        if os.environ.get("CHROME_PATH"):
            opts["executable_path"] = os.environ["CHROME_PATH"]
        elif os.path.exists("/usr/bin/google-chrome"):
            opts["executable_path"] = "/usr/bin/google-chrome"
        browser = await p.chromium.launch(**opts)
        ctx = await browser.new_context(viewport={"width": 1024, "height": 768}, has_touch=True)
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(HTML.as_uri())
        await page.evaluate("([k,v])=>localStorage.setItem(k,v)", [KEY, '{"ver":2,"view":"mixer","pan":1}'])
        await page.reload()
        await page.wait_for_timeout(800)
        cdp = await ctx.new_cdp_session(page)

        async def touch_drag(track, which, dy, steps=8):
            box = await page.locator(f'.strip[data-id="{track}"] [data-d="{which}"] .knob').bounding_box()
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            pt = lambda yy: [{"x": x, "y": yy, "id": 1}]
            await cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": pt(y)})
            for i in range(1, steps + 1):
                await cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": pt(y + dy * i / steps)})
                await page.wait_for_timeout(60)       # several messages, as a real finger would produce
            await cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            await page.wait_for_timeout(1500)         # past the 700 ms hold: the label now shows what REAPER reports
            return await page.locator(f'.strip[data-id="{track}"] [data-d="{which}"] .panv').inner_text()

        cases = [
            ("balance, drag down 30 px   (C   -> 40L)", 1, "pan", 30, "40L"),
            ("balance, drag up 45 px     (40L -> 20R)", 1, "pan", -45, "20R"),
            ("dual pan L, drag up 45 px  (40L -> 20R)", 5, "pan", -45, "20R"),
            ("dual pan R, drag down 90  (70R -> 50L)", 5, "pan2", 90, "50L"),
            ("width, drag up 30 px       (W60 -> W100)", 2, "pan2", -30, "W100"),
            ("width, drag down 105       (W100 -> W-40)", 2, "pan2", 105, "W-40"),
        ]
        failed = 0
        for name, track, which, dy, expect in cases:
            got = await touch_drag(track, which, dy)
            ok = got == expect
            failed += not ok
            print(("ok   " if ok else "FAIL ") + name + "  got " + got + ", expected " + expect)
        async def double_tap(selector):
            box = await page.locator(selector).bounding_box()
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            for _ in range(2):
                await cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y, "id": 1}]})
                await cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                await page.wait_for_timeout(80)
            await page.wait_for_timeout(1500)

        resets = [
            ("double tap resets balance to centre", '.strip[data-id="1"] [data-d="pan"] .knob', '.strip[data-id="1"] [data-d="pan"] .panv', "C"),
            ("double tap resets dual pan L to 100L", '.strip[data-id="5"] [data-d="pan"] .knob', '.strip[data-id="5"] [data-d="pan"] .panv', "100L"),
            ("double tap resets width to W100", '.strip[data-id="2"] [data-d="pan2"] .knob', '.strip[data-id="2"] [data-d="pan2"] .panv', "W100"),
        ]
        for name, knob, label, expect in resets:
            await double_tap(knob)
            got = await page.locator(label).inner_text()
            ok = got == expect
            failed += not ok
            print(("ok   " if ok else "FAIL ") + name + "  got " + got + ", expected " + expect)

        # volume: drag a fader down by touch, then double tap to return to 0.0 dB
        box = await page.locator('.strip[data-id="2"] .fader').bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        await cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y, "id": 1}]})
        for i in range(1, 7):
            await cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y + 10 * i, "id": 1}]})
            await page.wait_for_timeout(60)
        await cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        await page.wait_for_timeout(1500)
        db = await page.locator('.strip[data-id="2"] .sdb').inner_text()
        ok = db.startswith("-") and db != "-inf"
        failed += not ok
        print(("ok   " if ok else "FAIL ") + "fader drag down 60 px lowers the level  got " + db)
        await double_tap('.strip[data-id="2"] .fader')
        db = await page.locator('.strip[data-id="2"] .sdb').inner_text()
        ok = db == "0.0"
        failed += not ok
        print(("ok   " if ok else "FAIL ") + "fader double tap returns to 0.0  got " + db)

        # language: English by default, Italian from the settings, kept after a reload
        async def texts():
            seg = await page.locator("#viewSeg button").all_inner_texts()
            return seg, await page.locator("#connText").inner_text(), await page.locator("#gearBtn").get_attribute("title")

        seg, conn, gear = await texts()
        ok = seg == ["Keys", "Mixer", "Both"] and conn == "Demo: main.js not loaded" and gear == "Settings"
        failed += not ok
        print(("ok   " if ok else "FAIL ") + "default language is English  got", seg, conn, gear)
        await page.click("#gearBtn")
        await page.select_option('select[data-k="lang"]', "it")
        await page.wait_for_timeout(300)
        seg, conn, gear = await texts()
        title = await page.locator("#settingsCard h2").inner_text()
        ok = seg == ["Tasti", "Mixer", "Entrambi"] and conn == "Demo: main.js assente" and gear == "Impostazioni" and title == "Impostazioni"
        failed += not ok
        print(("ok   " if ok else "FAIL ") + "switching to Italian updates the page and the open settings  got", seg, conn, gear, title)
        await page.reload()
        await page.wait_for_timeout(600)
        seg, conn, gear = await texts()
        ok = seg == ["Tasti", "Mixer", "Entrambi"]
        failed += not ok
        print(("ok   " if ok else "FAIL ") + "Italian is kept after a reload  got", seg)

        print("page errors:", errors or "none")
        await browser.close()
        sys.exit(1 if failed or errors else 0)

asyncio.run(main())
