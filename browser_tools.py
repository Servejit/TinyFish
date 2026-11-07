from playwright.sync_api import sync_playwright

DANGEROUS = ["send", "submit", "buy", "purchase", "pay", "transfer", "delete", "remove", "publish", "place order", "confirm booking", "confirm payment"]

class Browser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    def start(self, headless=True):
        if self.page:
            return
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless, args=["--no-sandbox"])
        self.page = self.browser.new_page(viewport={"width": 1365, "height": 900})
        self.page.set_default_timeout(12000)

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        self.playwright = None
        self.browser = None
        self.page = None

    def describe(self):
        if not self.page:
            return "No page open."
        try:
            return "URL: " + self.page.url + "\nTitle: " + self.page.title() + "\nPage text:\n" + self.page.locator("body").inner_text(timeout=5000)[:6500]
        except Exception as exc:
            return "Page read error: " + str(exc)

    def execute(self, action, args, allow_actions=False):
        if not self.page:
            return {"ok": False, "message": "Browser is not running."}
        try:
            if action == "open":
                url = str(args.get("url", "")).strip()
                if not url.startswith("https://") and not url.startswith("http://"):
                    return {"ok": False, "message": "Use a complete http:// or https:// URL."}
                self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                return {"ok": True, "message": "Opened " + self.page.url + ". Title: " + self.page.title()}
            if action == "extract":
                return {"ok": True, "message": self.describe()}
            if action == "wait":
                seconds = max(1, min(int(args.get("seconds", 2)), 10))
                self.page.wait_for_timeout(seconds * 1000)
                return {"ok": True, "message": "Waited " + str(seconds) + " seconds."}
            if action == "click":
                target = str(args.get("text", args.get("selector", ""))).strip()
                if not target:
                    return {"ok": False, "message": "Specify visible text or selector."}
                if not allow_actions and any(word in target.lower() for word in DANGEROUS):
                    return {"ok": False, "blocked": True, "message": "Safety block: this may be a consequential action. Review the page and enable consequential actions only if you explicitly intend to proceed."}
                if args.get("text"):
                    self.page.get_by_text(target, exact=True).first.click()
                else:
                    self.page.locator(target).first.click()
                self.page.wait_for_timeout(700)
                return {"ok": True, "message": "Clicked. Current URL: " + self.page.url}
            if action == "fill":
                selector = str(args.get("selector", "")).strip()
                if not selector:
                    return {"ok": False, "message": "A CSS selector is required."}
                self.page.locator(selector).first.fill(str(args.get("value", "")))
                return {"ok": True, "message": "Filled " + selector}
            return {"ok": False, "message": "Unknown action: " + str(action)}
        except Exception as exc:
            return {"ok": False, "message": "Browser action failed: " + str(exc)}
