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

def generate_video(image_path: str, output_mp4: str, duration: int = 15):
    bgm_path = "bgm.mp3"
    if not os.path.exists(bgm_path):
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=c=pink:r=44100:a=0.1,lowpass=f=200", "-t", "15", bgm_path], stderr=subprocess.DEVNULL)
        
    frames = duration * 30
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-stream_loop", "-1", "-i", bgm_path,
        "-vf", f"zoompan=z='min(zoom+0.001,1.15)':d={frames}:s=1080x1920:fps=30",
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_mp4
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_mp4
    except subprocess.CalledProcessError as e:
        print(f"Lỗi render FFmpeg: {e}")
        return None

def send_facebook_video(video_path: str, description: str, page_token: str, page_id: str):
    url = f"https://graph.facebook.com/v25.0/{page_id}/videos"
    payload = {"description": description, "access_token": page_token}
    print("Đang tải Reel lên Facebook...")
    with open(video_path, "rb") as f:
        resp = requests.post(url, data=payload, files={"source": f})
    if resp.status_code != 200:
        print(f"Lỗi Facebook Video: {resp.text}")
    resp.raise_for_status()
    result = resp.json()
    post_id = result.get("post_id", result.get("id", "?"))
    print(f"✅ Đã đăng Reel sản phẩm thành công! (post_id: {post_id})")
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
    
    video_path = "reel_product.mp4"
    generated_video = generate_video(frame_path, video_path, duration=15)
    
    if generated_video:
        fb_token = os.environ.get("FB_PAGE_TOKEN")
        fb_page_id = os.environ.get("FB_PAGE_ID")
        
        if fb_token and fb_page_id:
            fb_desc = f"🔥 {product['title']}\n\n"
            if product.get('regular_price'):
                fb_desc += f"💰 Giá SALE: {product['price']} (Gốc: {product['regular_price']})\n\n"
            else:
                fb_desc += f"💰 Giá: {product['price']}\n\n"
            fb_desc += "👇 BẤM VÀO LINK Ở PHẦN BÌNH LUẬN ĐỂ MUA NGAY!\n\n"
            fb_desc += "#LucasCombo #PhuKienApple #KhuyenMai"
            
            fb_result = send_facebook_video(generated_video, fb_desc, fb_token, fb_page_id)
            post_id = fb_result.get("post_id", fb_result.get("id"))
            if post_id:
                comment_msg = f"🛒 Mua ngay tại đây: {product['link']}"
                comment_on_facebook_post(post_id, comment_msg, fb_token)

if __name__ == "__main__":
    main()
