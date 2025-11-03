# services/images_google.py
import os
import requests

GOOGLE_CSE_KEY = os.getenv("GOOGLE_CSE_KEY") or os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_CX  = os.getenv("GOOGLE_CSE_CX") or os.getenv("GOOGLE_CSE_ID")   # supports legacy var

def search_first_image(query: str) -> str | None:
    """
    Returns the first image link for the query, or None.
    """
    if not GOOGLE_CSE_KEY or not GOOGLE_CSE_CX or not query:
        return None

    try:
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": GOOGLE_CSE_KEY,
                "cx": GOOGLE_CSE_CX,
                "q": query,
                "searchType": "image",
                "num": 1,
                "safe": "active",
            },
            timeout=6,
        )
        r.raise_for_status()
        data = r.json()
        items = (data or {}).get("items") or []
        return items[0]["link"] if items else None
    except Exception:
        return None
