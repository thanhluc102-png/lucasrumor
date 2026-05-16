import os
import json
import random
from datetime import datetime
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
BUMPED_POSTS_FILE = "bumped_posts.json"

def get_bumped_posts():
    if os.path.exists(BUMPED_POSTS_FILE):
        try:
            with open(BUMPED_POSTS_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_bumped_post(post_id):
    posts = get_bumped_posts()
    if post_id not in posts:
        posts.append(post_id)
        with open(BUMPED_POSTS_FILE, "w") as f:
            json.dump(posts, f, indent=2)

def get_recent_posts():
    all_posts = []
    url = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/feed"
    params = {
        "access_token": FB_PAGE_TOKEN,
        "limit": 100,
        "fields": "id,message,created_time,comments.summary(true)"
    }
    
    # Quét tối đa 20 trang (khoảng 2000 bài viết)
    for _ in range(20):
        resp = requests.get(url, params=params if not all_posts else None)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", [])
        if not posts:
            break
        all_posts.extend(posts)
        
        url = data.get("paging", {}).get("next")
        if not url:
            break
            
    return all_posts

def generate_comment(post_message):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Bạn là quản trị viên Fanpage Lucas Combo (chuyên bán phụ kiện Apple).
Đọc nội dung bài đăng sau đây trên Fanpage của bạn:
"{post_message}"

Hãy viết một bình luận (comment) ngắn gọn, tự nhiên, thân thiện để tương tác lại với bài viết này.
Mục tiêu là "đào mộ" bài viết cũ để nó hiện lại lên News Feed.
Yêu cầu:
- Rất ngắn gọn (1-2 câu).
- Khéo léo nhắc đến việc mua phụ kiện tại Lucas Combo (website: lucas.vn) hoặc rủ rê mọi người ghé shop.
- Vui vẻ, lịch sự, phù hợp với ngữ cảnh của bài đăng.
- Chỉ in ra nội dung bình luận, tuyệt đối không có phần mở đầu hay kết thúc dư thừa.
"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()

def post_comment(post_id, message):
    url = f"https://graph.facebook.com/v25.0/{post_id}/comments"
    data = {
        "message": message,
        "access_token": FB_PAGE_TOKEN
    }
    resp = requests.post(url, data=data)
    if resp.status_code != 200:
        raise Exception(resp.text)
    return resp.json()

def main():
    if not all([FB_PAGE_TOKEN, FB_PAGE_ID, ANTHROPIC_API_KEY]):
        print("Thiếu biến môi trường (FB_PAGE_TOKEN, FB_PAGE_ID, ANTHROPIC_API_KEY). Bỏ qua.")
        return

    print("Đang lấy danh sách bài viết gần đây...")
    try:
        posts = get_recent_posts()
    except Exception as e:
        print(f"Lỗi khi lấy posts: {e}")
        return

    bumped_posts = get_bumped_posts()
    valid_posts = []
    now = datetime.now()
    
    for p in posts:
        if "message" not in p:
            continue
        if p["id"] in bumped_posts:
            continue
        
        try:
            # Chỉ bump bài có >= 50 comment
            comments_data = p.get("comments", {})
            summary = comments_data.get("summary", {})
            total_comments = summary.get("total_count", 0)
            
            if total_comments < 50:
                continue

            # Graph API datetime format: "2025-05-13T10:00:00+0000"
            # Some python versions don't like +0000 in strptime %z if it's strictly formatted
            time_str = p["created_time"].replace("+0000", "")
            created_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
            
            # Chỉ bump các bài đã đăng được hơn 24 tiếng (để tránh bump bài mới)
            if (now - created_time).total_seconds() > 24 * 3600:
                valid_posts.append(p)
        except Exception as e:
            pass

    if not valid_posts:
        print("Không có bài viết cũ nào hợp lệ để đào mộ.")
        return

    # Random 1 bài để bump
    target_post = random.choice(valid_posts)
    print(f"Chọn bài viết ID: {target_post['id']}")
    print(f"Trích đoạn: {target_post['message'][:60]}...")

    print("Đang dùng AI tạo comment...")
    try:
        comment_msg = generate_comment(target_post["message"])
        print(f"Comment sinh ra:\n{comment_msg}\n")
    except Exception as e:
        print(f"Lỗi khi sinh comment: {e}")
        return

    print("Đang đăng comment lên Facebook...")
    try:
        res = post_comment(target_post["id"], comment_msg)
        print(f"✅ Đã comment thành công! Comment ID: {res['id']}")
        save_bumped_post(target_post["id"])
    except Exception as e:
        print(f"⚠️ Lỗi khi post comment: {e}")

if __name__ == "__main__":
    main()
