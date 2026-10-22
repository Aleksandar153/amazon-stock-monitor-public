import json
import os
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright


PRODUCTS = [
    "B093QF35KZ",
    "B07K6RYVJ5",
    "B0C1H3K2V4",
    "B0C1GYD3KN",
    "B07K6PVR8B",
    "B07K6RYVHR",
]

STATE_FILE = Path("stock_state.json")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def send_telegram(message):
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    response.raise_for_status()


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)
    except Exception as exc:
        print(
            f"Could not read previous state: {exc}"
        )
        return {}


def save_state(state):
    with STATE_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            state,
            file,
            indent=2,
            ensure_ascii=False,
        )


def prepare_product_page(page, url):
    response = page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    if response is None:
        raise RuntimeError(
            "Amazon returned no HTTP response."
        )

    print(f"HTTP status: {response.status}")

    page.wait_for_timeout(3000)

    continue_button = page.get_by_text(
        "Continue shopping",
        exact=True,
    )

    if continue_button.count() > 0:
        print(
            "Amazon interstitial detected."
        )
        print(
            "Clicking Continue shopping..."
        )

        continue_button.first.click()

        page.wait_for_load_state(
            "domcontentloaded",
            timeout=30000,
        )

        page.wait_for_timeout(3000)

        print(
            "Loading product again..."
        )

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(5000)


def check_product(page, asin):
    url = f"https://www.amazon.in/dp/{asin}"

    print("")
    print("=" * 60)
    print(f"Checking ASIN: {asin}")

    prepare_product_page(
        page,
        url,
    )

    print(f"Page URL: {page.url}")
    print(f"Page title: {page.title()}")

    product_title = page.locator(
        "#productTitle"
    )

    if product_title.count() == 0:
        raise RuntimeError(
            "Amazon product page not detected."
        )

    title = product_title.first.inner_text(
        timeout=5000
    ).strip()

    body_text = page.locator(
        "body"
    ).inner_text(
        timeout=10000
    )

    body_lower = body_text.lower()

    unavailable_phrases = [
        "currently unavailable",
        "temporarily out of stock",
        "currently out of stock",
        "we don't know when or if this item will be back",
    ]

    unavailable = any(
        phrase in body_lower
        for phrase in unavailable_phrases
    )

    add_to_cart = (
        page.locator(
            "#add-to-cart-button"
        ).count() > 0
    )

    buy_now = (
        page.locator(
            "#buy-now-button"
        ).count() > 0
    )

    in_stock = (
        (add_to_cart or buy_now)
        and not unavailable
    )

    print(f"Product: {title}")
    print(f"Add to Cart: {add_to_cart}")
    print(f"Buy Now: {buy_now}")
    print(
        f"Unavailable text found: {unavailable}"
    )
    print(f"IN STOCK: {in_stock}")

    return {
        "asin": asin,
        "title": title,
        "url": url,
        "in_stock": in_stock,
    }


def main():
    previous_state = load_state()
    new_state = previous_state.copy()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            locale="en-IN",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 "
                "Safari/537.36"
            ),
        )

        try:
            for asin in PRODUCTS:
                try:
                    product = check_product(
                        page,
                        asin,
                    )

                    old_status = previous_state.get(
                        asin
                    )

                    new_status = (
                        "in_stock"
                        if product["in_stock"]
                        else "out_of_stock"
                    )

                    print(
                        f"Previous state: {old_status}"
                    )
                    print(
                        f"Current state: {new_status}"
                    )

                    should_notify = (
                        product["in_stock"]
                        and old_status != "in_stock"
                    )

                    if should_notify:
                        message = (
                            "AMAZON.IN - ITEM AVAILABLE!"
                            "\n\n"
                            + product["title"]
                            + "\n\n"
                            + "The item appears to be "
                            + "purchasable now."
                            + "\n\n"
                            + product["url"]
                        )

                        send_telegram(message)

                        print(
                            "Telegram notification sent."
                        )
                    else:
                        print(
                            "No Telegram notification "
                            "needed."
                        )

                    new_state[asin] = new_status

                except Exception as exc:
                    print(
                        f"CHECK FAILED for {asin}: "
                        f"{exc}"
                    )

        finally:
            browser.close()

    save_state(new_state)

    print("")
    print("State saved:")
    print(
        json.dumps(
            new_state,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
