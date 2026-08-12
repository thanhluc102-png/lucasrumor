import os
import json
import base64
import requests
import subprocess
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
import product_fetch

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def _load_logo_b64() -> str:
    path = Path(__file__).parent / "logo.png"
    if not path.exists():
        return ""
    data = path.read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode()}"

LOGO_B64 = _load_logo_b64()

def fetch_image_b64(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        r.raise_for_status()
        mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
    except Exception as e:
        print(f"Không lấy được ảnh tĩnh: {e}")
        return None

def render_story_png(data: dict, output_path: str = "mock_story.png", image_b64: str | None = None):
    env = Environment(loader=FileSystemLoader("."))
    html = env.get_template("template_story.html").render(
        image_b64=image_b64,
        logo_b64=LOGO_B64,
        **data
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path

# Lịch sử nằm ở gốc repo — chỉ để biết đã đăng gì, KHÔNG dùng chấm điểm:
# Story không có reactions/comments/shares, và chỉ số riêng của Story thì app
# chưa có quyền đọc. Ghi lại vẫn hữu ích để tra cứu và tránh đăng trùng.
HISTORY_FILE = Path(__file__).resolve().parent.parent / "product_history.json"


def send_facebook_story(image_path: str, page_token: str, page_id: str):
    """Đăng ảnh lên Facebook Story 24h. Trả về story post_id (hoặc None)."""
    upload_url = f"https://graph.facebook.com/v25.0/{page_id}/photos"
    print("Đang tải ảnh lên server Facebook...")
    with open(image_path, "rb") as f:
        resp = requests.post(upload_url,
                             data={"published": "false", "access_token": page_token},
                             files={"source": f})
    if resp.status_code != 200:
        print(f"Lỗi upload ảnh: {resp.text}")
    resp.raise_for_status()
    photo_id = resp.json().get("id")

    story_url = f"https://graph.facebook.com/v25.0/{page_id}/photo_stories"
    print(f"Đang đẩy ảnh (ID: {photo_id}) lên bảng tin Story...")
    story_resp = requests.post(story_url,
                               data={"photo_id": photo_id, "access_token": page_token})
    if story_resp.status_code != 200:
        print(f"Lỗi đăng Story: {story_resp.text}")
    story_resp.raise_for_status()

    print("✅ Đã đăng thành công lên Facebook Story 24h!")
    return (story_resp.json() or {}).get("post_id")


def save_post_to_history(post_id, product: dict):
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append({
        "post_id": post_id,
        "channel": "story",
        "title": product.get("title"),
        "price": product.get("price"),
        "link": product.get("link"),
        "publish_time": datetime.now().isoformat(),
    })
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  📝 Đã ghi {HISTORY_FILE.name} ({len(history)} bài)")


def main():
    print("Đang cào sản phẩm mới từ lucas.vn...")
    product = product_fetch.pick_product()
    if not product:
        print("Không tìm thấy sản phẩm hợp lệ.")
        return
        
    print(f"Đã chọn: {product['title']}")
    img_b64 = fetch_image_b64(product["image_url"])
    
    frame_path = "frame_product.png"
    render_story_png(product, frame_path, img_b64)
    
    fb_token = os.environ.get("FB_PAGE_TOKEN")
    fb_page_id = os.environ.get("FB_PAGE_ID")
    
    if fb_token and fb_page_id:
        post_id = send_facebook_story(frame_path, fb_token, fb_page_id)
        save_post_to_history(post_id, product)
    else:
        print("Thiếu FB_PAGE_TOKEN/FB_PAGE_ID — bỏ qua bước đăng.")

if __name__ == "__main__":
    main()
