from services.images import get_images

def test_local_manifest_hit():
    payload = {"id":"yamaha_r3", "query":"Yamaha R3", "limit":1}
    data = get_images(payload, offline_mode=True, google=None)
    assert data["images"][0]["url"].startswith("/static/")
