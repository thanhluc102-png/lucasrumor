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
        **{k: v for k, v in data.items() if k not in ("article_link", "image_url", "source")},
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


def comment_on_facebook_post(post_id: str, message: str, page_token: str):
    """Bình luận tự động vào bài viết Facebook vừa đăng."""
    if not post_id or post_id == "?":
        return
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    payload = {"message": message, "access_token": page_token}
    resp = requests.post(url, data=payload)
    if resp.status_code == 200:
        print(f"  💬 Đã comment thành công: {message[:30]}...")
    else:
        print(f"  ⚠️ Lỗi comment ({message[:10]}...): {resp.text}")



def main():
    api_key    = os.environ.get("ANTHROPIC_API_KEY")
    fb_token   = os.environ.get("FB_PAGE_TOKEN")
    fb_page_id = os.environ.get("FB_PAGE_ID")

    if not api_key:
        print("Thiếu ANTHROPIC_API_KEY"); return

    fb_enabled = bool(fb_token and fb_page_id)
    if fb_enabled:
        print("📘 Facebook đăng fanpage: BẬT")
    else:
        print("📘 Facebook: TẮT (thiếu FB_PAGE_TOKEN hoặc FB_PAGE_ID)")

    client = anthropic.Anthropic(api_key=api_key)
    print("Đang tìm bài viral nhất theo khung giờ của sub...")
    # Chạy chế độ single_sub (luân phiên 6 sub theo từng khung giờ)
    result, new_seen = rss_fetch.run(client, limit_per_source=5, mode="single_sub")

    if not result:
        print("Không có bài mới thoả mãn (có ảnh)."); return

    def send_story(data, emoji):
        try:
            img = fetch_article_image(data)
            output_png = "digest_1.png"
            render_png(data, output_png, img)
            # --- Đăng lên Facebook Fanpage ---
            if fb_enabled:
                try:
                    bullets = data.get("bullets", [])
                    fb_caption = f"{emoji} {data['title']}\n\n"
                    fb_caption += f"{data['summary']}\n\n"
                    if bullets:
                        fb_caption += "\n".join(f"• {b}" for b in bullets) + "\n\n"
                    fb_caption += "#LucasCombo #Apple #iPhone #MacBook"
                    
                    # Đăng LIVE trực tiếp (delay_hours = 0)
                    fb_result = send_facebook(output_png, fb_caption, fb_token, fb_page_id, delay_hours=0)
                    
                    # Tự động comment sau khi đăng
                    post_id = fb_result.get("post_id", fb_result.get("id"))
                    if post_id:
                        # Comment khuyến mãi (Đã cho phép đăng lại bình thường)
                        comment_on_facebook_post(post_id, "🛍️ Săn ngay các sản phẩm Apple phụ kiện siêu HOT đang SALE tại Lucas:\n👉 https://lucas.vn/khuyen-mai", fb_token)
                        
                except Exception as fb_err:
                    print(f"  ⚠️ Lỗi đăng Facebook: {fb_err}")

        except Exception as e:
            print(f"  Lỗi xử lý bài: {e}")

    source = result.get("source", "")
    is_reddit = source.startswith("r/")
    emoji = "🔥" if is_reddit else "🍎"
    
    print(f"\n🗞️ Đã chọn bài: {result['title']} (từ {source}) - Đăng LIVE")
    send_story(result, emoji)

    rss_fetch.save_seen(new_seen)


if __name__ == "__main__":
    main()
