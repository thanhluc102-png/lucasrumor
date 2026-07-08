import main
import requests
import base64

mock_data = [
    {
        "title": "Tin đồn: iPhone 17 Air lộ thiết kế mỏng nhất lịch sử Apple",
        "summary": "Cộng đồng mạng đang truyền tay nhau bản vẽ được cho là của iPhone 17 Air. Viền màn hình gần như vô hình, cụm camera mỏng gọn chưa từng thấy.",
        "category": "Thảo luận", "category_icon": "🔥", "visual_type": "community",
        "visual_data": {"subreddit": "iphone", "upvotes": 5200, "comments": 850},
        "img_url": "https://images.unsplash.com/photo-1510557880182-3d4d3cba35a5?auto=format&fit=crop&w=800&q=80"
    },
    {
        "title": "Góc khoe góc làm việc Mac Studio tối giản cực chất",
        "summary": "Một người dùng khoe góc setup Mac Studio kết hợp màn hình Pro Display XDR siêu gọn gàng. Ai nhìn vào cũng muốn dọn dẹp lại bàn làm việc ngay lập tức.",
        "category": "Thảo luận", "category_icon": "🔥", "visual_type": "community",
        "visual_data": {"subreddit": "mac", "upvotes": 3100, "comments": 420},
        "img_url": "https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?auto=format&fit=crop&w=800&q=80"
    },
    {
        "title": "Leak: Màn hình iPad Pro OLED thế hệ mới có viền siêu mỏng",
        "summary": "Hình ảnh rò rỉ tấm nền OLED được cho là của iPad Pro thế hệ tiếp theo. Màn hình sáng rực rỡ và viền mỏng hơn đáng kể so với bản hiện tại.",
        "category": "Tin đồn", "category_icon": "🔥", "visual_type": "community",
        "visual_data": {"subreddit": "ipad", "upvotes": 4100, "comments": 612},
        "img_url": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?auto=format&fit=crop&w=800&q=80"
    },
    {
        "title": "Rò rỉ tính năng AI bí mật trên iOS 19",
        "summary": "Người dùng phát hiện một đoạn code lạ trong bản thử nghiệm cho thấy Siri sắp có giao diện hoàn toàn mới tích hợp ChatGPT sâu vào hệ điều hành.",
        "category": "Leak", "category_icon": "🔥", "visual_type": "community",
        "visual_data": {"subreddit": "ios", "upvotes": 2900, "comments": 350},
        "img_url": "https://images.unsplash.com/photo-1603921326210-6ead2cd24f46?auto=format&fit=crop&w=800&q=80"
    },
    {
        "title": "MacOS 16 sẽ mang trở lại widget tương tác trên màn hình Desktop?",
        "summary": "Bản phác thảo rò rỉ cho thấy Apple đang thử nghiệm giao diện Desktop mới cho MacOS với các widget nổi bật và khả năng tùy biến mạnh mẽ.",
        "category": "Thảo luận", "category_icon": "🔥", "visual_type": "community",
        "visual_data": {"subreddit": "MacOS", "upvotes": 1800, "comments": 290},
        "img_url": "https://images.unsplash.com/photo-1517059224940-d4af9eec41b7?auto=format&fit=crop&w=800&q=80"
    },
    {
        "title": "Cộng đồng tranh cãi về thiết kế Apple Watch Series X",
        "summary": "Hình ảnh render Apple Watch Series X mới nhất đang gây bão. Dây đeo nam châm kiểu mới liệu có làm mất đi khả năng tương thích của các dây cũ?",
        "category": "Cộng đồng", "category_icon": "🔥", "visual_type": "community",
        "visual_data": {"subreddit": "apple", "upvotes": 6700, "comments": 1500},
        "img_url": "https://images.unsplash.com/photo-1434493789847-2f02dc6ca35d?auto=format&fit=crop&w=800&q=80"
    }
]

for i, m in enumerate(mock_data):
    try:
        r = requests.get(m.pop("img_url"), timeout=5)
        img_b64 = f"data:image/jpeg;base64,{base64.b64encode(r.content).decode()}"
    except:
        img_b64 = None
    
    m["bullets"] = []
    m["sources"] = []
    main.render_png(m, f"mock_digest_{i}.png", img_b64)
    print(f"Generated mock_digest_{i}.png")
