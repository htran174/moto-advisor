from services.chat_nlu import nlu

def test_offtopic_guard():
    out = nlu("write a python script")
    assert out["topic"] == "OFFTOPIC"
    assert out["actions"] == []

def test_extract_and_recommend():
    out = nlu("I'm 175 cm, budget 7000, prefer naked. Please recommend.")
    assert out["topic"] in ("MOTO_DOMAIN","AMBIGUOUS")
    acts = [a["type"] for a in out["actions"]]
    assert "UPDATE_PROFILE" in acts
    assert "RECOMMEND" in acts
