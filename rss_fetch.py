import feedparser
import json
import re
import requests
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

# Subreddit theo dõi — xếp theo engagement thực tế (đã khảo sát)
REDDIT_SUBS = ["mac", "iphone", "AppleWatch", "apple", "MacOS", "macapps", "airpods", "VisionPro"]

# Bỏ qua thread hỏi đáp / megathread
REDDIT_SKIP = ["weekly", "daily", "megathread", "what should i buy",
               "advice thread", "order/shipping", "discussion thread",
               "buying advice", "mod post", "pinned"]

# Chỉ lấy bài có engagement đủ lớn
MIN_SCORE    = 80   # upvotes tối thiểu
KEYWORDS = ["macbook", "iphone", "apple", "mac", "ipad", "ios", "macos"]
DEAL_KEYWORDS = ["save $", "save up to", " off on ", "deal:", "% off", "drops to $",
                 "for just $", "for only $", "price drop", "on sale", "grab ", "coupon",
                 "refurbished", "best place to buy", "skip apple's pricey",
                 "costco", " sale "]
SEEN_FILE  = Path("seen_articles.json")
REDDIT_UA  = "AppleNewsBot/1.0 (by /u/lucasrumor)"
MIN_SCORE  = 80  # upvotes tối thiểu cho Reddit link post


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)))


def is_similar(a: str, b: str, threshold=0.6) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def _add_entries(feed_entries, source, seen_links, articles, limit):
    count = 0
    for entry in feed_entries:
        if count >= limit:
            break
        link  = entry.get("link", "")
        title = entry.get("title", "")
        if link in seen_links:
            continue
        summary  = entry.get("summary", entry.get("description", ""))
        combined = (title + " " + summary).lower()
        if any(kw in combined for kw in DEAL_KEYWORDS):
            continue
        if not any(kw in combined for kw in KEYWORDS):
            continue
        if any(is_similar(title, a["title"]) for a in articles):
            continue
        articles.append({"source": source, "title": title,
                          "summary": summary[:1000], "link": link})
        count += 1


def fetch_articles(limit_per_source=5):
    seen_links = load_seen()
    articles = []

    # nguồn báo thông thường
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        _add_entries(feed.entries, source, seen_links, articles, limit_per_source)

    # Reddit — lấy câu chuyện cộng đồng: image post + self post nhiều comment
    reddit_pool = []
    for sub in REDDIT_SUBS:
        try:
            url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit=25"
            r = requests.get(url, headers={"User-Agent": REDDIT_UA}, timeout=8)
            posts = r.json()["data"]["children"]
            for post in posts:
                p        = post["data"]
                title    = p.get("title", "")
                score    = p.get("score", 0)
                comments = p.get("num_comments", 0)
                link     = f"https://www.reddit.com{p.get('permalink', '')}"
                hint     = p.get("post_hint", "")
                selftext = p.get("selftext", "")

                # lọc cơ bản
                if score < MIN_SCORE or comments < 20:
                    continue
                if any(skip in title.lower() for skip in REDDIT_SKIP):
                    continue
                if any(kw in title.lower() for kw in DEAL_KEYWORDS):
                    continue
                if link in seen_links:
                    continue
                # chỉ lấy image post, gallery, hoặc self post — bỏ link bài báo ngoài
                is_self = p.get("is_self", False)
                if hint == "link" and not is_self:
                    continue

                # lấy ảnh đính kèm nếu có
                image_url = None
                if hint == "image":
                    image_url = p.get("url", "")
                elif p.get("gallery_data"):
                    # gallery — lấy ảnh đầu tiên
                    media = p.get("media_metadata", {})
                    first_id = p["gallery_data"]["items"][0]["media_id"]
                    img_data = media.get(first_id, {})
                    if img_data.get("s"):
                        image_url = img_data["s"].get("u", "").replace("&amp;", "&")

                reddit_pool.append({
                    "source":    f"r/{sub}",
                    "title":     title,
                    "summary":   selftext[:600] if selftext else title,
                    "link":      link,
                    "image_url": image_url,
                    "score":     score,
                    "comments":  comments,
                    # sort ưu tiên comment vì = đang được bàn luận nhiều
                    "rank":      comments * 3 + score,
                })
        except Exception as e:
            print(f"Reddit r/{sub} lỗi: {e}")

    reddit_pool.sort(key=lambda x: x["rank"], reverse=True)
    seen_subs: dict[str, int] = {}
    for post in reddit_pool:
        sub = post["source"]
        if seen_subs.get(sub, 0) >= 2:
            continue
        if any(is_similar(post["title"], a["title"]) for a in articles):
            continue
        articles.append({k: v for k, v in post.items() if k not in ("score","rank")})
        seen_subs[sub] = seen_subs.get(sub, 0) + 1

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

  "visual_type": "comparison | stat | announcement | deal | timeline | community",
  // Chọn loại visual phù hợp nhất với nội dung:
  // - comparison: khi tin so sánh 2 thứ (đời cũ vs mới, trước vs sau)
  // - stat: khi tin xoay quanh 1-2 con số nổi bật (RAM, giá, %)
  // - announcement: khi tin là thông báo ra mắt / sự kiện
  // - deal: khi tin về giá khuyến mãi, sale
  // - timeline: khi tin về lịch trình, ngày tháng
  // - community: BẮT BUỘC dùng khi nguồn bắt đầu bằng "r/" (bài từ Reddit)

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

    // Nếu visual_type = "community":
    // "subreddit": "tên subreddit",
    // "upvotes": số upvotes,
    // "comments": số comments,
    // "translated_post": "dịch toàn bộ nội dung bài đăng sang tiếng Việt tự nhiên, 2-4 câu, giữ nguyên giọng của người dùng"
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


