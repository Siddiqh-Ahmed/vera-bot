#!/usr/bin/env python3
"""
Smoke test matching the judge harness flow from challenge-testing-brief.md
Run: BOT_URL=http://localhost:8000 python test_local.py

Covers:
- Phase 1: healthz, metadata, context push (category + merchant + customer + trigger)
- Idempotency (same version → 409, higher version → 200)
- Phase 2: tick with trigger → actions
- Phase 3: reply flow (YES → action mode, auto-reply detection, reject → exit)
"""

import json
import sys
import requests

BASE = os.environ.get("BOT_URL", "http://localhost:8000")
import os
BASE = os.environ.get("BOT_URL", "http://localhost:8000")

PASS = 0
FAIL = 0

def check(label: str, resp: requests.Response, expect_status: int = 200):
    global PASS, FAIL
    ok = resp.status_code == expect_status
    icon = "✅" if ok else "❌"
    if not ok:
        FAIL += 1
    else:
        PASS += 1
    try:
        body = resp.json()
        body_str = json.dumps(body, indent=2, ensure_ascii=False)[:400]
    except Exception:
        body_str = resp.text[:200]
    print(f"{icon} [{resp.status_code}] {label}")
    if not ok:
        print(f"   Expected {expect_status}, got {resp.status_code}")
    print(f"   {body_str}\n")
    return body if ok else None

# ── Phase 1: Warmup ───────────────────────────────────────────────────
print("=" * 60)
print("PHASE 1 — Warmup")
print("=" * 60)

# 1.1 Healthz (before context)
r = requests.get(f"{BASE}/v1/healthz")
check("GET /v1/healthz (before context)", r)

# 1.2 Metadata
r = requests.get(f"{BASE}/v1/metadata")
check("GET /v1/metadata", r)

# 1.3 Push category context
dentist_category = {
    "scope": "category",
    "context_id": "dentists",
    "version": 1,
    "delivered_at": "2026-04-26T09:45:00Z",
    "payload": {
        "slug": "dentists",
        "display_name": "Dentists",
        "voice": {
            "tone": "peer_clinical",
            "register": "respectful_collegial",
            "code_mix": "hindi_english_natural",
            "vocab_allowed": ["fluoride varnish", "scaling", "caries", "bruxism", "RCT"],
            "vocab_taboo": ["guaranteed", "100% safe", "miracle", "best in city"],
            "salutation_examples": ["Dr. {first_name}", "Doc"],
        },
        "offer_catalog": [
            {"id": "den_001", "title": "Dental Cleaning @ ₹299", "value": "299", "audience": "new_user"},
            {"id": "den_002", "title": "Free Consultation", "value": "0", "audience": "new_user"},
            {"id": "den_003", "title": "Teeth Whitening @ ₹1,499", "value": "1499", "audience": "new_user"},
        ],
        "peer_stats": {"avg_rating": 4.4, "avg_ctr": 0.030, "avg_reviews": 62},
        "digest": [
            {
                "id": "d_2026W17_jida_fluoride",
                "kind": "research",
                "title": "3-month fluoride recall cuts caries 38% better than 6-month",
                "source": "JIDA Oct 2026, p.14",
                "trial_n": 2100,
                "patient_segment": "high_risk_adults",
                "summary": "RCT in 2,100 high-risk adults. 3-month recall interval showed 38% reduction in caries recurrence vs 6-month interval.",
            }
        ],
        "seasonal_beats": [{"month_range": "Nov-Feb", "note": "exam-stress bruxism spike"}],
        "trend_signals": [{"query": "clear aligners delhi", "delta_yoy": 0.62, "segment_age": "28-45"}],
    },
}
r = requests.post(f"{BASE}/v1/context", json=dentist_category)
check("POST /v1/context — dentist category", r)

