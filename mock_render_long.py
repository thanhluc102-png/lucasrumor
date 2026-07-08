import main
import requests
import base64

data = {
    "title": "Apple tung Beta 3 của iOS 27 cho lập trình viên",
    "summary": "Apple vừa phát hành phiên bản Beta thứ ba của iOS 27 và iPadOS 27 dành cho các nhà phát triển. Đây là bước tiếp theo trong lộ trình thử nghiệm trước khi ra mắt chính thức. Cộng đồng lập trình viên đang tích cực cài đặt và chia sẻ những tính năng mới mẻ được ẩn giấu sâu bên trong mã nguồn, hứa hẹn một sự lột xác toàn diện về mặt giao diện và hiệu năng cho thế hệ iPhone tiếp theo.",
    "category": "Thảo luận",
    "category_icon": "🔥",
    "visual_type": "community",
    "bullets": [],
    "sources": ["r/apple - Reddit"], 
    "visual_data": {
        "subreddit": "apple",
        "upvotes": 4500,
        "comments": 1200
    }
}

try:
    img_resp = requests.get("https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?auto=format&fit=crop&w=800&q=80", timeout=5)
    img_b64 = f"data:image/jpeg;base64,{base64.b64encode(img_resp.content).decode()}"
except:
    img_b64 = None

main.render_png(data, "mock_long.png", img_b64)
print("Done rendering mock_long.png")
