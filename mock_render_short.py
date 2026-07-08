import main
import requests
import base64

data = {
    "title": "Apple tung Beta 3 của iOS 27 cho lập trình viên",
    "summary": "Apple vừa phát hành phiên bản Beta 3 của iOS 27 với nhiều nâng cấp về hiệu năng và giao diện mới tuyệt đẹp.",
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

main.render_png(data, "mock_short.png", img_b64)
print("Done rendering mock_short.png")