# 1.4 Push merchant context
drmeera = {
    "scope": "merchant",
    "context_id": "m_001_drmeera_dentist_delhi",
    "version": 1,
    "delivered_at": "2026-04-26T09:45:30Z",
    "payload": {
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "category_slug": "dentists",
        "identity": {
            "name": "Dr. Meera's Dental Clinic",
            "city": "Delhi",
            "locality": "Lajpat Nagar",
            "verified": True,
            "languages": ["en", "hi"],
            "owner_first_name": "Meera",
        },
        "subscription": {"status": "active", "plan": "Pro", "days_remaining": 82},
        "performance": {
            "window_days": 30,
            "views": 2410,
            "calls": 18,
            "directions": 45,
            "ctr": 0.021,
            "delta_7d": {"views_pct": 0.18, "calls_pct": -0.05},
        },
        "offers": [
            {"id": "o_meera_001", "title": "Dental Cleaning @ ₹299", "status": "active"},
            {"id": "o_meera_002", "title": "Deep Cleaning @ ₹499", "status": "expired"},
        ],
        "conversation_history": [],
        "customer_aggregate": {
            "total_unique_ytd": 540,
            "lapsed_180d_plus": 78,
            "retention_6mo_pct": 0.38,
            "high_risk_adult_count": 124,
        },
        "signals": ["stale_posts:22d", "ctr_below_peer_median", "high_risk_adult_cohort"],
    },
}
r = requests.post(f"{BASE}/v1/context", json=drmeera)
check("POST /v1/context — Dr Meera merchant", r)

# 1.5 Idempotency: same version → 409
r = requests.post(f"{BASE}/v1/context", json=drmeera)
check("POST /v1/context — idempotent (same version → 409)", r, expect_status=409)

# 1.6 Version bump → 200
drmeera_v2 = {**drmeera, "version": 2}
drmeera_v2["payload"] = {**drmeera["payload"], "performance": {**drmeera["payload"]["performance"], "views": 2580}}
r = requests.post(f"{BASE}/v1/context", json=drmeera_v2)
check("POST /v1/context — version bump v2 → 200", r)

# 1.7 Push customer context
priya = {
    "scope": "customer",
    "context_id": "c_001_priya_for_m001",
    "version": 1,
    "delivered_at": "2026-04-26T09:46:00Z",
    "payload": {
        "customer_id": "c_001_priya_for_m001",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "identity": {"name": "Priya", "language_pref": "hi-en mix"},
        "relationship": {
            "first_visit": "2025-11-04",
            "last_visit": "2025-12-12",
            "visits_total": 4,
            "services_received": ["cleaning", "cleaning", "whitening", "cleaning"],
        },
        "state": "lapsed_soft",
        "preferences": {"preferred_slots": "weekday_evening", "channel": "whatsapp"},
        "consent": {"opted_in_at": "2025-11-04", "scope": ["recall_reminders"]},
    },
}
r = requests.post(f"{BASE}/v1/context", json=priya)
check("POST /v1/context — Priya customer", r)

# 1.8 Push trigger (research digest)
research_trg = {
    "scope": "trigger",
    "context_id": "trg_001_research_digest_dentists",
    "version": 1,
    "delivered_at": "2026-04-26T10:32:00Z",
    "payload": {
        "id": "trg_001_research_digest_dentists",
        "scope": "merchant",
        "kind": "research_digest",
        "source": "external",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "customer_id": None,
        "payload": {"category": "dentists", "top_item_id": "d_2026W17_jida_fluoride"},
        "urgency": 2,
        "suppression_key": "research:dentists:2026-W17",
        "expires_at": "2026-05-10T00:00:00Z",
    },
}
r = requests.post(f"{BASE}/v1/context", json=research_trg)
check("POST /v1/context — research digest trigger", r)

# 1.9 Push recall trigger (customer-scoped)
recall_trg = {
    "scope": "trigger",
    "context_id": "trg_002_recall_priya",
    "version": 1,
    "delivered_at": "2026-04-26T10:33:00Z",
    "payload": {
        "id": "trg_002_recall_priya",
        "scope": "customer",
        "kind": "recall_due",
        "source": "internal",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "customer_id": "c_001_priya_for_m001",
        "payload": {"recall_months": 6, "months_since_last_visit": 5},
        "urgency": 3,
        "suppression_key": "recall:c_001_priya_for_m001:6mo",
        "expires_at": "2026-06-01T00:00:00Z",
    },
}
r = requests.post(f"{BASE}/v1/context", json=recall_trg)
check("POST /v1/context — recall trigger (customer)", r)

# 1.10 Healthz after warmup — should show context counts
r = requests.get(f"{BASE}/v1/healthz")
data = check("GET /v1/healthz — after warmup", r)

# ── Phase 2: Test window ──────────────────────────────────────────────
print("=" * 60)
print("PHASE 2 — Test Window (Tick)")
print("=" * 60)

