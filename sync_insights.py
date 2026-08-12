import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")

def get_engagement(post_id, token):
    # Thử gọi dạng post_id trực tiếp, nếu lỗi thử ghép {page_id}_{post_id}
    for pid in (post_id, f"{FB_PAGE_ID}_{post_id}"):
        url = f"https://graph.facebook.com/v25.0/{pid}"
        params = {
            "fields": "reactions.summary(true),comments.summary(true),shares",
            "access_token": token
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                res = r.json()
                reactions = res.get("reactions", {}).get("summary", {}).get("total_count", 0)
                comments = res.get("comments", {}).get("summary", {}).get("total_count", 0)
                shares = res.get("shares", {}).get("count", 0)
                return {
                    "reactions": reactions,
                    "comments": comments,
                    "shares": shares,
                    "score": reactions * 1 + comments * 3 + shares * 5
                }
        except Exception as e:
            print(f"Error fetching stats for {pid}: {e}")
    return None

def sync_file(file_path):
    p = Path(file_path)
    if not p.exists():
        print(f"File {file_path} không tồn tại. Bỏ qua.")
        return
    
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Lỗi đọc {file_path}: {e}")
        return
        
    updated = False
    now = datetime.now()
    
    for entry in data:
        post_id = entry.get("post_id")
        if not post_id:
            continue
            
        publish_time_str = entry.get("publish_time")
        try:
            if publish_time_str.endswith("Z"):
                publish_time_str = publish_time_str[:-1]
            publish_time = datetime.fromisoformat(publish_time_str)
        except Exception:
            publish_time = now - timedelta(days=10)
            
        # Sync posts from the last 7 days
        if now - publish_time < timedelta(days=7):
            print(f"Đang đồng bộ tương tác cho {post_id} ({entry.get('title') or entry.get('product_name')})...")
            stats = get_engagement(post_id, FB_PAGE_TOKEN)
            if stats:
                entry["performance"] = stats
                updated = True
                print(f" -> Kết quả: L:{stats['reactions']}, C:{stats['comments']}, S:{stats['shares']}")
                
    if updated:
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Đã cập nhật {file_path}\n")

def main():
    if not FB_PAGE_TOKEN:
        print("Thiếu FB_PAGE_TOKEN. Bỏ qua.")
        return
        
    print("=== ĐỒNG BỘ TƯƠNG TÁC FANPAGE ===")
    
    # Đồng bộ tin đồn
    sync_file("post_history.json")

    # Đồng bộ bài sản phẩm (từ lucas-story/main_product.py)
    sync_file("product_history.json")

if __name__ == "__main__":
    main()
