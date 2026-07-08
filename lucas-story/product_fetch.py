import requests
import json
from bs4 import BeautifulSoup
import random

def get_products():
    url = "https://lucas.vn/wp-json/wc/store/products?per_page=20"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def pick_product():
    products = get_products()
    valid_products = [
        p for p in products 
        if p.get("is_in_stock") and p.get("images") and len(p["images"]) > 0
    ]
    if not valid_products:
        return None
    
    p = random.choice(valid_products)
    
    desc_html = p.get("short_description", "")
    desc = BeautifulSoup(desc_html, "html.parser").get_text(separator=' ', strip=True) if desc_html else ""
    
    prices = p.get("prices", {})
    price = int(prices.get("price", "0") or "0")
    regular_price = int(prices.get("regular_price", "0") or "0")
    
    price_str = f"{price:,}".replace(",", ".") + "đ"
    regular_price_str = f"{regular_price:,}".replace(",", ".") + "đ" if regular_price > price else None

    return {
        "title": p.get("name", ""),
        "link": p.get("permalink", ""),
        "image_url": p["images"][0].get("src", ""),
        "description": desc[:150] + "..." if len(desc) > 150 else desc,
        "price": price_str,
        "regular_price": regular_price_str
    }

if __name__ == "__main__":
    print(json.dumps(pick_product(), indent=2, ensure_ascii=False))
