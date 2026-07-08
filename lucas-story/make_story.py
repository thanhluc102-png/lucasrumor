import os
import base64
import requests
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

def main():
    print("Đang cào sản phẩm mới từ lucas.vn...")
    product = product_fetch.pick_product()
    if not product:
        print("Không tìm thấy sản phẩm hợp lệ.")
        return
        
    print(f"Đã chọn: {product['title']}")
    
    print("Đang tải ảnh sản phẩm...")
    img_b64 = fetch_image_b64(product["image_url"])
    
    output_png = "mock_story.png"
    print("Đang vẽ giao diện Story...")
    render_story_png(product, output_png, img_b64)
    print(f"Hoàn tất tạo ảnh: {output_png}")
    print(f"Link sản phẩm: {product['link']}")

if __name__ == "__main__":
    main()
