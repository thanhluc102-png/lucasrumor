"""
make_ad.py — Tạo ảnh quảng cáo Story (1080×1920) từ link sản phẩm lucas.vn
Usage: python make_ad.py <url>
"""
import sys, re, base64, requests
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from jinja2 import Environment, BaseLoader

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

LOGO_B64 = "data:image/png;base64," + base64.b64encode(
    (Path(__file__).parent / "logo.png").read_bytes()
).decode()


# ── SCRAPE ─────────────────────────────────────────────────────────────────

def scrape(url: str) -> dict:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")

    # Tên sản phẩm
    name = soup.find("h1")
    name = name.text.strip() if name else "Sản phẩm"

    # Giá: tìm del (gốc) và ins (sale), hoặc lấy giá đơn
    price_wrap = soup.find(class_="price")
    original = sale = ""
    if price_wrap:
        del_el = price_wrap.find("del")
        ins_el = price_wrap.find("ins")
        if del_el and ins_el:
            original = _clean_price(del_el.text)
            sale     = _clean_price(ins_el.text)
        else:
            # Một giá duy nhất — lấy tất cả rồi dùng cái đầu tiên
            amounts = price_wrap.find_all(class_="woocommerce-Price-amount")
            prices  = [_clean_price(a.text) for a in amounts if _clean_price(a.text) != "0"]
            if len(prices) >= 2:
                original, sale = prices[0], prices[1]
            elif prices:
                sale = prices[0]

    # Tính tiết kiệm
    saved = _calc_saved(original, sale)

    # Bullets từ short description (Flatsome theme dùng class khác)
    short = (soup.find(class_="product-short-description")
             or soup.find(class_="woocommerce-product-details__short-description"))
    bullets = []
    if short:
        lis = short.find_all("li")
        if lis:
            bullets = [li.text.strip() for li in lis[:4]]
        else:
            lines = [l.strip() for l in short.text.strip().splitlines() if l.strip()]
            bullets = lines[:4]

    # Ảnh chính: data-large_image > src từ gallery > og:image
    img_url = None
    gallery_imgs = soup.select(".woocommerce-product-gallery__image img")
    if gallery_imgs:
        img_url = (gallery_imgs[0].get("data-large_image")
                   or gallery_imgs[0].get("src", ""))
    if not img_url or "100x100" in img_url:
        og = soup.find("meta", property="og:image")
        img_url = og["content"] if og else ""

    # Fetch ảnh về base64
    img_b64 = _fetch_img_b64(img_url) if img_url else None

    return {
        "name":     name,
        "original": original,
        "sale":     sale,
        "saved":    saved,
        "bullets":  bullets,
        "img_b64":  img_b64,
        "url":      url,
    }


def _clean_price(text: str) -> str:
    digits = re.sub(r"[^\d]", "", text)
    if not digits or digits == "0":
        return ""
    n = int(digits)
    return f"{n:,.0f}₫".replace(",", ".")


def _calc_saved(original: str, sale: str) -> str:
    try:
        o = int(re.sub(r"[^\d]", "", original))
        s = int(re.sub(r"[^\d]", "", sale))
        diff = o - s
        if diff <= 0:
            return ""
        if diff >= 1_000_000:
            return f"Tiết kiệm {diff//1_000_000}tr"
        return f"Tiết kiệm {diff//1000}K"
    except Exception:
        return ""


def _fetch_img_b64(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=12)
        r.raise_for_status()
        mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
    except Exception:
        return None


# ── TEMPLATE ────────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
* { margin:0; padding:0; box-sizing:border-box; }

body {
  width: 540px; height: 960px; overflow: hidden;
  font-family: 'Inter', sans-serif;
  background: #0f172a;
  position: relative;
}

