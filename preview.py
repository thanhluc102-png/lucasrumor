import base64
import requests
from main import render_png

def get_sample_image():
    try:
        r = requests.get("https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?w=800&q=80", timeout=10)
        r.raise_for_status()
        return f"data:image/jpeg;base64,{base64.b64encode(r.content).decode()}"
    except:
        return None

data = {
    "title": "Apple ra mắt MacBook Pro M4 siêu mỏng",
    "summary": "Mẫu MacBook Pro mới dự kiến sẽ có thiết kế mỏng hơn đáng kể, sử dụng chip M4 siêu mạnh mẽ và thời lượng pin vượt trội so với thế hệ tiền nhiệm.",
    "category": "Rumor",
    "category_icon": "💻",
    "bullets": [
        "Màn hình OLED viền siêu mỏng, độ sáng cao hơn 20%.",
        "Tích hợp chip M4 Max cho hiệu năng xử lý AI vượt trội.",
        "Màu sắc mới Space Black chống bám vân tay."
    ],
    "sources": ["Bloomberg", "MacRumors"],
}

img_b64 = get_sample_image()
try:
    out = render_png(data, "preview.png", img_b64)
    print(f"Rendered to {out}")
except Exception as e:
    print(f"Error: {e}")
