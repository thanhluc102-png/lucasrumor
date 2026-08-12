import os
import json
import anthropic
from datetime import datetime
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
    products = load_history("product_history.json")

    # Chỉ lấy các bài viết đã được cập nhật tương tác
    valid_rumors = [r for r in rumors if r.get("performance")]
    valid_products = [p for p in products if p.get("performance")]

    if not valid_rumors and not valid_products:
        print("Chưa có đủ dữ liệu tương tác để phân tích. Sử dụng hướng dẫn mặc định.")
        default_instructions = "- Ưu tiên viết ngắn gọn, giật tít tập trung vào dòng sản phẩm iPhone, MacBook, iPad.\n- Tránh nội dung mang tính chất quảng cáo lộ liễu, tăng tính thảo luận cộng đồng."
        Path("learnings.txt").write_text(default_instructions, encoding="utf-8")
        return
        
    # Tạo báo cáo tóm tắt tương tác gửi sang AI
    report_lines = []
    
    def fmt_rumor(r):
        perf = r["performance"]
        return (
            f"Tiêu đề: {r['title']}\n"
            f"Hook: {r['summary']}\n"
            f"Thể loại: {r['category']} ({r['visual_type']})\n"
            f"Nguồn: {r['source']}\n"
            f"Tương tác: Reactions={perf['reactions']}, Comments={perf['comments']}, "
            f"Shares={perf['shares']} (Score={perf['score']})\n"
        )

    # Cho AI nhìn TƯƠNG PHẢN thay vì 15 bài gần nhất theo thứ tự thời gian.
    # Xếp hạng cho thấy rõ đâu là thứ tạo khác biệt; lấy theo thời gian thì
    # phần lớn là bài điểm sàn na ná nhau, không rút ra được gì sắc.
    ranked = sorted(valid_rumors, key=lambda r: r["performance"]["score"], reverse=True)
    n = min(10, max(1, len(ranked) // 3))
    best, worst = ranked[:n], ranked[-n:]

    report_lines.append(f"--- TIN ĐỒN: {n} BÀI CAO ĐIỂM NHẤT (trên tổng {len(ranked)} bài) ---")
    for r in best:
        report_lines.append(fmt_rumor(r))

    report_lines.append(f"--- TIN ĐỒN: {n} BÀI THẤP ĐIỂM NHẤT ---")
    for r in worst:
        report_lines.append(fmt_rumor(r))

    if valid_products:
        report_lines.append("--- BÀI SẢN PHẨM (ảnh sản phẩm + giá) ---")
        for p in valid_products[-15:]:
            perf = p["performance"]
            report_lines.append(
                f"Sản phẩm: {p.get('title')}\n"
                f"Mô tả: {p.get('summary')}\n"
                f"Giá: {p.get('price')}" + (f" (gốc {p['regular_price']})" if p.get('regular_price') else "") + "\n"
                f"Tương tác: Reactions={perf['reactions']}, Comments={perf['comments']}, Shares={perf['shares']} (Score={perf['score']})\n"
            )

    data_context = "\n".join(report_lines)
    
    prompt = f"""Dưới đây là thống kê tương tác thực tế từ Fanpage Lucas Combo (chuyên phụ kiện Apple) cho hai loại bài: Infographic tin đồn/thảo luận, và bài sản phẩm (ảnh sản phẩm + giá).
Điểm tương tác (Score) = Reactions * 1 + Comments * 3 + Shares * 5.
LƯU Ý: Comments ở đây ĐÃ TRỪ bình luận do chính Page tự đăng, nên đây là
bình luận thật của người xem. Comments = 0 nghĩa là không ai bình luận.

DỮ LIỆU TƯƠNG TÁC:
{data_context}

Nhiệm vụ của bạn:
Phân tích dữ liệu trên và đúc kết thành bộ hướng dẫn cụ thể (style guide tối ưu tương tác) cho các bài viết tiếp theo.
Yêu cầu bộ hướng dẫn:
1. Nêu rõ những chủ đề hoặc góc tiếp cận nào có điểm tương tác cao nhất.
2. Nêu rõ những cấu trúc tiêu đề (headline) hoặc câu hook nào kích thích bình luận, chia sẻ nhiều nhất.
3. Chỉ ra những gì đang kém hiệu quả (nội dung/style) cần tránh hoặc thay đổi.
3b. Nếu có dữ liệu cả hai loại bài, nêu rõ khác biệt giữa chúng thay vì gộp chung.
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

        # Lưu vết để sau còn truy được: bài học nào rút ra lúc nào, từ bao nhiêu
        # bài, điểm trung vị khi đó bao nhiêu. learnings.txt bị ghi đè mỗi lượt
        # nên nếu không lưu thì không bao giờ biết vòng học có tiến bộ hay không.
        try:
            scores = sorted(r["performance"]["score"] for r in valid_rumors)
            median = scores[len(scores) // 2] if scores else 0
            record = {
                "time": datetime.now().isoformat(timespec="seconds"),
                "n_rumors": len(valid_rumors),
                "n_products": len(valid_products),
                "median_score": median,
                "max_score": max(scores) if scores else 0,
                "learnings": learnings,
            }
            with open("learnings_history.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"Đã ghi learnings_history.jsonl (n={len(valid_rumors)}, trung vị={median}).")
        except Exception as e:
            print(f"Không ghi được lịch sử bài học: {e}")
    except Exception as e:
        print(f"Lỗi khi gọi Claude AI: {e}")

if __name__ == "__main__":
    main()
