import os
import base64
import requests
import subprocess
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

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
        print(f"Không lấy được ảnh: {e}")
        return None

def render_frame_png(data: dict, output_path: str = "frame.png", image_b64: str | None = None):
    date_str = datetime.now().strftime("%d/%m/%Y")
    env = Environment(loader=FileSystemLoader("."))
    html = env.get_template("template_reels.html").render(
        date=date_str,
        image_b64=image_b64,
        logo_b64=LOGO_B64,
        **data
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Viewport cố định 1080x1920
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path

def generate_video(image_path: str, bgm_path: str, output_mp4: str, duration: int = 15):
    print(f"Đang render video {output_mp4} (dài {duration}s)...")
    
    # Lệnh FFmpeg:
    # 1. Lặp ảnh tĩnh (loop 1)
    # 2. Lặp audio (stream_loop -1)
    # 3. Hiệu ứng zoompan (phóng to chậm từ 1.0 đến ~1.1 trong 15s)
    # 4. Scale cứng 1080x1920 để tránh lỗi số lẻ của libx264
    # 5. Cắt đúng duration (-t 15)
    
    # Tính số frames cho zoompan (fps=30)
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
        print("✅ Render video thành công!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Lỗi FFmpeg: {e}")

def main():
    # Mock data để test
    mock_data = {
        "title": "Màn hình OLED cho MacBook Pro 2026",
        "summary": "Apple đang thử nghiệm màn hình OLED siêu mỏng, hứa hẹn thời lượng pin vượt trội cho dòng MacBook Pro thế hệ mới.",
        "category": "Tin đồn",
        "category_icon": "🔥"
    }
    
    print("Đang lấy ảnh mockup...")
    img_b64 = fetch_image_b64("https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=1080&q=80")
    
    print("Đang render frame HTML...")
    render_frame_png(mock_data, "frame.png", img_b64)
    
    if not os.path.exists("bgm.mp3"):
        print("Đang tạo BGM giả lập (vì không có file bgm.mp3)...")
        # Sinh 1 tiếng noise thư giãn dài 15s làm bgm tạm
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=c=pink:r=44100:a=0.1,lowpass=f=200", "-t", "15", "bgm.mp3"], stderr=subprocess.DEVNULL)
        
    generate_video("frame.png", "bgm.mp3", "mock_reels.mp4", duration=15)

if __name__ == "__main__":
    main()
