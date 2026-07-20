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
REDDIT_SUBS = ["apple", "mac", "iphone", "ipad", "ios", "MacOS"]

# Bỏ qua thread hỏi đáp / megathread
REDDIT_SKIP = ["weekly", "daily", "megathread", "what should i buy",
               "advice thread", "order/shipping", "discussion thread",
               "buying advice", "mod post", "pinned"]

# Chỉ lấy bài có engagement đủ lớn
MIN_SCORE    = 80   # upvotes tối thiểu
KEYWORDS = ["iphone", "macbook", "ipad", "ios", "macos", "ipados"]
DEAL_KEYWORDS = [
    "save $", "save up to", " off on ", "deal:", "% off", "drops to $",
    "for just $", "for only $", "price drop", "on sale", "grab ", "coupon",
    "refurbished", "best place to buy", "skip apple's pricey", "costco", " sale ",
    "giveaway", "promo", "sponsored", "advertisement", "discount", "deal", "deals",
    "unboxing", "review", "hands-on", "hands on", "first look", "best deals",
    "buy now", "shop", "gift card", "gift cards", "sweepstakes", "free shipping",
    "pre-order", "preorder"
]
SEEN_FILE  = Path("seen_articles.json")
REDDIT_UA  = "AppleNewsBot/1.0 (by /u/lucasrumor)"
MIN_SCORE  = 80  # upvotes tối thiểu cho Reddit link post


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)))


