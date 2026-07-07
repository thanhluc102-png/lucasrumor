import os
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

def send_facebook_photo(image_path: str, caption: str, page_token: str, page_id: str):
    url = f"https://graph.facebook.com/v25.0/{page_id}/photos"
    payload = {"caption": caption, "access_token": page_token}
    print("Đang tải Ảnh (Story Layout) lên Facebook...")
    with open(image_path, "rb") as f:
        resp = requests.post(url, data=payload, files={"source": f})
    if resp.status_code != 200:
        print(f"Lỗi Facebook Photo: {resp.text}")
    resp.raise_for_status()
    result = resp.json()
    post_id = result.get("post_id", result.get("id", "?"))
    print(f"✅ Đã đăng Ảnh sản phẩm thành công! (post_id: {post_id})")
    return result

def comment_on_facebook_post(post_id: str, message: str, page_token: str):
    if not post_id or post_id == "?": return
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    resp = requests.post(url, data={"message": message, "access_token": page_token})
    if resp.status_code == 200:
        print(f"💬 Đã comment link thành công!")

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
        fb_caption = f"🔥 {product['title']}\n\n"
        if product.get('regular_price'):
            fb_caption += f"💰 Giá SALE: {product['price']} (Gốc: {product['regular_price']})\n\n"
        else:
            fb_caption += f"💰 Giá: {product['price']}\n\n"
        fb_caption += "👇 BẤM VÀO LINK Ở PHẦN BÌNH LUẬN ĐỂ MUA NGAY!\n\n"
        fb_caption += "#LucasCombo #PhuKienApple #KhuyenMai"
        
        fb_result = send_facebook_photo(frame_path, fb_caption, fb_token, fb_page_id)
        post_id = fb_result.get("post_id", fb_result.get("id"))
        if post_id:
            comment_msg = f"🛒 Mua ngay tại đây: {product['link']}"
            comment_on_facebook_post(post_id, comment_msg, fb_token)

if __name__ == "__main__":
    main()
