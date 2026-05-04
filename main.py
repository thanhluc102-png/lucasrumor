import os
import base64
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
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


def fetch_image_b64(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        r.raise_for_status()
        mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
    except Exception as e:
        print(f"  Không lấy được ảnh: {e}")
        return None


def fetch_article_image(data: dict) -> str | None:
    """Fetch ảnh cho bài (Reddit direct URL hoặc og:image từ báo). Trả về base64."""
    image_url = data.get("image_url")
    article_link = data.get("article_link")
    if image_url:
        print(f"  Đang lấy ảnh Reddit...")
        img = fetch_image_b64(image_url)
    elif article_link:
        print(f"  Đang lấy ảnh từ {article_link.split('/')[2]}...")
        img = fetch_og_image_b64(article_link)
    else:
        img = None
    print(f"  {'Có ảnh' if img else 'Không có ảnh'}")
    return img


def render_png(data: dict, output_path: str = "digest.png", image_b64: str | None = None):
    date_str = datetime.now().strftime("%d/%m/%Y")
    env = Environment(loader=FileSystemLoader("."))
    html = env.get_template("template.html").render(
        date=date_str,
        image_b64=image_b64,
        logo_b64=LOGO_B64,
        **{k: v for k, v in data.items() if k not in ("article_link", "image_url")},
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


def render_tiktok_png(data: dict, image_b64: str | None, output_path: str) -> str:
    """Render ảnh 4:5 (1080×1350) — dùng cho Telegram, TikTok và Facebook."""
    date_str = datetime.now().strftime("%d/%m/%Y")
    env = Environment(loader=FileSystemLoader("."))
    html = env.get_template("template_tiktok.html").render(
        date=date_str,
        image_b64=image_b64,
        logo_b64=LOGO_B64,
        **{k: v for k, v in data.items() if k not in ("article_link", "image_url")},
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 540, "height": 675},
            device_scale_factor=2,   # 2x → 1080×1350 (4:5)
        )
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=output_path)
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
    result, new_seen = rss_fetch.run(client, limit_per_source=5, mode="top3")

    if not result:
        print("Không có tin mới."); return

    news_stories   = result.get("news", [])
    reddit_stories = result.get("reddit", [])
    total = len(news_stories) + len(reddit_stories)

    def send_story(data, idx, emoji):
        try:
            img = fetch_article_image(data)
            out = f"story_{idx}.png"
            render_tiktok_png(data, img, out)
            caption = f"{emoji} {data['title']}\n\n{data['summary']}"
            send_telegram(out, caption, tg_token, str(tg_chat_id))
            print(f"  Đã gửi!")
        except Exception as e:
            print(f"  Lỗi bài {idx}: {e}")

    print(f"\n📰 Tin báo ({len(news_stories)} bài):")
    for i, data in enumerate(news_stories, 1):
        print(f"\n[{i}/{total}] {data['title']}")
        send_story(data, i, "🍎")

    print(f"\n🔴 Reddit community ({len(reddit_stories)} bài):")
    for i, data in enumerate(reddit_stories, 1):
        idx = len(news_stories) + i
        print(f"\n[{idx}/{total}] {data['title']}")
        send_story(data, idx, "🔥")

    rss_fetch.save_seen(new_seen)


if __name__ == "__main__":
    main()
