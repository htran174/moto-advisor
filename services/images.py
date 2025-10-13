# services/images.py
# Local-first image lookup. Ensures manifest/local_image point at /static/stock_images/...

import os, json
from flask import url_for
from dotenv import load_dotenv

load_dotenv()

IMAGES_MANIFEST_PATH = os.path.join("static", "images.json")

def _load_local_manifest():
    try:
        with open(IMAGES_MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[images] manifest read warning: {e}")
        return {}

MANIFEST = _load_local_manifest()

def _with_stock_prefix(path: str | None) -> str:
    if not path:
        return "stock_images/motorcycle_ride.jpg"
    return path if path.startswith("stock_images/") else f"stock_images/{path}"

def get_image_results(data: dict) -> dict:
    """
    Input: { id, query, local_image, mfr_domain, limit }
    Output: { source: 'local'|'fallback', images: [{url,width,height}] }
    """
    # 1) explicit local_image from the caller
    local_image = data.get("local_image")
    if local_image:
        path = _with_stock_prefix(local_image)
        return {"source": "local",
                "images": [{"url": url_for("static", filename=path), "width": 1200, "height": 800}]}

    # 2) manifest hit by id
    bid = data.get("id")
    if bid and bid in MANIFEST:
        path = _with_stock_prefix(MANIFEST[bid])
        return {"source": "local",
                "images": [{"url": url_for("static", filename=path), "width": 1200, "height": 800}]}

    # 3) fallback stock
    return {"source": "fallback",
            "images": [{"url": url_for("static", filename="stock_images/motorcycle_ride.jpg"),
                        "width": 1200, "height": 800}]}
