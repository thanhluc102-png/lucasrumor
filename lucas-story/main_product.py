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

# Lịch sử nằm ở gốc repo để sync_insights.py (chạy từ gốc) đọc được.
HISTORY_FILE = Path(__file__).resolve().parent.parent / "product_history.json"


def build_caption(p: dict) -> str:
    """Caption cho bài feed. Không để link trong caption (Facebook bóp reach) —
    link đặt hàng đưa xuống bình luận đầu tiên, giống playbook của Lucas."""
    lines = [p["title"]]
    if p.get("description"):
        lines += ["", p["description"]]
    if p.get("regular_price"):
        lines += ["", f"Giá {p['price']} (giá gốc {p['regular_price']})"]
    else:
        lines += ["", f"Giá {p['price']}"]
    lines += ["Link đặt hàng ở bình luận đầu tiên 👇", "",
              "#LucasCombo #chinhhang #phukienapple"]
    return "\n".join(lines)


def send_facebook_feed(image_path: str, caption: str, page_token: str, page_id: str):
    """Đăng ảnh + caption lên BẢNG TIN (giống main.py), trả về post_id.

    Trước đây bài sản phẩm đăng qua /photo_stories (Story 24h). Story không có
    reactions/comments/shares — Graph API trả thẳng '(#100) Tried accessing
    nonexisting field (reactions)' — nên vòng tự học không chấm điểm được bài
    nào. Đổi sang /photos để dùng đúng cơ chế đo đã chạy tốt cho tin đồn.
    """
    url = f"https://graph.facebook.com/v25.0/{page_id}/photos"
    payload = {"caption": caption, "access_token": page_token}
    print("Đang đăng ảnh sản phẩm lên bảng tin...")
    with open(image_path, "rb") as f:
        resp = requests.post(url, data=payload, files={"source": f})
    if resp.status_code != 200:
        print(f"  ⚠️ Chi tiết lỗi Facebook: {resp.text}")
    resp.raise_for_status()
    result = resp.json()
    post_id = result.get("post_id") or result.get("id")
    print(f"✅ Đã đăng lên bảng tin! (post_id: {post_id})")
    return post_id


def comment_link(post_id: str, link: str, page_token: str):
    try:
        requests.post(
            f"https://graph.facebook.com/v25.0/{post_id}/comments",
            data={"message": f"Đặt hàng: {link}", "access_token": page_token},
            timeout=15,
        )
        print("  💬 Đã comment link đặt hàng.")
    except Exception as e:
        print(f"  ⚠️ Không comment được link: {e}")


def save_post_to_history(post_id: str, product: dict):
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append({
        "post_id": post_id,
        "title": product.get("title"),
        "summary": product.get("description"),
        "price": product.get("price"),
        "regular_price": product.get("regular_price"),
        "link": product.get("link"),
        "publish_time": datetime.now().isoformat(),
        "performance": None,
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
        post_id = send_facebook_feed(frame_path, build_caption(product), fb_token, fb_page_id)
        if post_id:
            save_post_to_history(post_id, product)
            if product.get("link"):
                comment_link(post_id, product["link"], fb_token)
    else:
        print("Thiếu FB_PAGE_TOKEN/FB_PAGE_ID — bỏ qua bước đăng.")

if __name__ == "__main__":
    main()