# 2.1 Tick with research digest trigger
tick1 = {
    "now": "2026-04-26T10:35:00Z",
    "available_triggers": ["trg_001_research_digest_dentists"],
}
r = requests.post(f"{BASE}/v1/tick", json=tick1)
tick_data = check("POST /v1/tick — research digest", r)

conv_id = None
if tick_data and tick_data.get("actions"):
    action = tick_data["actions"][0]
    conv_id = action.get("conversation_id")
    print(f"   📨 MESSAGE: {action.get('body', '')[:200]}")
    print(f"   🎯 CTA: {action.get('cta')}")
    print(f"   📝 RATIONALE: {action.get('rationale', '')[:150]}")
    required = ["conversation_id", "merchant_id", "send_as", "trigger_id", "body", "cta", "suppression_key", "rationale"]
    missing = [f for f in required if not action.get(f)]
    if missing:
        print(f"   ⚠️  MISSING FIELDS: {missing}")
    print()

# 2.2 Tick with recall trigger (customer-scoped)
tick2 = {
    "now": "2026-04-26T10:40:00Z",
    "available_triggers": ["trg_002_recall_priya"],
}
r = requests.post(f"{BASE}/v1/tick", json=tick2)
recall_data = check("POST /v1/tick — recall (customer)", r)
if recall_data and recall_data.get("actions"):
    a = recall_data["actions"][0]
    print(f"   📨 MESSAGE: {a.get('body', '')[:200]}")
    print(f"   send_as: {a.get('send_as')} (should be merchant_on_behalf)\n")

# 2.3 Empty tick (no triggers)
r = requests.post(f"{BASE}/v1/tick", json={"now": "2026-04-26T11:00:00Z", "available_triggers": []})
empty = check("POST /v1/tick — empty (should return actions: [])", r)
if empty:
    assert empty.get("actions") == [], f"Expected empty actions, got {empty}"

# ── Phase 3: Reply Flows ──────────────────────────────────────────────
print("=" * 60)
print("PHASE 3 — Reply Flows")
print("=" * 60)

if conv_id:
    # 3.1 Merchant says YES
    r = requests.post(f"{BASE}/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": "Yes please send the abstract",
        "received_at": "2026-04-26T10:42:00Z",
        "turn_number": 2,
    })
    d = check("POST /v1/reply — YES (action mode)", r)
    if d:
        print(f"   action: {d.get('action')} (should be send)")
        print(f"   📨 {d.get('body', '')[:200]}\n")

    # 3.2 Auto-reply (first)
    r = requests.post(f"{BASE}/v1/reply", json={
        "conversation_id": conv_id + "_auto",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly.",
        "received_at": "2026-04-26T10:50:00Z",
        "turn_number": 2,
    })
    d = check("POST /v1/reply — auto-reply #1 (should hint to owner)", r)
    if d:
        print(f"   action: {d.get('action')}")
        print(f"   📨 {d.get('body', '')[:200]}\n")

    # 3.3 Auto-reply (second — same message)
    r = requests.post(f"{BASE}/v1/reply", json={
        "conversation_id": conv_id + "_auto",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly.",
        "received_at": "2026-04-26T10:55:00Z",
        "turn_number": 3,
    })
    d = check("POST /v1/reply — auto-reply #2 (should wait 24h)", r)
    if d:
        print(f"   action: {d.get('action')} (should be wait)\n")

    # 3.4 Hostile / not interested
    r = requests.post(f"{BASE}/v1/reply", json={
        "conversation_id": conv_id + "_hostile",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": "Why are you bothering me. This is useless. Stop sending these.",
        "received_at": "2026-04-26T11:00:00Z",
        "turn_number": 2,
    })
    d = check("POST /v1/reply — hostile/reject (graceful exit)", r)
    if d:
        print(f"   action: {d.get('action')} (should be send or end)")
        print(f"   📨 {d.get('body', '')[:200]}\n")

# ── Summary ───────────────────────────────────────────────────────────
print("=" * 60)
total = PASS + FAIL
print(f"Result: {PASS}/{total} tests passed {'✅' if FAIL == 0 else '⚠️'}")
if FAIL:
    print(f"{FAIL} test(s) FAILED — check ❌ lines above")
print("=" * 60)
