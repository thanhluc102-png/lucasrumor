import main
import requests
import base64

# Lấy 1 ảnh mẫu ngẫu nhiên từ mạng để giả lập ảnh gốc của bài viết Reddit
try:
    img_resp = requests.get("https://images.unsplash.com/photo-1510557880182-3d4d3cba35a5?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=80", timeout=5)
    img_b64 = f"data:image/jpeg;base64,{base64.b64encode(img_resp.content).decode()}"
except:
    img_b64 = None

data = {
    "title": "Tin đồn: Lộ diện thiết kế iPhone 17 siêu mỏng qua bản vẽ CAD",
    "summary": "Nhiều người dùng Reddit đang xôn xao bàn tán về bản vẽ rò rỉ được cho là của mẫu iPhone 17 Air sắp tới. Thiết kế mới cho thấy máy mỏng đến mức khó tin và cụm camera được xếp lại hoàn toàn khác biệt so với các thế hệ trước.",
    "category": "Thảo luận",
    "category_icon": "🔥",
    "visual_type": "community",
    "bullets": [],
    "sources": [], 
    "visual_data": {
        "subreddit": "apple",
        "upvotes": 4500,
        "comments": 1200
    }
}

main.render_png(data, "mock_digest.png", img_b64)
print("Done rendering mock_digest.png")
