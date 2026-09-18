import os

BASE_URL = os.getenv("STUDIO_TEST_URL", "http://127.0.0.1:8765")
"""Manual AI workflow and visible progress, against a running local server."""

from playwright.sync_api import sync_playwright
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    errors = []
    requests = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url))
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.locator('[data-dialog="settings-dialog"]').click()
    assert page.locator("#complete-story").is_checked()
    assert page.locator("#agenda").is_checked()
    page.locator("#complete-story").uncheck()
    page.locator("#agenda").uncheck()
    page.locator("#settings-dialog [data-close]").last.click()
    page.locator("#prompt").fill("GCP")
    page.locator("#content").fill(
        "## Pilot\n- A reviewed idea.\n## Conclusion\n- A clear next step."
    )
    page.locator("#pictures-button").click()
    page.locator("#picture-files").set_input_files(str(ROOT / "static/kaar-logo.png"))
    page.wait_for_selector(".picture-row input")
    page.locator(".picture-row input").fill("Pilot")
    page.locator("#pictures-dialog [data-close]").last.click()
    page.locator("#plan").click()
    page.wait_for_function("!document.querySelector('#export').disabled", timeout=60000)
    assert page.locator("#storyboard .story-card").count() == 4
    page.get_by_role("button", name="Edit slide 2: Pilot", exact=True).click()
    page.locator('[aria-label="Slide 2 title"]').fill("Edited pilot")
    page.locator("#view-storyboard").click()
    assert "Edited pilot" in page.locator("#storyboard").inner_text()
    page.locator("#view-outline").click()
    for provider, domain in [
        ("claude", "claude.ai"),
        ("gemini", "gemini.google.com"),
        ("chatgpt", "chatgpt.com"),
    ]:
        context.route(
            f"https://{domain}/**",
            lambda route: route.fulfill(
                content_type="text/html", body="<h1>AI website fixture</h1>"
            ),
        )
        page.locator("#ai-menu-button").click()
        page.locator("[data-provider=" + provider + "]").click()
        page.wait_for_function(
            "document.querySelector('#prompt-output').value.includes('GCP')"
        )
        assert page.locator("#editor-fields").is_enabled()
        page.locator("#copy-generated-prompt").click()
        page.wait_for_function(
            "document.querySelector('#prompt-status').textContent.startsWith('Copied')"
        )
        assert "exactly 8 content slides" in page.evaluate(
            "navigator.clipboard.readText()"
        )
        if provider == "claude":
            page.screenshot(path=str(ROOT / ".build/manual-prompt.png"))
        with context.expect_page() as opened:
            page.locator("#open-provider").click()
        ai_tab = opened.value
        ai_tab.wait_for_url(f"https://{domain}/**")
        assert len(context.pages) == 2
        assert page.url == BASE_URL + "/"
        assert ai_tab.evaluate("window.opener===null")
        ai_tab.close()
        assert page.locator("#prompt").input_value() == "GCP"
        assert "A reviewed idea" in page.locator("#content").input_value()
        assert page.locator("#picture-count").inner_text() == "1 added"
        assert (
            page.locator('[aria-label="Slide 2 title"]').input_value() == "Edited pilot"
        )
        assert page.locator("#export").is_enabled()
    page.reload()
    page.wait_for_selector("#prompt")
    assert page.locator('[aria-label="Slide 2 title"]').input_value() == "Edited pilot"
    page.locator("#content").focus()
    page.locator("#content").press("Control+End")
    page.evaluate(
        "navigator.clipboard.writeText('\\n## Response\\n- Pasted response.')"
    )
    page.locator("#paste-content").click()
    page.wait_for_function(
        "document.querySelector('#content').value.includes('Pasted response')"
    )
    assert page.locator("#export").is_disabled()
    page.evaluate(
        "Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('blocked')},readText:async()=>{throw Error('blocked')}}})"
    )
    page.locator("#copy-prompt").click()
    page.wait_for_function("!document.querySelector('#copy-generated-prompt').disabled")
    page.locator("#copy-generated-prompt").click()
    assert "Ctrl+C" in page.locator("#prompt-status").inner_text()
    page.locator("#prompt-dialog [data-close]").click()
    page.locator("#paste-content").click()
    assert "Ctrl+V" in page.locator("#progress").inner_text()
    page.locator("#plan").click()
    page.wait_for_function("!document.querySelector('#export').disabled", timeout=60000)
    page.route(
        "**/api/generate", lambda route: route.fulfill(json={"id": "progress-fixture"})
    )
    stage = {"value": "export"}

    def poll(route):
        if stage["value"] == "export":
            route.fulfill(
                json={
                    "status": "running",
                    "stage": "export",
                    "current": 2,
                    "total": 4,
                    "message": "Building editable slides",
                    "title": "Pilot",
                }
            )
        elif stage["value"] == "packaging":
            route.fulfill(
                json={
                    "status": "running",
                    "stage": "packaging",
                    "message": "Packaging your file",
                }
            )
        else:
            route.fulfill(
                json={"status": "error", "message": "Example recoverable failure"}
            )

    page.route("**/api/jobs/progress-fixture", poll)
    page.locator("#export").click()
    page.wait_for_function(
        "document.querySelector('#loading-topic').textContent.includes('Slide 2 of 4')"
    )
    assert page.locator("#loading-bar").get_attribute("value") == "25"
    for w, h in [(1366, 768), (1280, 720), (1024, 768), (1280, 665), (1920, 1080)]:
        page.set_viewport_size({"width": w, "height": h})
        box = page.locator("#loading").bounding_box()
        assert box["y"] + box["height"] <= h
        assert page.evaluate("document.documentElement.scrollHeight") == h
    page.screenshot(path=str(ROOT / ".build/manual-progress.png"))
    stage["value"] = "packaging"
    page.wait_for_function(
        "document.querySelector('#loading-step').textContent.includes('Packaging')"
    )
    assert page.locator("#loading-bar").get_attribute("value") is None
    stage["value"] = "error"
    page.wait_for_function("!document.querySelector('#editor-fields').disabled")
    assert "Example recoverable failure" in page.locator("#error").inner_text()
    assert page.locator("#loading").get_attribute("data-state") == "error"
    page.unroute("**/api/generate")
    page.unroute("**/api/jobs/progress-fixture")
    page.locator("#export").click()
    page.wait_for_selector("#download:visible", timeout=60000)
    assert page.locator("#loading-bar").get_attribute("value") == "100"
    assert page.locator("#loading").get_attribute("data-state") == "done"
    assert (
        page.request.get(
            BASE_URL + page.locator("#download").get_attribute("href")
        ).status
        == 200
    )
    # Removal updates the actual export plan, survives refresh, and invalidates the old file.
    count = page.locator("#outline details").count()
    row = page.locator("#outline details").nth(1)
    if row.get_attribute("open") is None:
        row.locator("summary").click()
    row.get_by_role("button", name="Remove slide 2", exact=True).click()
    assert page.locator("#outline details").count() == count - 1
    assert page.locator("#download").is_hidden()
    page.reload()
    page.wait_for_selector("#outline details")
    assert page.locator("#outline details").count() == count - 1
    page.locator('[data-dialog="settings-dialog"]').click()
    assert not page.locator("#agenda").is_checked()
    page.locator("#agenda").check()
    page.locator("#settings-dialog [data-close]").last.click()
    assert page.locator("#export").is_disabled()
    page.reload()
    page.locator('[data-dialog="settings-dialog"]').click()
    assert page.locator("#agenda").is_checked()
    page.locator("#settings-dialog [data-close]").last.click()
    page.evaluate(
        "const k='kaartech-studio-draft-v1';const d=JSON.parse(localStorage.getItem(k));d.version=1;d.stale=false;localStorage.setItem(k,JSON.stringify(d))"
    )
    # New document context avoids pagehide writing the current revision over this legacy fixture.
    legacy = context.new_page()
    legacy.goto(BASE_URL)
    legacy.wait_for_selector("#outline details")
    assert legacy.locator("#export").is_disabled()
    assert (
        "design engine has been updated" in legacy.locator("#review-hint").inner_text()
    )
    assert legacy.locator("#content").input_value()
    legacy.close()
    assert not any("/api/ai/generate" in r for r in requests)
    # A refreshed tab reconnects to a saved durable job.
    recovery_id = "e" * 32
    saved_outline = page.evaluate(
        "JSON.parse(localStorage.getItem('kaartech-studio-draft-v1')).current"
    )
    page.route(
        "**/api/jobs/" + recovery_id,
        lambda route: route.fulfill(json={"status": "done", "result": saved_outline}),
    )
    page.evaluate(
        "id => sessionStorage.setItem('oneclick-away-active-job', JSON.stringify({id, path:'/api/plan'}))",
        recovery_id,
    )
    page.reload()
    page.wait_for_function(
        "document.querySelector('#progress').textContent === 'Your saved job is complete.'"
    )
    assert page.evaluate("sessionStorage.getItem('oneclick-away-active-job')") is None
    assert page.locator("#export").is_enabled()
    assert not errors, errors
    print(
        "PASS: separate AI tabs preserve Studio; graphical storyboard editing; draft restoration; clipboard fallbacks; visible progress; error recovery; real download; slide removal; agenda setting persistence; no automation calls."
    )
    browser.close()
