import os
import base64
import requests
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import anthropic
import rss_fetch

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def _load_logo_b64() -> str:
    path = Path(__file__).parent / "logo.png"
    data = path.read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode()}"

LOGO_B64 = _load_logo_b64()


def fetch_og_image_b64(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.find("meta", property="og:image")
        if not og:
            return None
        img_r = requests.get(og["content"], headers={"User-Agent": UA}, timeout=10)
        img_r.raise_for_status()
        mime = img_r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return f"data:{mime};base64,{base64.b64encode(img_r.content).decode()}"
    except Exception as e:
        print(f"  Không lấy được ảnh: {e}")
        return None


def render_digest_png(data: dict, output_path: str = "digest.png"):
    date_str = datetime.now().strftime("%d/%m/%Y")

    # lấy ảnh cho từng story
    for story in data["stories"]:
        link = story.pop("article_link", None)
        if link:
            story["image_b64"] = fetch_og_image_b64(link)
        else:
            story["image_b64"] = None

    env = Environment(loader=FileSystemLoader("."))
    html = env.get_template("template_digest.html").render(
        date=date_str, logo_b64=LOGO_B64, **data
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 1}, device_scale_factor=2)
        page.set_content(html, wait_until="networkidle")
        height = page.evaluate("document.body.scrollHeight")
        page.set_viewport_size({"width": 800, "height": height})
        page.screenshot(path=output_path, full_page=True)
        browser.close()

    return output_path


def render_png(data: dict, output_path: str = "digest.png"):
    date_str = datetime.now().strftime("%d/%m/%Y")

    article_link = data.get("article_link")
    image_b64 = None
    if article_link:
        print(f"  Đang lấy ảnh từ {article_link.split('/')[2]}...")
        image_b64 = fetch_og_image_b64(article_link)
        print(f"  {'Có ảnh' if image_b64 else 'Không có ảnh'}")

    env = Environment(loader=FileSystemLoader("."))
    html = env.get_template("template.html").render(
        date=date_str,
        image_b64=image_b64,
        logo_b64=LOGO_B64,
        **{k: v for k, v in data.items() if k != "article_link"},
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 800, "height": 1},
            device_scale_factor=2,  # render 2x → ảnh nét gấp đôi
        )
        page.set_content(html, wait_until="networkidle")
        height = page.evaluate("document.body.scrollHeight")
        page.set_viewport_size({"width": 800, "height": height})
        page.screenshot(path=output_path, full_page=True)
        browser.close()

    return output_path


def send_telegram(image_path: str, caption: str, token: str, chat_id: str):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(image_path, "rb") as f:
        resp = requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"photo": f})
    resp.raise_for_status()
    return resp.json()


def get_chat_id(token: str):
    resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates")
    updates = resp.json().get("result", [])
    if not updates:
        return None
    return updates[-1]["message"]["chat"]["id"]


def main():
    api_key   = os.environ.get("ANTHROPIC_API_KEY")
    tg_token  = os.environ.get("TELEGRAM_TOKEN")
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not api_key:
        print("Thiếu ANTHROPIC_API_KEY"); return
    if not tg_token:
        print("Thiếu TELEGRAM_TOKEN"); return

    client = anthropic.Anthropic(api_key=api_key)

    if not tg_chat_id:
        print("Đang lấy Telegram chat_id...")
        tg_chat_id = get_chat_id(tg_token)
        if not tg_chat_id:
            print("Chưa tìm thấy chat_id. Gửi 1 tin cho bot rồi chạy lại."); return
        print(f"Chat ID: {tg_chat_id}")

    print("Đang lấy và tổng hợp tin...")
    stories, new_seen = rss_fetch.run(client, limit_per_source=5, mode="top3")

    if not stories:
        print("Không có tin mới."); return

    for i, data in enumerate(stories, 1):
        print(f"\n[{i}/3] {data['title']}")
        img_path = render_png(data, f"digest_{i}.png")
        caption = f"🍎 {data['title']}\n\n{data['summary']}"
        send_telegram(img_path, caption, tg_token, str(tg_chat_id))
        print(f"  Đã gửi Telegram!")

    rss_fetch.save_seen(new_seen)


if __name__ == "__main__":
    main()
