import os
import base64
import subprocess
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
import anthropic
import rss_fetch
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def _load_logo_b64() -> str:
    path = Path(__file__).parent / "logo.png"
    if not path.exists():
        return ""
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
    image_url = data.get("image_url")
    article_link = data.get("article_link")
    if image_url:
        print(f"  Đang lấy ảnh tĩnh...")
        img = fetch_image_b64(image_url)
    elif article_link:
        print(f"  Đang lấy ảnh từ bài báo...")
        img = fetch_og_image_b64(article_link)
    else:
        img = None
    return img

def render_frame_png(data: dict, output_path: str = "frame.png", image_b64: str | None = None):
    date_str = datetime.now().strftime("%d/%m/%Y")
    env = Environment(loader=FileSystemLoader("."))
    html = env.get_template("template_reels.html").render(
        date=date_str,
        image_b64=image_b64,
        logo_b64=LOGO_B64,
        **{k: v for k, v in data.items() if k not in ("article_link", "image_url", "source")},
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Viewport cố định 1080x1920 cho định dạng dọc
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path

def generate_video(image_path: str, output_mp4: str, duration: int = 15):
    print(f"  Đang dùng FFmpeg để render video {output_mp4} (dài {duration}s)...")
    
    # Đảm bảo có file âm thanh
    bgm_path = "bgm.mp3"
    if not os.path.exists(bgm_path):
        print("  Không tìm thấy nhạc nền, đang tự tạo âm thanh lofi (tiếng mưa/nhiễu thư giãn)...")
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
        print("  ✅ Tạo video thành công!")
        return output_mp4
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Lỗi render FFmpeg: {e}")
        return None

def send_facebook_video(video_path: str, description: str, page_token: str, page_id: str):
    """Đăng video lên Facebook Page dưới dạng Reels/Video qua Graph API."""
    url = f"https://graph.facebook.com/v25.0/{page_id}/videos"
    payload = {"description": description, "access_token": page_token}
    print("  Đang tải video lên Facebook...")
    with open(video_path, "rb") as f:
        resp = requests.post(url, data=payload, files={"source": f})
        
    if resp.status_code != 200:
        print(f"  ⚠️ Chi tiết lỗi Facebook Video: {resp.text}")
    resp.raise_for_status()
    result = resp.json()
    post_id = result.get("post_id", result.get("id", "?"))
    print(f"  ✅ Đã đăng Video/Reel thành công! (post_id: {post_id})")
    return result

def comment_on_facebook_post(post_id: str, message: str, page_token: str):
    if not post_id or post_id == "?": return
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    resp = requests.post(url, data={"message": message, "access_token": page_token})
    if resp.status_code == 200:
        print(f"  💬 Đã comment thành công: {message[:30]}...")

def main():
    api_key    = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Thiếu ANTHROPIC_API_KEY"); return

    client = anthropic.Anthropic(api_key=api_key)
    print("Đang tìm bài viral nhất theo khung giờ của sub...")
    
    # Tái sử dụng logic cũ: lấy 1 bài tuỳ theo khung giờ (xen kẽ News và Reddit)
    result, new_seen = rss_fetch.run(client, limit_per_source=5, mode="single_sub")

    if not result:
        print("Không có bài mới thoả mãn (có ảnh)."); return

    try:
        source = result.get("source", "")
        is_reddit = source.startswith("r/")
        emoji = "🔥" if is_reddit else "🍎"
        
        print(f"\n🗞️ Đã chọn bài: {result['title']} (từ {source})")
        
        # 1. Lấy ảnh nền
        img_b64 = fetch_article_image(result)
        
        # 2. Render HTML ra khung tĩnh
        frame_path = "frame.png"
        render_frame_png(result, frame_path, img_b64)
        
        # 3. Tạo Video với hiệu ứng Zoom-in
        video_path = "video_reels.mp4"
        generated_video = generate_video(frame_path, video_path, duration=15)
        
        if generated_video:
            print(f"🎉 Hoàn thành xử lý video: {generated_video}")
            
            fb_token   = os.environ.get("FB_PAGE_TOKEN")
            fb_page_id = os.environ.get("FB_PAGE_ID")
            
            if fb_token and fb_page_id:
                bullets = result.get("bullets", [])
                fb_desc = f"{emoji} {result['title']}\n\n"
                fb_desc += f"{result['summary']}\n\n"
                if bullets:
                    fb_desc += "\n".join(f"• {b}" for b in bullets) + "\n\n"
                fb_desc += "#LucasCombo #Apple #iPhone #MacBook"
                
                fb_result = send_facebook_video(generated_video, fb_desc, fb_token, fb_page_id)
                post_id = fb_result.get("post_id", fb_result.get("id"))
                if post_id:
                    comment_on_facebook_post(post_id, "🛍️ Săn ngay các sản phẩm Apple phụ kiện siêu HOT đang SALE tại Lucas:\n👉 https://lucas.vn/khuyen-mai", fb_token)
            
    except Exception as e:
        print(f"Lỗi xử lý bài: {e}")

    rss_fetch.save_seen(new_seen)

if __name__ == "__main__":
    main()