def check_has_image(article: dict) -> bool:
    if article.get("image_url"):
        return True
    if article["source"].startswith("r/"):
        return False
    # Check og:image for RSS links
    try:
        from bs4 import BeautifulSoup
        r = requests.get(article["link"], headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        return bool(soup.find("meta", property="og:image"))
    except:
        return False


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


_REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.reddit.com/",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}


def _fetch_reddit_posts(sub: str) -> list[dict]:
    """Try JSON API with browser headers, fall back to RSS if blocked."""
    for base in ("https://www.reddit.com", "https://old.reddit.com"):
        try:
            url = f"{base}/r/{sub}/top.json?t=day&limit=25"
            r = requests.get(url, headers=_REDDIT_HEADERS, timeout=10)
            if r.status_code == 200 and r.text.strip().startswith("{"):
                posts = r.json()["data"]["children"]
                print(f"Reddit r/{sub}: {len(posts)} bài (JSON từ {base.split('//')[1]})")
                return [p["data"] for p in posts]
        except Exception as e:
            print(f"Reddit r/{sub} JSON lỗi ({base}): {e}")

    # Fallback: fetch RSS thủ công với browser headers rồi parse
    try:
        import io
        rss_url = f"https://www.reddit.com/r/{sub}/top.rss?t=day&limit=25"
        r = requests.get(rss_url, headers=_REDDIT_HEADERS, timeout=12)
        feed = feedparser.parse(io.BytesIO(r.content))
        posts = []
        for entry in feed.entries[:25]:
            full_link = entry.get("link", "")
            title = entry.get("title", "")
            # Lấy thumbnail từ <media:thumbnail> trong RSS
            thumbs = entry.get("media_thumbnail") or entry.get("media_content") or []
            image_url = thumbs[0].get("url", "") if thumbs else None
            # Chỉ giữ ảnh thật từ preview.redd.it hoặc external-preview.redd.it
            if image_url and "redd.it" not in image_url:
                image_url = None
            hint = "image" if image_url else ""
            posts.append({
                "title":        title,
                "permalink":    "",
                "_rss_link":    full_link,
                "score":        MIN_SCORE,
                "num_comments": 25,
                "is_self":      not image_url,
                "post_hint":    hint,
                "url":          image_url or "",
                "selftext":     entry.get("summary", ""),
            })
        print(f"Reddit r/{sub}: {len(posts)} bài (RSS fallback)")
        return posts
    except Exception as e:
        print(f"Reddit r/{sub} RSS lỗi: {e}")
        return []


def fetch_articles(limit_per_source=5):
    seen_links = load_seen()
    articles = []

    # Lấy tin từ nguồn báo chí
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            _add_entries(feed.entries, source, seen_links, articles, limit_per_source)
        except Exception as e:
            print(f"Lỗi lấy RSS {url}: {e}")

    # Reddit — lấy câu chuyện cộng đồng: image post + self post nhiều comment
    reddit_pool = []
    for sub in REDDIT_SUBS:
        posts = _fetch_reddit_posts(sub)
        for p in posts:
            title    = p.get("title", "")
            score    = p.get("score", 0)
            comments = p.get("num_comments", 0)
            permalink = p.get("permalink", "")
            link = p.get("_rss_link") or f"https://www.reddit.com{permalink}"
            hint     = p.get("post_hint", "")
            selftext = p.get("selftext", "")

            if score < MIN_SCORE or comments < 20:
                continue
            if any(skip in title.lower() for skip in REDDIT_SKIP):
                continue
            if any(kw in title.lower() for kw in DEAL_KEYWORDS):
                continue
            if not any(kw in (title + " " + selftext).lower() for kw in KEYWORDS):
                continue
            if link in seen_links:
                continue
            is_self = p.get("is_self", False)
            if hint == "link" and not is_self:
                continue

            image_url = None
            if hint == "image":
                image_url = p.get("url", "")
            elif p.get("gallery_data"):
                media = p.get("media_metadata", {})
                first_id = p["gallery_data"]["items"][0]["media_id"]
                img_data = media.get(first_id, {})
                if img_data.get("s"):
                    image_url = img_data["s"].get("u", "").replace("&amp;", "&")

            if not image_url:
                continue

            reddit_pool.append({
                "source":    f"r/{sub}",
                "title":     title,
                "summary":   selftext[:600] if selftext else title,
                "link":      link,
                "image_url": image_url,
                "score":     score,
                "comments":  comments,
                "rank":      comments * 3 + score,
            })

    reddit_pool.sort(key=lambda x: x["rank"], reverse=True)
    seen_subs: dict[str, int] = {}
    for post in reddit_pool:
        sub = post["source"]
        if seen_subs.get(sub, 0) >= 2:
            continue
        if any(is_similar(post["title"], a["title"]) for a in articles):
            continue
        articles.append({k: v for k, v in post.items() if k != "rank"})
        seen_subs[sub] = seen_subs.get(sub, 0) + 1

    return articles, seen_links


def pick_and_build(client, articles: list[dict]) -> dict:
    articles_text = "\n\n".join(
        f"[{i+1}] {a['source']} — {a['title']}\n{a['summary'][:400]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Bạn là biên tập viên công nghệ người Việt kiêm nhà thiết kế infographic.
Tuyệt đối KHÔNG sử dụng các từ "News", "Tin tức" trong tiêu đề, tóm tắt hay bất kỳ đâu trong nội dung sinh ra. Thay vào đó hãy ưu tiên dùng các từ như "Tin đồn", "Thảo luận", "Cộng đồng", "Leak".

Dưới đây là các tin Apple mới nhất:

{articles_text}

Chọn 1 tin nổi bật nhất rồi trả về JSON để render infographic (chỉ JSON, không markdown):

{{
  "selected_index": số thứ tự bài (1-based),
  "category": "iPhone | MacBook | Apple AI | Tin nóng | Deal | Sự kiện",
  "category_icon": "emoji phù hợp với category",
  "title": "tiêu đề tiếng Việt mạnh, tối đa 10 từ",
  "summary": "Tóm tắt cực kỳ ngắn gọn, TỐI ĐA 25 TỪ, đi thẳng vào trọng tâm",
  "full_translated_content": "Viết lại toàn bộ nội dung chi tiết của bản tin sang tiếng Việt một cách mượt mà, đầy đủ thông tin nhất có thể (dựa trên dữ liệu gốc được cung cấp). Trình bày rõ ràng, thân thiện, dễ đọc, độ dài từ 3-6 câu.",

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
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    match = re.search(r"\{[\s\S]+?\n\}", raw)
    if not match:
        match = re.search(r"\{[\s\S]+\}", raw)
    data = json.loads(match.group() if match else raw)

    idx = max(0, min(data.pop("selected_index", 1) - 1, len(articles) - 1))
    data["article_link"] = articles[idx]["link"]
    data["source"] = articles[idx]["source"]
    # Bắt buộc điền đúng visual_type cho r/
    if data["source"].startswith("r/") and data.get("visual_type") != "community":
        data["visual_type"] = "community"
        if "visual_data" not in data:
            data["visual_data"] = {}
        data["visual_data"]["subreddit"] = data["source"].replace("r/", "")
        data["visual_data"]["upvotes"] = articles[idx].get("score", 0)
        data["visual_data"]["comments"] = articles[idx].get("comments", 0)

    if articles[idx].get("image_url"):
        data["image_url"] = articles[idx]["image_url"]
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
    # Claude đôi khi trả dict thay vì list khi n=1
    if isinstance(picks, dict):
        picks = [picks]
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
            # Patch số liệu thật cho community post (Claude có thể điền sai/None)
            if art["source"].startswith("r/") and data.get("visual_type") == "community":
                vd = data.setdefault("visual_data", {})
                vd["upvotes"]  = art.get("score", 0)
                vd["comments"] = art.get("comments", 0)
                vd.setdefault("subreddit", art["source"].replace("r/", ""))
            results.append(data)
        return results

    news_results = build_results(news, 3, "Chọn 3 tin tức Apple nổi bật nhất, đa dạng chủ đề.")

    # Lọc reddit pool: bỏ bài trùng chủ đề với news đã chọn
    chosen_news_titles = [d["title"] for d in news_results]
    reddit_filtered = [
        a for a in reddit
        if not any(is_similar(a["title"], t) for t in chosen_news_titles)
    ]
    reddit_results = build_results(reddit_filtered, 3, "Chọn 3 bài cộng đồng thú vị nhất, ưu tiên bài có hình ảnh và nhiều bình luận.")

    return {"news": news_results, "reddit": reddit_results}


def pick_digest(client, articles: list[dict]) -> dict:
    """Chọn top 4 tin và tổng hợp thành digest."""
    articles_text = "\n\n".join(
        f"[{i+1}] {a['source']} — {a['title']}\n{a['summary'][:300]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Bạn là biên tập viên công nghệ người Việt.
Tuyệt đối KHÔNG sử dụng các từ "News", "Tin tức" trong kết quả. Thay bằng "Tin đồn", "Góc cộng đồng".

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
    if mode == "single":
        import random
        news = [a for a in articles if not a["source"].startswith("r/")]
        reddit = [a for a in articles if a["source"].startswith("r/")]
        if news and reddit:
            chosen_pool = reddit if random.random() < 0.5 else news
        elif reddit:
            chosen_pool = reddit
        else:
            chosen_pool = news
        data = pick_and_build(client, chosen_pool)
        chosen_link = data.get("article_link")
        new_links = {chosen_link} if chosen_link else set()
        return data, seen_links | new_links

    elif mode == "single_sub":
        import datetime
        hour = datetime.datetime.utcnow().hour
        
        # Xen kẽ 1 Reddit, 1 Báo:
        # Chạy mỗi 4 tiếng: chẵn (0-3h, 8-11h...) -> Reddit, lẻ (4-7h, 12-15h...) -> Báo
        is_reddit_turn = (hour // 4) % 2 == 0
        
        # Chỉ mục xoay vòng (mỗi 4 tiếng tăng 1)
        cycle_idx = hour // 4
        
        if is_reddit_turn:
            primary_list = REDDIT_SUBS
            secondary_list = list(RSS_FEEDS.keys())
        else:
            primary_list = list(RSS_FEEDS.keys())
            secondary_list = REDDIT_SUBS
            
        start_idx = cycle_idx % len(primary_list)
        ordered_sources = primary_list[start_idx:] + primary_list[:start_idx] + secondary_list
        
        # Thử lần lượt các nguồn ưu tiên
        for target_source in ordered_sources:
            source_key = f"r/{target_source}" if target_source in REDDIT_SUBS else target_source
            
            # Lọc ra các bài của target_source từ danh sách articles
            sub_articles = [a for a in articles if a["source"] == source_key]
            
            for top_post in sub_articles:
                if not check_has_image(top_post):
                    continue
                try:
                    data = pick_and_build(client, [top_post])
                    data["article_link"] = top_post["link"]
                    if top_post.get("image_url"):
                        data["image_url"] = top_post["image_url"]
                    return data, seen_links | {top_post["link"]}
                except Exception as e:
                    print(f"Lỗi AI cho {target_source}: {e}")
                    # Nếu AI lỗi thì thử post tiếp theo của sub_articles
                    
        return None, seen_links

    else:
        data = pick_and_build(client, articles)
        new_links = {a["link"] for a in articles if not a.get("source", "").startswith("r/")}
        return data, seen_links | new_links
