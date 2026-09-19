"""Fetch GloweUp Studio's public Shopify catalog into data/catalog.json + data/images/."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

STORE = "https://gloweupstudio.com"
UA = "GloweUpFounderDemo/1.0 (catalog ingest for private founder demo)"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
IMAGES_DIR = DATA_DIR / "images"
CATALOG_PATH = DATA_DIR / "catalog.json"
MIN_PRODUCTS = 15


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._chunks)).strip()


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def paginate_products(base_url: str) -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        sep = "&" if "?" in base_url else "?"
        data = fetch_json(f"{base_url}{sep}page={page}&limit=250")
        batch = data.get("products") or []
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
        time.sleep(0.15)
    return products


def image_ext(src: str) -> str:
    path = urllib.parse.urlparse(src).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"


def download(src: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return True
    req = urllib.request.Request(src, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
        return dest.stat().st_size > 0
    except urllib.error.URLError as exc:
        print(f"  skip image {src}: {exc}", file=sys.stderr)
        return False


def variant_row(v: dict) -> dict:
    return {
        "id": v.get("id"),
        "title": v.get("title"),
        "sku": v.get("sku"),
        "price": v.get("price"),
        "compare_at_price": v.get("compare_at_price"),
        "available": bool(v.get("available")),
        "grams": v.get("grams"),
        "option1": v.get("option1"),
        "option2": v.get("option2"),
        "option3": v.get("option3"),
    }


def normalize(product: dict, collections_by_id: dict[int, list[str]]) -> dict:
    variants = [variant_row(v) for v in product.get("variants") or []]
    first = variants[0] if variants else {}
    handle = product["handle"]
    images = []
    for i, img in enumerate(product.get("images") or [], start=1):
        src = img.get("src") or ""
        local_rel = f"images/{handle}/{i}{image_ext(src)}" if src else None
        images.append(
            {
                "src": src,
                "local": local_rel,
                "width": img.get("width"),
                "height": img.get("height"),
                "position": img.get("position", i),
                "alt": img.get("alt"),
            }
        )
    pid = product["id"]
    return {
        "id": pid,
        "title": product.get("title"),
        "handle": handle,
        "url": f"{STORE}/products/{handle}",
        "vendor": product.get("vendor") or "",
        "collections": collections_by_id.get(pid, []),
        "description_html": product.get("body_html") or "",
        "description_text": html_to_text(product.get("body_html") or ""),
        "price": first.get("price"),
        "compare_at_price": first.get("compare_at_price"),
        "available": first.get("available", False),
        "sku": first.get("sku"),
        "variants": variants,
        "images": images,
    }


def assert_catalog(products: list[dict]) -> None:
    assert len(products) >= MIN_PRODUCTS, f"expected >= {MIN_PRODUCTS} products, got {len(products)}"
    missing_desc = [p["handle"] for p in products if not p.get("description_text")]
    assert not missing_desc, f"missing description_text: {missing_desc}"
    missing_img = [p["handle"] for p in products if not (p.get("images") and p["images"][0].get("src"))]
    assert not missing_img, f"missing image src: {missing_img}"


def main() -> int:
    print(f"Fetching products from {STORE}/products.json")
    raw_products = paginate_products(f"{STORE}/products.json")
    collections = fetch_json(f"{STORE}/collections.json").get("collections") or []

    collections_by_id: dict[int, list[str]] = {}
    collection_meta = []
    for col in collections:
        handle = col["handle"]
        title = re.sub(r"\s+", " ", (col.get("title") or handle)).strip()
        col_products = paginate_products(f"{STORE}/collections/{handle}/products.json")
        collection_meta.append(
            {
                "id": col.get("id"),
                "title": title,
                "handle": handle,
                "description_text": html_to_text(col.get("description") or ""),
                "products_count": len(col_products),
            }
        )
        for p in col_products:
            collections_by_id.setdefault(p["id"], [])
            if title not in collections_by_id[p["id"]]:
                collections_by_id[p["id"]].append(title)
        time.sleep(0.15)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    catalog_products = [normalize(p, collections_by_id) for p in raw_products]
    catalog_products.sort(key=lambda p: (p["title"] or "").lower())

    print(f"Downloading images for {len(catalog_products)} products")
    for product in catalog_products:
        for img in product["images"]:
            src = img.get("src")
            local = img.get("local")
            if not src or not local:
                continue
            dest = DATA_DIR / local
            ok = download(src, dest)
            if not ok:
                img["local"] = None

    catalog = {
        "store": STORE,
        "source": f"{STORE}/products.json",
        "product_count": len(catalog_products),
        "collections": collection_meta,
        "products": catalog_products,
    }
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert_catalog(catalog_products)
    print(f"Wrote {CATALOG_PATH} ({len(catalog_products)} products)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
