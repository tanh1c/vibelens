"""
Shopee Product Extractor - Trích xuất dữ liệu sản phẩm từ VibeLens captured traffic.
Thay vì gọi lại API (bị anti-bot chặn), script này phân tích dữ liệu
tracking events đã capture để trích xuất thông tin sản phẩm và giá.
"""
import csv
import json
import re
import httpx
from datetime import datetime


def fetch_captured_data() -> list[dict]:
    """Lấy captured requests từ VibeLens bridge server."""
    print("📡 Đang lấy dữ liệu từ VibeLens bridge server...")
    try:
        res = httpx.get("http://localhost:8000/requests", timeout=10)
        data = res.json()
        requests_list = data if isinstance(data, list) else data.get("requests", [])
        print(f"  ✅ Nhận được {len(requests_list)} requests")
        return requests_list
    except Exception as e:
        print(f"  ❌ Lỗi kết nối bridge: {e}")
        return []


def extract_products_from_tracking(requests_list: list[dict]) -> list[dict]:
    """
    Trích xuất thông tin sản phẩm từ tracking events (__t__ và event_batch).
    Shopee gửi impression events chứa đầy đủ product_card data.
    """
    products = {}  # Dùng dict theo itemid để tránh trùng lặp

    for req in requests_list:
        body = req.get("postData") or req.get("body", "")
        if not body or not isinstance(body, str):
            continue

        # Tìm tất cả product_card trong body
        # Pattern: "itemid":12345678 ... "product_card":{...}
        try:
            # Parse JSON nếu body là JSON array hoặc object
            if body.startswith("[") or body.startswith("{"):
                parsed = json.loads(body)
            else:
                continue
        except json.JSONDecodeError:
            continue

        # Duyệt qua tracking events
        events = parsed if isinstance(parsed, list) else [parsed]
        for event in events:
            if not isinstance(event, dict):
                continue

            # Tìm trong data.viewed_objects
            data_obj = event.get("data", {})
            if not isinstance(data_obj, dict):
                continue
                
            viewed = data_obj.get("viewed_objects", [])
            for obj in viewed:
                if not isinstance(obj, dict):
                    continue
                    
                item_info = obj.get("item", {})
                search_fe = obj.get("search_FE", {})
                item_fe = search_fe.get("item", {}) if isinstance(search_fe, dict) else {}

                itemid = item_info.get("itemid")
                shopid = item_info.get("shopid")
                if not itemid:
                    continue

                # Lấy product_card từ ads_info
                ads_info = event.get("ads_info", {})
                product_card = {}
                if isinstance(ads_info, dict):
                    ads_items = ads_info.get("items", [])
                    for ad in ads_items:
                        if isinstance(ad, dict) and ad.get("itemid") == itemid:
                            product_card = ad.get("product_card", {})
                            break

                # Trích xuất dữ liệu
                price = product_card.get("price", 0) or 0
                price_min = product_card.get("price_min", price) or 0
                price_max = product_card.get("price_max", price) or 0

                products[itemid] = {
                    "item_id": itemid,
                    "shop_id": shopid,
                    "price": price / 100_000 if price else 0,
                    "price_min": price_min / 100_000 if price_min else 0,
                    "price_max": price_max / 100_000 if price_max else 0,
                    "currency": "VND",
                    "sold": product_card.get("sold_count", item_info.get("sold", 0)),
                    "rating": round(product_card.get("rating_star", item_info.get("rating", 0)), 2),
                    "discount": int(item_info.get("discount_percentage", product_card.get("item_discount", 0)) or 0),
                    "likes": item_info.get("likes", 0),
                    "is_mall": item_info.get("is_mall", False),
                    "is_preferred": item_info.get("is_preferred", False),
                    "has_video": product_card.get("has_video", False),
                    "url": f"https://shopee.vn/product/{shopid}/{itemid}",
                }

    return list(products.values())


def extract_from_search_api(requests_list: list[dict]) -> list[dict]:
    """
    Trích xuất sản phẩm từ response body của search_items API (nếu captured).
    """
    products = []
    for req in requests_list:
        url = req.get("url", "")
        if "search_items" not in url:
            continue

        response_body = req.get("responseBody") or req.get("response_body", "")
        if not response_body:
            continue

        try:
            data = json.loads(response_body) if isinstance(response_body, str) else response_body
            items = data.get("items", [])
            for item in items:
                info = item.get("item_basic", item)
                price = info.get("price", 0) or 0
                products.append({
                    "item_id": info.get("itemid"),
                    "shop_id": info.get("shopid"),
                    "name": info.get("name", "N/A"),
                    "price": price / 100_000,
                    "price_min": (info.get("price_min", 0) or 0) / 100_000,
                    "price_max": (info.get("price_max", 0) or 0) / 100_000,
                    "currency": "VND",
                    "sold": info.get("sold", 0),
                    "rating": round(info.get("item_rating", {}).get("rating_star", 0), 2) if isinstance(info.get("item_rating"), dict) else 0,
                    "discount": info.get("show_discount", 0),
                    "likes": info.get("liked_count", 0),
                    "is_mall": info.get("is_official_shop", False),
                    "is_preferred": False,
                    "has_video": False,
                    "url": f"https://shopee.vn/product/{info.get('shopid')}/{info.get('itemid')}",
                })
        except (json.JSONDecodeError, TypeError):
            continue

    return products


def to_csv(products: list[dict], filename: str):
    """Xuất ra CSV."""
    if not products:
        print("❌ Không có sản phẩm để xuất.")
        return

    fieldnames = [
        "item_id", "shop_id", "price", "price_min", "price_max",
        "currency", "sold", "rating", "discount", "likes",
        "is_mall", "is_preferred", "has_video", "url"
    ]
    # Thêm "name" nếu có
    if "name" in products[0]:
        fieldnames.insert(2, "name")

    with open(filename, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)

    print(f"💾 Đã lưu {len(products)} sản phẩm vào {filename}")


# ─── MAIN ────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("🛒 Shopee Product Extractor - Powered by VibeLens")
    print("=" * 60)

    # Bước 1: Lấy captured data từ VibeLens
    captured = fetch_captured_data()

    if not captured:
        print("\n❌ Không lấy được data. Hãy đảm bảo VibeLens bridge server đang chạy.")
        exit(1)

    # Bước 2: Thử trích xuất từ search API response trước
    products = extract_from_search_api(captured)
    source = "search_items API"

    # Bước 3: Nếu không có, fallback sang tracking events
    if not products:
        print("\n📊 Không tìm thấy search API response → Trích xuất từ tracking events...")
        products = extract_products_from_tracking(captured)
        source = "tracking events"

    print(f"\n✅ Trích xuất được {len(products)} sản phẩm từ {source}")

    # Bước 4: Xuất CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"shopee_products_{timestamp}.csv"
    to_csv(products, csv_file)

    # Preview
    if products:
        print(f"\n── Preview 5 sản phẩm đầu ──")
        for i, p in enumerate(products[:5], 1):
            name = p.get("name", f"Item #{p['item_id']}")
            print(f"  {i}. {name}")
            print(f"     💰 {p['price']:,.0f} VND (min: {p['price_min']:,.0f} ~ max: {p['price_max']:,.0f})")
            print(f"     🛒 Đã bán: {p['sold']} | ⭐ {p['rating']} | 🏷️ Giảm: {p['discount']}%")
            print(f"     🔗 {p['url']}")
            print()
