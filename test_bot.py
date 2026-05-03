"""
Quick test for all 5 endpoints.
Run: python test_bot.py
Make sure server is running first: uvicorn main:app --port 8000
"""

import requests
import json

BOT = "http://localhost:8000"

def test(name, response, expected=200):
    ok = response.status_code == expected
    icon = "✅" if ok else "❌"
    try:
        body = response.json()
    except Exception:
        body = response.text
    print(f"{icon} {name}")
    if not ok:
        print(f"   Expected HTTP {expected}, got {response.status_code}")
    # Show key output
    if isinstance(body, dict):
        if "body" in body:
            print(f"   MESSAGE: {body['body'][:180]}")
        if "actions" in body and body["actions"]:
            a = body["actions"][0]
            print(f"   MESSAGE: {a.get('body','')[:180]}")
            print(f"   CTA: {a.get('cta')} | SEND_AS: {a.get('send_as')}")
        if "action" in body:
            print(f"   ACTION: {body['action']} | {body.get('body','')[:100]}")
    print()

print("=" * 55)
print("  Vera Bot — Endpoint Tests")
print("=" * 55, "\n")

# 1. Health check
test("GET /v1/healthz", requests.get(f"{BOT}/v1/healthz"))

# 2. Metadata
test("GET /v1/metadata", requests.get(f"{BOT}/v1/metadata"))

# 3. Push dentist category
test("POST /v1/context (category)", requests.post(f"{BOT}/v1/context", json={
    "scope": "category", "context_id": "dentists", "version": 1,
    "delivered_at": "2026-05-03T09:00:00Z",
    "payload": {
        "slug": "dentists",
        "voice": {"tone": "peer_clinical", "vocab_taboo": ["guaranteed", "miracle"]},
        "peer_stats": {"avg_rating": 4.4, "avg_ctr": 0.030},
        "offer_catalog": [{"id": "den_001", "title": "Dental Cleaning @ ₹299", "value": "299"}],
        "digest": [{
            "id": "d_2026W17_jida_fluoride", "kind": "research",
            "title": "3-month fluoride recall cuts caries 38% better than 6-month",
            "source": "JIDA Oct 2026, p.14", "trial_n": 2100,
            "patient_segment": "high_risk_adults"
        }],
        "seasonal_beats": [{"month_range": "Nov-Feb", "note": "exam-stress bruxism spike"}],
        "trend_signals": [{"query": "clear aligners delhi", "delta_yoy": 0.62}],
    }
}))

# 4. Push merchant
test("POST /v1/context (merchant)", requests.post(f"{BOT}/v1/context", json={
    "scope": "merchant", "context_id": "m_001_drmeera_dentist_delhi", "version": 1,
    "delivered_at": "2026-05-03T09:01:00Z",
    "payload": {
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "category_slug": "dentists",
        "identity": {
            "name": "Dr. Meera's Dental Clinic", "city": "Delhi",
            "locality": "Lajpat Nagar", "verified": True,
            "languages": ["en", "hi"], "owner_first_name": "Meera"
        },
        "subscription": {"status": "active", "plan": "Pro", "days_remaining": 82},
        "performance": {"views": 2410, "calls": 18, "ctr": 0.021,
                        "delta_7d": {"views_pct": 0.18, "calls_pct": -0.05}},
        "offers": [{"id": "o1", "title": "Dental Cleaning @ ₹299", "status": "active"}],
        "customer_aggregate": {"total_unique_ytd": 540, "lapsed_180d_plus": 78,
                               "retention_6mo_pct": 0.38, "high_risk_adult_count": 124},
        "signals": ["stale_posts:22d", "ctr_below_peer_median", "high_risk_adult_cohort"],
        "conversation_history": []
    }
}))

# 5. Idempotency test (same version → should return 409)
test("POST /v1/context (idempotent → 409)", requests.post(f"{BOT}/v1/context", json={
    "scope": "merchant", "context_id": "m_001_drmeera_dentist_delhi", "version": 1,
    "delivered_at": "2026-05-03T09:01:00Z", "payload": {}
}), expected=409)

# 6. Push trigger
test("POST /v1/context (trigger)", requests.post(f"{BOT}/v1/context", json={
    "scope": "trigger", "context_id": "trg_001", "version": 1,
    "delivered_at": "2026-05-03T09:02:00Z",
    "payload": {
        "id": "trg_001", "kind": "research_digest", "source": "external",
        "merchant_id": "m_001_drmeera_dentist_delhi", "customer_id": None,
        "payload": {"category": "dentists", "top_item_id": "d_2026W17_jida_fluoride"},
        "urgency": 2,
        "suppression_key": "research:dentists:2026-W17",
        "expires_at": "2026-06-01T00:00:00Z"
    }
}))

# 7. Tick — this calls Gemini and composes a message!
print("⏳ Calling Gemini AI (may take 5-10 seconds)...")
tick_resp = requests.post(f"{BOT}/v1/tick", json={
    "now": "2026-05-03T10:00:00Z",
    "available_triggers": ["trg_001"]
}, timeout=30)
test("POST /v1/tick (compose message)", tick_resp)

# 8. Reply — merchant says YES
conv_id = None
if tick_resp.status_code == 200 and tick_resp.json().get("actions"):
    conv_id = tick_resp.json()["actions"][0]["conversation_id"]

if conv_id:
    print("⏳ Composing reply (Gemini)...")
    test("POST /v1/reply (merchant says YES)", requests.post(f"{BOT}/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": "Yes please send the abstract",
        "received_at": "2026-05-03T10:05:00Z",
        "turn_number": 2
    }, timeout=30))

    # 9. Auto-reply test
    print("⏳ Testing auto-reply detection...")
    test("POST /v1/reply (auto-reply)", requests.post(f"{BOT}/v1/reply", json={
        "conversation_id": conv_id + "_ar",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly.",
        "received_at": "2026-05-03T10:06:00Z",
        "turn_number": 2
    }, timeout=30))

print("=" * 55)
print("Done! If you see mostly ✅, your bot is working.")
print("Now deploy it and submit the URL to magicpin!")
print("=" * 55)
