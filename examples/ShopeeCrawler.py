"""
Shopee Product Crawler - Powered by VibeLens
Crawl sản phẩm từ Shopee API và xuất ra file CSV.
Sử dụng httpx với headers trích xuất từ VibeLens capture.
"""
import httpx
import csv
import json
import time
import urllib.parse
from datetime import datetime


class ShopeeCrawler:
    """Crawl sản phẩm Shopee dựa trên API search_items đã được VibeLens phân tích."""

    def __init__(self):
        self.base_url = "https://shopee.vn/api/v4/search/search_items"

        # Headers trích xuất từ VibeLens capture
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": "https://shopee.vn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "X-API-SOURCE": "pc",
            "X-Shopee-Language": "vi",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            # Anti-bot header trích xuất từ VibeLens
            "af-ac-enc-dat": "YWNzCgBLABRiZjEuOC4xLTIuMC4xMS1kZWIAbwAxSXlyYlF3RmpRZFRkOU1tcllhOXVidFhsaFF6V2MybEtFQWYrd2xVdEtiUjU0YkVLYW90SUhkSHRhUWVPTW0yZHVXUXRqNnVFRT0=",
            "af-ac-enc-sz-token": "VSwMCCA4VuOEETtapYxc3g==|fRlt2IHCepbuOOHdQmBnNyZYTovOj52p6Y+pI4xvSxhLErVKy1nD27ycWgCSTkAujqJXLVgudBo=|lSR/l2dt4D2hfEhM|08|3",
        }

        # Cookies trích xuất từ Set-Cookie trong VibeLens capture
        self.cookies = {
            "SPC_R_T_ID": "h+hjaxK50V2uZV3SE67QxjpXsZaNxouEYl8nZpC+u0WqIKRttfyM875oY5dN26sLVHkWPcIsXRy0Uou85YqPDCSKOyPVbY7P620BMxTQUzV0QQ48Ofz6YVa2izjD5TBk0aXOklEab/uV517SqWtfrqnkyZb7tOlxQ15orJG52H0=",
        }

        self.client = httpx.Client(
            headers=self.headers,
            cookies=self.cookies,
            follow_redirects=True,
            timeout=30.0,
        )

    def search_products(self, keyword: str, page: int = 0, limit: int = 60,
                        sort_by: str = "relevancy", order: str = "desc") -> dict | None:
        """Gọi API search_items của Shopee."""
        params = {
            "by": sort_by,
            "keyword": keyword,
            "limit": str(limit),
            "newest": str(page * limit),
            "order": order,
            "page_type": "search",
            "scenario": "PAGE_GLOBAL_SEARCH",
            "source": "SRP",
            "version": "2",
        }
        
        print(f"  ➡️  GET search_items?keyword={keyword}&page={page}")
        try:
            res = self.client.get(self.base_url, params=params)
            print(f"  📡 Status: {res.status_code} | Size: {len(res.content)} bytes")
            
            if res.status_code == 200:
                text = res.text.strip()
                if not text:
                    print("  ⚠️  Response body rỗng (bị Shopee anti-bot chặn)")
                    return None
                try:
                    return res.json()
                except json.JSONDecodeError as e:
                    print(f"  ❌ JSON decode error: {e}")
                    print(f"  📝 Raw (first 300 chars): {text[:300]}")
                    return None
            else:
                print(f"  ❌ HTTP {res.status_code}")
                return None
        except httpx.RequestError as e:
            print(f"  ❌ Request error: {e}")
            return None

    @staticmethod
    def parse_item(item: dict) -> dict:
        """Trích xuất thông tin quan trọng từ 1 item."""
        info = item.get("item_basic", item)
        price_raw = info.get("price", 0) or 0
        price_min = info.get("price_min", price_raw) or 0
        price_max = info.get("price_max", price_raw) or 0

        # Rating có thể nằm trong item_rating hoặc trực tiếp
        rating = 0
        if isinstance(info.get("item_rating"), dict):
            rating = info["item_rating"].get("rating_star", 0)
        elif "rating_star" in info:
            rating = info["rating_star"]

        return {
            "item_id": info.get("itemid"),
            "shop_id": info.get("shopid"),
            "name": info.get("name", "N/A"),
            "price": price_raw / 100_000 if price_raw else 0,
            "price_min": price_min / 100_000 if price_min else 0,
            "price_max": price_max / 100_000 if price_max else 0,
            "currency": info.get("currency", "VND"),
            "sold": info.get("sold", 0),
            "historical_sold": info.get("historical_sold", 0),
            "stock": info.get("stock", 0),
            "rating": round(rating, 2) if rating else 0,
            "liked": info.get("liked_count", 0),
            "discount": info.get("show_discount", 0),
            "shop_location": info.get("shop_location", ""),
            "is_official": info.get("is_official_shop", False),
            "image": f"https://down-vn.img.susercontent.com/file/{info.get('image', '')}" if info.get("image") else "",
            "url": f"https://shopee.vn/product/{info.get('shopid')}/{info.get('itemid')}",
        }

    def crawl(self, keyword: str, max_pages: int = 3, delay: float = 2.0) -> list[dict]:
        """Crawl nhiều trang và trả về danh sách sản phẩm đã parse."""
        all_products = []
        print(f"\n🚀 Bắt đầu crawl Shopee: \"{keyword}\" (tối đa {max_pages} trang)\n")

        for page in range(max_pages):
            data = self.search_products(keyword, page=page)
            if not data:
                print("  ⛔ Dừng crawl do không có dữ liệu.\n")
                break

            items = data.get("items", [])
            if not items:
                print("  ⛔ Không còn sản phẩm.\n")
                break

            for raw in items:
                parsed = self.parse_item(raw)
                all_products.append(parsed)

            print(f"  ✅ Trang {page}: lấy được {len(items)} sản phẩm (tổng: {len(all_products)})")

            if data.get("nomore", False):
                print("  📥 Đã hết trang.\n")
                break

            if page < max_pages - 1:
                time.sleep(delay)

        print(f"\n📊 Tổng cộng: {len(all_products)} sản phẩm\n")
        return all_products

    @staticmethod
    def to_csv(products: list[dict], filename: str = "shopee_products.csv"):
        """Xuất danh sách sản phẩm ra file CSV."""
        if not products:
            print("❌ Không có dữ liệu để xuất CSV.")
            return

        fieldnames = [
            "item_id", "shop_id", "name", "price", "price_min", "price_max",
            "currency", "sold", "historical_sold", "stock", "rating", "liked",
            "discount", "shop_location", "is_official", "image", "url"
        ]

        with open(filename, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(products)

        print(f"💾 Đã lưu {len(products)} sản phẩm vào {filename}")

    def close(self):
        self.client.close()


# ─── MAIN ────────────────────────────────────────────────
if __name__ == "__main__":
    crawler = ShopeeCrawler()

    try:
        # Crawl sản phẩm "iphone 17", tối đa 3 trang, delay 2 giây
        products = crawler.crawl(keyword="iphone 17", max_pages=3, delay=2.0)

        # Xuất CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = f"shopee_iphone17_{timestamp}.csv"
        crawler.to_csv(products, filename=csv_file)

        # Preview 5 sản phẩm đầu tiên
        if products:
            print("\n── Preview 5 sản phẩm đầu ──")
            for i, p in enumerate(products[:5], 1):
                print(f"  {i}. {p['name']}")
                print(f"     💰 {p['price']:,.0f} VND | 🛒 Đã bán: {p['sold']} | ⭐ {p['rating']}")
                print(f"     📍 {p['shop_location']} | 🔗 {p['url']}")
                print()
    finally:
        crawler.close()