def _pick_best(client, pool: list[dict], n: int, context: str = "") -> list[int]:
    """Dùng Claude chọn n bài tốt nhất từ pool, trả về list index (0-based) trong pool."""
    articles_text = "\n\n".join(
        f"[{i+1}] {a['source']} — {a['title']}\n{a['summary'][:300]}"
        for i, a in enumerate(pool)
    )
    prompt = f"""Bạn là biên tập viên công nghệ người Việt.{(' ' + context) if context else ''}

Dưới đây là các bài:

{articles_text}

Chọn {n} bài nổi bật nhất, đa dạng chủ đề (không trùng nhau). Trả về JSON (chỉ JSON, không markdown):

[{", ".join(['{{"selected_index": số thứ tự (1-based)}}'] * n)}]"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    match = re.search(r"\[[\s\S]+\]", raw)
    picks = json.loads(match.group() if match else raw)
    return [max(0, min(p["selected_index"] - 1, len(pool) - 1)) for p in picks[:n]]


def pick_top3(client, articles: list[dict]) -> dict:
    """Trả về {"news": [...], "reddit": [...]} — 3 tin báo + 3 bài Reddit."""
    news   = [a for a in articles if not a["source"].startswith("r/")]
    reddit = [a for a in articles if a["source"].startswith("r/")]

    def build_results(pool, n, context=""):
        if not pool:
            return []
        idxs = _pick_best(client, pool, min(n, len(pool)), context)
        results = []
        for i in idxs:
            art  = pool[i]
            data = pick_and_build(client, [art])
            data["article_link"] = art["link"]
            if art.get("image_url"):
                data["image_url"] = art["image_url"]
            results.append(data)
        return results

    news_results   = build_results(news, 3, "Chọn 3 tin tức Apple nổi bật nhất, đa dạng chủ đề.")
    reddit_results = build_results(reddit, 3, "Chọn 3 bài cộng đồng thú vị nhất, ưu tiên bài có hình ảnh và nhiều bình luận.")

    return {"news": news_results, "reddit": reddit_results}


def pick_digest(client, articles: list[dict]) -> dict:
    """Chọn top 4 tin và tổng hợp thành digest."""
    articles_text = "\n\n".join(
        f"[{i+1}] {a['source']} — {a['title']}\n{a['summary'][:300]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Bạn là biên tập viên công nghệ người Việt.

Dưới đây là các tin Apple mới nhất:

{articles_text}

Chọn 4 tin đa dạng, nổi bật nhất (không trùng chủ đề) rồi trả về JSON (chỉ JSON, không markdown):

{{
  "intro": "1 câu mở đầu ngắn, tổng quan tin hôm nay, giọng thân thiện",
  "stories": [
    {{
      "selected_index": số thứ tự bài (1-based),
      "category": "iPhone | MacBook | Apple AI | Sự kiện | Tin nóng",
      "category_icon": "emoji",
      "title": "tiêu đề tiếng Việt súc tích, tối đa 10 từ",
      "bullets": ["điểm nổi bật 1", "điểm nổi bật 2"]
    }}
  ]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    match = re.search(r"\{[\s\S]+\}", raw)
    data = json.loads(match.group() if match else raw)

    # gán link cho từng story
    for story in data["stories"]:
        idx = max(0, min(story.pop("selected_index", 1) - 1, len(articles) - 1))
        story["article_link"] = articles[idx]["link"]
        story["source"] = articles[idx]["source"]

    return data


def run(client, limit_per_source=5, mode="top3"):
    articles, seen_links = fetch_articles(limit_per_source)
    if not articles:
        return None, seen_links

    if mode == "top3":
        data = pick_top3(client, articles)
    elif mode == "digest":
        data = pick_digest(client, articles)
    else:
        data = pick_and_build(client, articles)

    new_links = {a["link"] for a in articles}
    return data, seen_links | new_links