/* ── ẢNH SẢN PHẨM (60% trên) ── */
.product-img {
  position: absolute; top: 0; left: 0; right: 0;
  height: 580px; overflow: hidden;
}
.product-img img {
  width: 100%; height: 100%; object-fit: cover; display: block;
}
.product-img-placeholder {
  width: 100%; height: 100%;
  background: linear-gradient(135deg, #1e3a8a, #1d4ed8);
  display: flex; align-items: center; justify-content: center;
  font-size: 80px;
}

/* gradient mờ dần xuống dưới */
.img-fade {
  position: absolute; bottom: 0; left: 0; right: 0; height: 220px;
  background: linear-gradient(to bottom, transparent, #0f172a);
  pointer-events: none;
}

/* ── LOGO góc trên trái ── */
.logo-wrap {
  position: absolute; top: 24px; left: 24px;
  display: flex; align-items: center; gap: 8px; z-index: 10;
}
.logo-icon {
  width: 36px; height: 36px; border-radius: 9px;
  overflow: hidden; background: rgba(255,255,255,0.1);
  backdrop-filter: blur(8px);
}
.logo-icon img { width: 100%; height: 100%; object-fit: contain; display: block; }
.logo-name {
  font-size: 14px; font-weight: 800; color: #fff;
  text-shadow: 0 1px 8px rgba(0,0,0,0.5);
  letter-spacing: -0.3px;
}

/* ── PHẦN THÔNG TIN DƯỚI (40%) ── */
.info {
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 410px;
  padding: 20px 28px 28px;
  display: flex; flex-direction: column; gap: 0;
}

/* tên sản phẩm */
.prod-name {
  font-size: 18px; font-weight: 800; color: #fff;
  line-height: 1.3; letter-spacing: -0.3px;
  margin-bottom: 14px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}

/* bullets */
.bullets { display: flex; flex-direction: column; gap: 7px; margin-bottom: 18px; }
.bullet {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 13px; color: rgba(255,255,255,0.7); line-height: 1.4;
}
.bullet-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #60a5fa; flex-shrink: 0; margin-top: 5px;
}

/* divider */
.divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent);
  margin-bottom: 18px;
}

/* giá */
.price-row {
  display: flex; align-items: flex-end; gap: 12px; margin-bottom: 14px;
}
.price-sale {
  font-size: 44px; font-weight: 900; letter-spacing: -2px; line-height: 1;
  background: linear-gradient(135deg, #60a5fa, #a78bfa);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
.price-original {
  font-size: 16px; color: rgba(255,255,255,0.35);
  text-decoration: line-through; font-weight: 500;
  padding-bottom: 6px;
}

/* badge tiết kiệm */
.saved-badge {
  display: inline-flex; align-items: center; gap: 6px;
  background: linear-gradient(135deg, #dc2626, #ea580c);
  border-radius: 100px; padding: 8px 20px;
  font-size: 15px; font-weight: 800; color: #fff;
  letter-spacing: 0.3px; align-self: flex-start;
  box-shadow: 0 4px 16px rgba(220,38,38,0.4);
  margin-bottom: 18px;
}

/* CTA */
.cta {
  background: linear-gradient(135deg, #1d4ed8, #7c3aed);
  border-radius: 16px; padding: 16px;
  text-align: center;
  font-size: 15px; font-weight: 800; color: #fff;
  letter-spacing: 0.3px;
  box-shadow: 0 8px 24px rgba(29,78,216,0.4);
  margin-top: auto;
}
.cta span { opacity: 0.7; font-weight: 500; }
</style>
</head>
<body>

<!-- ẢNH SẢN PHẨM -->
<div class="product-img">
  {% if img_b64 %}
    <img src="{{ img_b64 }}" alt="">
  {% else %}
    <div class="product-img-placeholder">🛍️</div>
  {% endif %}
  <div class="img-fade"></div>
</div>

<!-- LOGO -->
<div class="logo-wrap">
  <div class="logo-icon"><img src="{{ logo_b64 }}" alt="Lucas"></div>
  <span class="logo-name">Lucas Combo</span>
</div>

<!-- THÔNG TIN -->
<div class="info">
  <div class="prod-name">{{ name }}</div>

  {% if bullets %}
  <div class="bullets">
    {% for b in bullets %}
    <div class="bullet">
      <div class="bullet-dot"></div>
      <span>{{ b }}</span>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="divider"></div>

  <div class="price-row">
    <div class="price-sale">{{ sale or original }}</div>
    {% if original and sale %}
    <div class="price-original">{{ original }}</div>
    {% endif %}
  </div>

  {% if saved %}
  <div class="saved-badge">🔥 {{ saved }}</div>
  {% endif %}

  <div class="cta">
    Mua ngay tại <span>lucas.vn</span>
  </div>
</div>

</body>
</html>"""


# ── RENDER ──────────────────────────────────────────────────────────────────

def render(data: dict, output: str = "ad_story.png"):
    env = Environment(loader=BaseLoader())
    html = env.from_string(TEMPLATE).render(logo_b64=LOGO_B64, **data)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 540, "height": 960},
            device_scale_factor=2,   # 2x → 1080×1920
        )
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=output)
        browser.close()

    return output


# ── MAIN ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else input("Nhập link sản phẩm: ").strip()
    print(f"Đang scrape {url}...")
    data = scrape(url)
    print(f"  Tên  : {data['name'][:60]}")
    print(f"  Sale : {data['sale']} (gốc: {data['original']})")
    print(f"  Saved: {data['saved']}")
    print(f"  Ảnh  : {'Có' if data['img_b64'] else 'Không'}")
    print(f"  Bullets: {len(data['bullets'])} dòng")
    print("Đang render...")
    out = render(data)
    print(f"✓ Xong: {out}")
