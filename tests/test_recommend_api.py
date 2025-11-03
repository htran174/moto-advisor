from app import app

def test_recommend_endpoint():
    client = app.test_client()
    resp = client.post("/api/recommend", json={
        "experience":"no_experience",
        "height_cm":170,
        "budget_usd":6000,
        "bike_types":["sportbike"],
        "k":3
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert "items" in data
    assert isinstance(data["items"], list)
