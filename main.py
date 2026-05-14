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
from PIL import Image
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
    """Render template.html (auto height) rồi fit vào canvas vuông 1080×1080."""
    tmp = output_path + ".tmp.png"
    render_png(data, tmp, image_b64)

    img = Image.open(tmp)
    w, h = img.size
    new_h = int(h * 1080 / w)
    img = img.resize((1080, new_h), Image.LANCZOS)

    # Canvas vuông: nếu ảnh cao hơn 1080 thì scale xuống vừa 1080 chiều cao
    if new_h <= 1080:
        canvas = Image.new("RGB", (1080, 1080), "#0f172a")
        canvas.paste(img, (0, 0))
    else:
        new_w = int(w * 1080 / h)
        img = img.resize((new_w, 1080), Image.LANCZOS)
        canvas = Image.new("RGB", (1080, 1080), "#0f172a")
        x = (1080 - new_w) // 2
        canvas.paste(img, (x, 0))

    canvas.save(output_path)
    Path(tmp).unlink(missing_ok=True)
    return output_path


def send_telegram(image_path: str, caption: str, token: str, chat_id: str):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(image_path, "rb") as f:
        resp = requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"photo": f})
    resp.raise_for_status()
    return resp.json()


def send_facebook(image_path: str, caption: str, page_token: str, page_id: str, delay_hours: int = 0):
    """Đăng ảnh + caption lên Facebook Page qua Graph API v25.0."""
    url = f"https://graph.facebook.com/v25.0/{page_id}/photos"
    
    payload = {"caption": caption, "access_token": page_token}
    if delay_hours > 0:
        payload["published"] = "false"
        payload["scheduled_publish_time"] = str(int(datetime.now().timestamp()) + delay_hours * 3600)

    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            data=payload,
            files={"source": f},
        )
    if resp.status_code != 200:
        print(f"  ⚠️ Chi tiết lỗi Facebook: {resp.text}")
    resp.raise_for_status()
    result = resp.json()
    post_id = result.get("post_id", result.get("id", "?"))
    
    if delay_hours > 0:
        print(f"  ✅ Đã lên lịch Facebook sau {delay_hours}h (post_id: {post_id})")
    else:
        print(f"  ✅ Đã đăng ngay lên Facebook! (post_id: {post_id})")
    return result


def get_chat_id(token: str):
    resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates")
    updates = resp.json().get("result", [])
    if not updates:
        return None
    return updates[-1]["message"]["chat"]["id"]


def main():
    api_key    = os.environ.get("ANTHROPIC_API_KEY")
    tg_token   = os.environ.get("TELEGRAM_TOKEN")
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    fb_token   = os.environ.get("FB_PAGE_TOKEN")
    fb_page_id = os.environ.get("FB_PAGE_ID")

    if not api_key:
        print("Thiếu ANTHROPIC_API_KEY"); return
    if not tg_token:
        print("Thiếu TELEGRAM_TOKEN"); return

    fb_enabled = bool(fb_token and fb_page_id)
    if fb_enabled:
        print("📘 Facebook đăng fanpage: BẬT")
    else:
        print("📘 Facebook: TẮT (thiếu FB_PAGE_TOKEN hoặc FB_PAGE_ID)")

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
            render_png(data, f"digest_{idx}.png", img)
            render_tiktok_png(data, img, f"tiktok_{idx}.png")
            caption = f"{emoji} {data['title']}\n\n{data['summary']}"
            send_telegram(f"digest_{idx}.png", caption, tg_token, str(tg_chat_id))
            send_telegram(f"tiktok_{idx}.png", "📱 TikTok version", tg_token, str(tg_chat_id))
            print(f"  Đã gửi Telegram + TikTok!")

            # --- Đăng lên Facebook Fanpage ---
            if fb_enabled:
                try:
                    bullets = data.get("bullets", [])
                    sources = data.get("sources", [])
                    fb_caption = f"{emoji} {data['title']}\n\n"
                    fb_caption += f"{data['summary']}\n\n"
                    if bullets:
                        fb_caption += "\n".join(f"• {b}" for b in bullets) + "\n\n"
                    if sources:
                        fb_caption += f"📎 Nguồn: {', '.join(sources)}\n\n"
                    fb_caption += "#LucasCombo #Apple #TinCongNghe #iPhone #MacBook #AppleNews"
                    
                    delay_hours = (idx - 1) * 4
                    send_facebook(f"digest_{idx}.png", fb_caption, fb_token, fb_page_id, delay_hours)
                except Exception as fb_err:
                    print(f"  ⚠️ Lỗi đăng Facebook bài {idx}: {fb_err}")

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
