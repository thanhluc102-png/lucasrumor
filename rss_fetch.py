import feedparser
import json
import re
from pathlib import Path
from difflib import SequenceMatcher

RSS_FEEDS = {
    "MacRumors":    "https://feeds.macrumors.com/MacRumors-All",
    "9to5Mac":      "https://9to5mac.com/feed/",
    "The Verge":    "https://www.theverge.com/rss/index.xml",
    "AppleInsider": "https://appleinsider.com/rss/news/",
    "Cult of Mac":  "https://www.cultofmac.com/feed/",
    "MacWorld":     "https://www.macworld.com/feed",
    "MacStories":   "https://www.macstories.net/feed/",
}

KEYWORDS = ["macbook", "iphone", "apple", "mac", "ipad", "ios", "macos"]
DEAL_KEYWORDS = ["save $", "save up to", " off on ", "deal:", "% off", "drops to $",
                 "for just $", "for only $", "price drop", "on sale", "grab ", "coupon",
                 "refurbished", "best place to buy", "skip apple's pricey"]
SEEN_FILE = Path("seen_articles.json")


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)))


def is_similar(a: str, b: str, threshold=0.6) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def fetch_articles(limit_per_source=5):
    seen_links = load_seen()
    articles = []

    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        count = 0
        for entry in feed.entries:
            if count >= limit_per_source:
                break
            link = entry.get("link", "")
            title = entry.get("title", "")
            if link in seen_links:
                continue
            summary = entry.get("summary", entry.get("description", ""))
            combined_lower = (title + " " + summary).lower()
            if not any(kw in combined_lower for kw in KEYWORDS):
                continue
            if any(kw in combined_lower for kw in DEAL_KEYWORDS):
                continue
            if any(is_similar(title, a["title"]) for a in articles):
                continue
            articles.append({
                "source": source,
                "title": title,
                "summary": summary[:1000],
                "link": link,
            })
            count += 1

    return articles, seen_links


def pick_and_build(client, articles: list[dict]) -> dict:
    articles_text = "\n\n".join(
        f"[{i+1}] {a['source']} — {a['title']}\n{a['summary'][:400]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Bạn là biên tập viên công nghệ người Việt kiêm nhà thiết kế infographic.

Dưới đây là các tin Apple mới nhất:

{articles_text}

Chọn 1 tin nổi bật nhất rồi trả về JSON để render infographic (chỉ JSON, không markdown):

{{
  "selected_index": số thứ tự bài (1-based),
  "category": "iPhone | MacBook | Apple AI | Tin nóng | Deal | Sự kiện",
  "category_icon": "emoji phù hợp với category",
  "title": "tiêu đề tiếng Việt mạnh, tối đa 10 từ",
  "summary": "2-3 câu tóm tắt tự nhiên",

  "visual_type": "comparison | stat | announcement | deal | timeline",
  // Chọn loại visual phù hợp nhất với nội dung:
  // - comparison: khi tin so sánh 2 thứ (đời cũ vs mới, trước vs sau)
  // - stat: khi tin xoay quanh 1-2 con số nổi bật (RAM, giá, %)
  // - announcement: khi tin là thông báo ra mắt / sự kiện
  // - deal: khi tin về giá khuyến mãi, sale
  // - timeline: khi tin về lịch trình, ngày tháng

  "visual_data": {{
    // Nếu visual_type = "comparison":
    // "left":  {{"label": "cái cũ/đối thủ", "value": số, "unit": "đơn vị"}},
    // "right": {{"label": "cái mới/Apple", "value": số, "unit": "đơn vị"}},
    // "max":   số lớn nhất để tính tỉ lệ bar,
    // "metric": "tên chỉ số đang so sánh"

    // Nếu visual_type = "stat":
    // "main": {{"value": "con số to nhất", "unit": "đơn vị nếu có", "label": "giải thích"}},
    // "sub":  [{{"value": "...", "label": "..."}}]  // tối đa 2 stat phụ

    // Nếu visual_type = "announcement":
    // "product": "tên sản phẩm",
    // "tagline": "1 câu mô tả ngắn, ấn tượng",
    // "date": "ngày/quý ra mắt nếu biết, hoặc null"

    // Nếu visual_type = "deal":
    // "product": "tên sản phẩm",
    // "original_price": "giá gốc có đơn vị",
    // "sale_price": "giá sale có đơn vị",
    // "discount": "% hoặc số tiền giảm"

    // Nếu visual_type = "timeline":
    // "events": [{{"date": "...", "label": "..."}}]  // tối đa 3 mốc
  }},

  "bullets": ["điểm 1", "điểm 2", "điểm 3"],
  "sources": ["nguồn 1"]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    match = re.search(r"\{[\s\S]+?\n\}", raw)
    if not match:
        match = re.search(r"\{[\s\S]+\}", raw)
    data = json.loads(match.group() if match else raw)

    idx = max(0, min(data.pop("selected_index", 1) - 1, len(articles) - 1))
    data["article_link"] = articles[idx]["link"]
    return data


def run(client, limit_per_source=5):
    articles, seen_links = fetch_articles(limit_per_source)
    if not articles:
        return None, seen_links

    infographic_data = pick_and_build(client, articles)
    new_links = {a["link"] for a in articles}

    return infographic_data, seen_links | new_links
