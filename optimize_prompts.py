import os
import json
import anthropic
from pathlib import Path

# Đọc API key từ môi trường
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

def load_history(file_path):
    p = Path(file_path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def main():
    if not ANTHROPIC_API_KEY:
        print("Thiếu ANTHROPIC_API_KEY. Bỏ qua phân tích AI.")
        return
        
    print("=== PHÂN TÍCH TƯƠNG TÁC BẰNG AI ===")
    
    # 1. Đọc lịch sử
    rumors = load_history("post_history.json")
    
    # Chỉ lấy các bài viết đã được cập nhật tương tác
    valid_rumors = [r for r in rumors if r.get("performance")]
    
    if not valid_rumors:
        print("Chưa có đủ dữ liệu tương tác để phân tích. Sử dụng hướng dẫn mặc định.")
        default_instructions = "- Ưu tiên viết ngắn gọn, giật tít tập trung vào dòng sản phẩm iPhone, MacBook, iPad.\n- Tránh nội dung mang tính chất quảng cáo lộ liễu, tăng tính thảo luận cộng đồng."
        Path("learnings.txt").write_text(default_instructions, encoding="utf-8")
        return
        
    # Tạo báo cáo tóm tắt tương tác gửi sang AI
    report_lines = []
    
    report_lines.append("--- TIN ĐỒN / THẢO LUẬN INFOGRAPHIC ---")
    for r in valid_rumors[-15:]: # lấy tối đa 15 bài gần nhất
        perf = r["performance"]
        report_lines.append(
            f"Tiêu đề: {r['title']}\n"
            f"Hook: {r['summary']}\n"
            f"Thể loại: {r['category']} ({r['visual_type']})\n"
            f"Nguồn: {r['source']}\n"
            f"Tương tác: Reactions={perf['reactions']}, Comments={perf['comments']}, Shares={perf['shares']} (Score={perf['score']})\n"
        )
        
    data_context = "\n".join(report_lines)
    
    prompt = f"""Dưới đây là thống kê tương tác thực tế từ Fanpage Lucas Combo (chuyên phụ kiện Apple) cho các bài viết (Infographic tin đồn/thảo luận) trong tuần qua.
Điểm tương tác (Score) được tính bằng: Reactions * 1 + Comments * 3 + Shares * 5.

DỮ LIỆU TƯƠNG TÁC:
{data_context}

Nhiệm vụ của bạn:
Phân tích dữ liệu trên và đúc kết thành bộ hướng dẫn cụ thể (style guide tối ưu tương tác) cho các bài viết tiếp theo.
Yêu cầu bộ hướng dẫn:
1. Nêu rõ những chủ đề hoặc góc tiếp cận nào có điểm tương tác cao nhất.
2. Nêu rõ những cấu trúc tiêu đề (headline) hoặc câu hook nào kích thích bình luận, chia sẻ nhiều nhất.
3. Chỉ ra những gì đang kém hiệu quả (nội dung/style) cần tránh hoặc thay đổi.
4. Trình bày cực kỳ ngắn gọn dưới dạng gạch đầu dòng (tổng cộng tối đa 5-8 gạch đầu dòng), viết bằng tiếng Việt rõ ràng, súc tích để đưa thẳng vào prompt hệ thống cho các lượt sinh tiếp theo.

Chỉ in ra kết quả bộ hướng dẫn dưới dạng danh sách gạch đầu dòng, tuyệt đối không thêm lời mở đầu hay kết thúc dư thừa nào.
"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        learnings = response.content[0].text.strip()
        print("-> Đã nhận phân tích từ Claude:")
        print(learnings)
        
        Path("learnings.txt").write_text(learnings, encoding="utf-8")
        print("Đã lưu learnings.txt.")
    except Exception as e:
        print(f"Lỗi khi gọi Claude AI: {e}")

if __name__ == "__main__":
    main()
