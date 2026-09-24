"""Browser smoke test against the generated offline report; no inference required."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto((ROOT / "index.html").as_uri())
        data = json.loads(page.locator("#dataset").text_content())
        planned = sum(len(run["rows"]) for run in data["runs"])
        generated = sum(row["status"] == "completed" for run in data["runs"] for row in run["rows"])
        for width, height in [(1440, 1000), (390, 844), (320, 740)]:
            page.set_viewport_size({"width": width, "height": height})
            page.locator("#tab-references").click()
            page.locator("#search").fill("")
            page.locator("#asset-grid img").evaluate_all(
                "images => images.forEach(image => image.loading = 'eager')"
            )
            page.wait_for_function(
                "Array.from(document.querySelectorAll('#asset-grid img')).every(i => i.complete && i.naturalWidth > 0)"
            )
            assert page.locator("#asset-grid .asset").count() == 63
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(artifacts / f"references-{width}.png"), full_page=False)
            page.locator("#search").fill("clapping")
            assert page.locator("#asset-grid .asset").count() == 1
            page.get_by_role("button", name="Inspect Clapping hands").click()
            assert page.locator("#detail").is_visible()
            assert page.locator("#detail-title").inner_text() == "Clapping hands"
            page.get_by_role("button", name="Close", exact=True).click()
            if data.get("curation"):
                page.locator("#search").fill("brain")
                page.get_by_role("button", name="Inspect Brain", exact=True).click()
                assert page.get_by_text("AI-reviewed caption", exact=True).is_visible()
                assert page.get_by_text("train", exact=True).is_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / f"pilot-detail-{width}.png"))
                page.get_by_role("button", name="Close", exact=True).click()
            page.locator("#search").fill("no-matching-reference-xyz")
            assert page.get_by_text("No matching references.", exact=True).is_visible()
            page.locator("#search").fill("")
            page.locator("#tab-benchmark").click()
            assert page.locator(".benchmark-row").count() == 40
            page.locator("#category").select_option(index=1)
            assert page.locator(".benchmark-row").count() == 10
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(artifacts / f"benchmark-{width}.png"), full_page=False)
            page.locator("#category").select_option("")
            page.locator("#tab-runs").click()
            assert (
                page.locator("#run-summary").inner_text()
                == f"{generated} generated / {planned} planned samples"
            )
            if generated:
                page.wait_for_function(
                    "Array.from(document.querySelectorAll('#run-list img')).every(i => i.complete && i.naturalWidth > 0)"
                )
                assert page.locator("#run-list img").count() == generated
                page.locator("#run-list .preview").first.click()
                assert page.locator("#detail").is_visible()
                assert page.locator("#detail-body img").evaluate(
                    "i => i.complete && i.naturalWidth > 0"
                )
                assert page.get_by_role("link", name="Open original PNG").is_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / f"output-detail-{width}.png"))
                page.get_by_role("button", name="Close", exact=True).click()
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(artifacts / f"runs-{width}.png"), full_page=False)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#tab-references").click()
        page.get_by_role("button", name="32", exact=True).click()
        assert (
            page.locator("#asset-grid img").first.evaluate("i => i.getBoundingClientRect().width")
            == 32
        )
        page.locator("#dark").check()
        assert page.locator("body").get_attribute("class") == "dark"
        page.locator("#asset-grid select").first.select_option("keep")
        page.reload()
        assert page.locator("#asset-grid select").first.input_value() == "keep"
        with page.expect_download() as event:
            page.get_by_role("button", name="Export reviews").click()
        export = artifacts / "test-reviews.json"
        event.value.save_as(export)
        payload = json.loads(export.read_text())
        assert len(payload["review_decisions"]) == 1
        assert next(iter(payload["review_decisions"].values()))["value"] == "keep"
        assert not errors, errors
        context.close()
        browser.close()
    print(
        "Passed: desktop/mobile layout, images, filters, modal, tabs, sizes, persistence, export; no JS errors"
    )


if __name__ == "__main__":
    main()
