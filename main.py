"""
Vera Message Engine — magicpin AI Challenge
Uses Google Gemini API (FREE — no credit card needed)
Get your free key at: https://aistudio.google.com/app/apikey
"""

import os
import json
import time
import re
from datetime import datetime, timezone
from typing import Any, Optional

import google.generativeai as genai
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ─────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="Vera Message Engine", version="2.0.0")

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")   # Free tier model

START_TIME = time.time()

# ─────────────────────────────────────────────────────────────────────
# In-Memory Stores
# ─────────────────────────────────────────────────────────────────────
contexts: dict[tuple[str, str], dict] = {}      # (scope, context_id) → data
conversations: dict[str, dict] = {}             # conversation_id → state
suppressed: set[str] = set()                    # suppression keys already sent


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def context_counts() -> dict:
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _) in contexts:
        if scope in counts:
            counts[scope] += 1
    return counts


def resolve_digest_item(category_payload: dict, item_id: str) -> Optional[dict]:
    """Find a specific digest item inside a category context."""
    for item in category_payload.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def clean_json(raw: str) -> dict:
    """Strip markdown code fences and parse JSON."""
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        # Take the part after the first ```
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ─────────────────────────────────────────────────────────────────────
# Trigger Priority (higher = compose first)
# ─────────────────────────────────────────────────────────────────────
TRIGGER_PRIORITY = {
    "perf_spike": 10,
    "appointment_tomorrow": 10,
    "milestone_reached": 9,
    "category_trend_movement": 9,
    "review_theme_emerged": 9,
    "regulation_change": 8,
    "research_digest": 8,
    "recall_due": 8,
    "customer_lapsed": 7,
    "perf_dip": 7,
    "competitor_opened": 7,
    "festival_upcoming": 6,
    "weather_event": 6,
    "local_news_event": 6,
    "dormant_with_vera": 5,
    "curious_ask_due": 5,
    "scheduled_recurring": 4,
}

def get_trigger_priority(kind: str) -> int:
    kind_lower = kind.lower()
    for k, v in TRIGGER_PRIORITY.items():
        if k in kind_lower:
            return v
    return 3


# ─────────────────────────────────────────────────────────────────────
# Auto-reply Detection
# ─────────────────────────────────────────────────────────────────────
AUTO_REPLY_MARKERS = [
    "thank you for contacting",
    "our team will respond",
    "automated message",
    "currently unavailable",
    "auto reply",
    "auto-reply",
    "get back to you",
    "out of office",
    "aapki jaankari ke liye",
    "bahut-bahut shukriya",
    "automated assistant",
    "team tak pahuncha",
    "main ek automated",
]

def is_auto_reply(text: str) -> bool:
    t = text.lower()
    return any(marker in t for marker in AUTO_REPLY_MARKERS)

def count_trailing_auto_replies(turns: list) -> int:
    """How many consecutive auto-replies are at the end of conversation?"""
    count = 0
    for turn in reversed(turns):
        if turn.get("from_role") in ("merchant", "customer") and is_auto_reply(turn.get("message", "")):
            count += 1
        else:
            break
    return count

def count_trailing_identical(turns: list) -> int:
    """How many consecutive identical messages at the end?"""
    if len(turns) < 2:
        return 0
    last_msg = turns[-1].get("message", "")
    count = 0
    for turn in reversed(turns):
        if turn.get("message", "") == last_msg and turn.get("from_role") != "vera":
            count += 1
        else:
            break
    return count


# ─────────────────────────────────────────────────────────────────────
# Intent Detection
# ─────────────────────────────────────────────────────────────────────
ACCEPT_WORDS = ["yes", "go ahead", "ok let's", "ok lets", "let's do it", "lets do it",
                "confirm", "send it", "proceed", "sure", "done", "bilkul",
                "haan", "theek hai", "karo", "chalo", "zaroor"]
REJECT_WORDS = ["not interested", "stop", "no thanks", "don't send", "remove",
                "unsubscribe", "bother", "useless", "nahi chahiye", "band karo", "mat bhejo"]
WAIT_WORDS = ["later", "not right now", "some other time", "maybe later",
              "bad mein", "kuch din", "thodi der", "abhi nahi"]

def detect_intent(msg: str) -> str:
    m = msg.lower()
    if any(w in m for w in REJECT_WORDS):
        return "reject"
    if any(w in m for w in WAIT_WORDS):
        return "wait"
    if any(w in m for w in ACCEPT_WORDS):
        return "accept"
    if "?" in msg:
        return "question"
    return "unknown"


# ─────────────────────────────────────────────────────────────────────
# LLM Composer Prompt
# ─────────────────────────────────────────────────────────────────────
COMPOSE_PROMPT_TEMPLATE = """You are Vera, magicpin's AI growth assistant for Indian merchants on WhatsApp.

Your job: compose ONE highly specific WhatsApp message grounded in the context below.

=== HARD RULES ===
1. NO URLs in the message body. Zero. Hard fail.
2. ONE primary CTA only (yes/no, confirm/cancel, or open question).
3. Use ONLY numbers and facts from the provided context. Never invent data.
4. No promotional hype ("AMAZING!", "BEST DEAL!"). Match the category voice.
5. No long openers like "Hope you're doing well..." — start with the hook.
6. Match language: if merchant languages includes "hi" → use natural Hindi-English mix.
7. send_as = "vera" for merchant-facing messages, "merchant_on_behalf" for customer-facing.
8. Body should be concise — 2-4 sentences max.

=== HOW TO SCORE 10/10 ===
• Specificity: use ONE concrete verifiable anchor — number, date, source, stat.
  GOOD: "2,100-patient JIDA trial" / "views up 28%" / "78 lapsed patients"
  BAD: "improve your visibility" / "run a campaign today"

• Category voice:
  - Dentist → peer_clinical (cite JIDA, use "caries"/"fluoride varnish", never "guaranteed")
  - Salon → visual-aspirational (slots, bridal window, trending looks)
  - Restaurant → appetite-first (covers, BOGO, delivery, combo deals)
  - Gym → coach-motivational (members, class, ad spend, conversion)
  - Pharmacy → utility-precise (batch numbers, molecule names, dispensed count)

• Merchant fit: use owner's FIRST NAME, their exact offers, their specific metrics.
• Trigger relevance: body must say WHY this message is going NOW.
• Engagement compulsion: pick one lever — loss aversion / curiosity / social proof / effort externalization / binary commit.

=== EXAMPLE HIGH-SCORE MESSAGES ===

Research digest (dentist):
"Dr. Meera, JIDA Oct: 3-mo fluoride recall cuts caries 38% better vs 6-mo (n=2,100, high-risk adults). Relevant to your 124 high-risk patients. Want me to pull the abstract + draft a patient WhatsApp? — JIDA Oct 2026 p.14"

Performance dip (gym):
"Karthik, views -30% this week — but this is the normal Apr-Jun gym lull across every metro (-25 to -35%). Skip ad spend now, save for Sept-Oct when conversion is 2x. Want me to draft a summer retention challenge for your 245 members?"

Festival trigger (restaurant):
"Suresh bhai, Mother's Day this Sunday — family dining searches up 3x in Indiranagar. Your Weekend Biryani Combo @ ₹249 is perfect for this. Want me to schedule a WhatsApp blast to your past customers? 40 reachable contacts."

=== CONTEXT ===
{CONTEXT_JSON}

=== OUTPUT ===
Return ONLY this JSON object. No markdown, no explanation:
{{
  "body": "<message text>",
  "cta": "binary_yes_no",
  "send_as": "vera",
  "template_name": "vera_generic_v1",
  "template_params": ["<owner_name>", "<trigger_label>", "<offer_or_hook>"],
  "suppression_key": "<echo the trigger suppression_key>",
  "rationale": "<1-2 sentences: which signal + why now + which compulsion lever used>"
}}

cta options: "binary_yes_no" | "binary_confirm_cancel" | "open_ended" | "multi_choice_slot" | "none"
send_as options: "vera" (for merchant) | "merchant_on_behalf" (for customer)"""


REPLY_PROMPT_TEMPLATE = """You are Vera, magicpin's AI growth assistant. You are continuing a WhatsApp conversation.

The merchant just replied. You must respond appropriately.

=== REPLY RULES ===
- If merchant ACCEPTED (yes/go ahead/confirm/haan): SWITCH TO ACTION MODE immediately.
  Do NOT ask another qualifying question. Draft the next artifact. State concrete next step + measurable scope.
- If merchant asked a QUESTION: answer with specific facts/numbers from context. Advance toward action.
- NEVER send the same message text twice in a conversation.
- Keep reply shorter than opening message — conversation is already warm.
- Same rules: no URLs, one CTA, no fabrication, match language.

=== CONTEXT ===
{CONTEXT_JSON}

=== OUTPUT ===
Return ONLY this JSON object. No markdown, no explanation:
{{
  "body": "<reply message>",
  "cta": "binary_yes_no",
  "rationale": "<why this reply, what mode you are in>"
}}"""


def call_gemini(prompt: str) -> dict:
    """Call Gemini and parse JSON response."""
    generation_config = genai.types.GenerationConfig(
        temperature=0.0,          # Deterministic
        max_output_tokens=600,
    )
    response = model.generate_content(
        prompt,
        generation_config=generation_config,
    )
    raw = response.text
    result = clean_json(raw)
    # Safety: remove any URLs that slipped through
    body = result.get("body", "")
    body = re.sub(r'https?://\S+', '', body).strip()
    result["body"] = body
    return result


def build_context_json(category: dict, merchant: dict, trigger: dict,
                       customer: Optional[dict], history: list,
                       resolved_digest: Optional[dict] = None) -> str:
    ctx = {
        "category": {
            "slug": category.get("slug", ""),
            "voice": category.get("voice", {}),
            "peer_stats": category.get("peer_stats", {}),
            "offer_catalog": category.get("offer_catalog", [])[:5],
            "seasonal_beats": category.get("seasonal_beats", []),
            "trend_signals": category.get("trend_signals", []),
            "resolved_digest_item": resolved_digest,
        },
        "merchant": merchant,
        "trigger": trigger,
    }
    if customer:
        ctx["customer"] = customer
    if history:
        ctx["recent_conversation"] = history[-4:]
    return json.dumps(ctx, ensure_ascii=False, indent=2)


def compose_message(category: dict, merchant: dict, trigger: dict,
                    customer: Optional[dict], history: list) -> dict:
    """Compose a proactive outbound message."""
    resolved_digest = None
    top_id = (trigger.get("payload") or {}).get("top_item_id")
    if top_id and category:
        resolved_digest = resolve_digest_item(category, top_id)

    ctx_json = build_context_json(category, merchant, trigger, customer, history, resolved_digest)
    prompt = COMPOSE_PROMPT_TEMPLATE.replace("{CONTEXT_JSON}", ctx_json)
    return call_gemini(prompt)


def compose_reply(category: dict, merchant: dict, trigger: dict,
                  customer: Optional[dict], history: list) -> dict:
    """Compose a reply to a merchant/customer message."""
    ctx_json = build_context_json(category, merchant, trigger, customer, history)
    prompt = REPLY_PROMPT_TEMPLATE.replace("{CONTEXT_JSON}", ctx_json)
    return call_gemini(prompt)


# ─────────────────────────────────────────────────────────────────────
# Pydantic Request Models
# ─────────────────────────────────────────────────────────────────────
class ContextReq(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: Optional[str] = None


class TickReq(BaseModel):
    now: str
    available_triggers: list[str] = []


class ReplyReq(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: Optional[str] = None
    turn_number: int = 1


# ─────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────

@app.get("/v1/healthz")
def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": context_counts(),
    }


@app.get("/v1/metadata")
def metadata():
    return {
        "team_name": "Vera Bot",
        "team_members": ["Candidate"],
        "model": "gemini-1.5-flash",
        "approach": (
            "4-context LLM composer using Gemini 1.5 Flash. "
            "Trigger-kind priority dispatch (spike > research/recall > dip > festival). "
            "Auto-reply detection (hint → wait 24h → end). "
            "Intent-transition routing (accept → action mode, reject → graceful exit). "
            "temperature=0 for determinism. Zero fabrication policy."
        ),
        "contact_email": "candidate@example.com",
        "version": "2.0.0",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/context")
def push_context(req: ContextReq):
    key = (req.scope, req.context_id)
    existing = contexts.get(key)

    # Same or older version → 409
    if existing is not None and existing["version"] >= req.version:
        return JSONResponse(
            status_code=409,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": existing["version"],
            },
        )

    ack_id = f"ack_{req.context_id}_v{req.version}"
    stored_at = datetime.now(timezone.utc).isoformat()
    contexts[key] = {
        "version": req.version,
        "payload": req.payload,
        "ack_id": ack_id,
        "stored_at": stored_at,
    }
    return {"accepted": True, "ack_id": ack_id, "stored_at": stored_at}


@app.post("/v1/tick")
def tick(req: TickReq):
    actions = []

    # Sort triggers by priority (highest first)
    def sort_key(trg_id: str) -> int:
        tc = contexts.get(("trigger", trg_id))
        if not tc:
            return 0
        kind = tc["payload"].get("kind", "")
        urgency = tc["payload"].get("urgency", 1)
        return get_trigger_priority(kind) + urgency

    sorted_triggers = sorted(req.available_triggers, key=sort_key, reverse=True)

    for trg_id in sorted_triggers:
        if len(actions) >= 20:   # Max 20 actions per tick
            break

        tc = contexts.get(("trigger", trg_id))
        if not tc:
            continue
        trigger = tc["payload"]

        # Skip suppressed triggers
        sup_key = trigger.get("suppression_key", "")
        if sup_key and sup_key in suppressed:
            continue

        # Skip expired triggers
        expires = trigger.get("expires_at")
        if expires:
            try:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                now_dt = datetime.fromisoformat(req.now.replace("Z", "+00:00"))
                if now_dt > exp_dt:
                    continue
            except Exception:
                pass

        merchant_id = trigger.get("merchant_id")
        customer_id = trigger.get("customer_id")
        if not merchant_id:
            continue

        # Look up contexts
        mc = contexts.get(("merchant", merchant_id))
        if not mc:
            continue
        merchant = mc["payload"]

        cat_slug = merchant.get("category_slug", "")
        cc = contexts.get(("category", cat_slug))
        category = cc["payload"] if cc else {}

        customer = None
        if customer_id:
            cuc = contexts.get(("customer", customer_id))
            if cuc:
                customer = cuc["payload"]

        # Build conversation ID
        trigger_date = req.now[:10]
        if customer_id:
            conv_id = f"conv_{customer_id}_{trigger.get('kind', 'msg')}_{trigger_date}"
        else:
            conv_id = f"conv_{merchant_id}_{trigger.get('kind', 'msg')}_{trigger_date}"

        # Skip suppressed conversations
        conv = conversations.get(conv_id, {})
        if conv.get("suppressed"):
            continue

        history = conv.get("turns", [])

        try:
            result = compose_message(category, merchant, trigger, customer, history)
        except Exception as e:
            print(f"[COMPOSE ERROR] {trg_id}: {e}")
            continue

        send_as = "merchant_on_behalf" if customer_id else "vera"
        result["send_as"] = send_as

        if sup_key:
            suppressed.add(sup_key)

        # Init/update conversation
        if conv_id not in conversations:
            conversations[conv_id] = {
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "turns": [],
                "suppressed": False,
            }
        conversations[conv_id]["turns"].append({
            "from_role": "vera",
            "message": result["body"],
            "ts": req.now,
        })

        # Template params
        owner = merchant.get("identity", {}).get("owner_first_name", "")
        trigger_label = trigger.get("kind", "update")
        active_offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
        offer_hint = active_offers[0].get("title", "") if active_offers else result["body"][:50]

        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": send_as,
            "trigger_id": trg_id,
            "template_name": result.get("template_name", "vera_generic_v1"),
            "template_params": [owner, trigger_label, offer_hint],
            "body": result["body"],
            "cta": result.get("cta", "open_ended"),
            "suppression_key": sup_key,
            "rationale": result.get("rationale", ""),
        })

    return {"actions": actions}


@app.post("/v1/reply")
def reply(req: ReplyReq):
    conv_id = req.conversation_id

    conv = conversations.get(conv_id) or {
        "merchant_id": req.merchant_id,
        "customer_id": req.customer_id,
        "turns": [],
        "suppressed": False,
    }

    # Add incoming message to history
    conv["turns"].append({
        "from_role": req.from_role,
        "message": req.message,
        "ts": req.received_at or datetime.now(timezone.utc).isoformat(),
        "turn_number": req.turn_number,
    })
    conversations[conv_id] = conv

    # ── Auto-reply detection ──────────────────────────────────────────
    auto_count = count_trailing_auto_replies(conv["turns"])
    same_count = count_trailing_identical(conv["turns"])
    repeat_count = max(auto_count, same_count)

    if repeat_count >= 3:
        conv["suppressed"] = True
        return {
            "action": "end",
            "rationale": f"Auto-reply detected {repeat_count}x consecutively. Owner not at phone. Closing.",
        }

    if repeat_count == 2:
        return {
            "action": "wait",
            "wait_seconds": 86400,
            "rationale": "Second consecutive identical/auto reply. Backing off 24 hours.",
        }

    if is_auto_reply(req.message) and repeat_count == 1:
        merchant_id = req.merchant_id or conv.get("merchant_id", "")
        merchant = contexts.get(("merchant", merchant_id), {}).get("payload", {})
        owner = merchant.get("identity", {}).get("owner_first_name", "")
        return {
            "action": "send",
            "body": (
                f"Looks like an auto-reply 🙂 "
                f"{owner + ', ' if owner else ''}when you see this, just reply YES to continue."
            ),
            "cta": "binary_yes_no",
            "rationale": "Detected WA Business auto-reply. One prompt to reach owner.",
        }

    # ── Intent detection ──────────────────────────────────────────────
    intent = detect_intent(req.message)

    if intent == "reject":
        conv["suppressed"] = True
        return {
            "action": "send",
            "body": "Samajh gayi — won't message again. Say 'Hi Vera' anytime to restart. 🙏",
            "cta": "none",
            "rationale": "Merchant expressed disinterest. Graceful exit with opt-back-in path.",
        }

    if intent == "wait":
        return {
            "action": "wait",
            "wait_seconds": 3600,
            "rationale": "Merchant asked for later. Backing off 1 hour.",
        }

    # ── Normal reply: compose response ───────────────────────────────
    merchant_id = req.merchant_id or conv.get("merchant_id", "")
    customer_id = req.customer_id or conv.get("customer_id")

    merchant = contexts.get(("merchant", merchant_id), {}).get("payload", {})
    cat_slug = merchant.get("category_slug", "")
    category = contexts.get(("category", cat_slug), {}).get("payload", {})
    customer = None
    if customer_id:
        cuc = contexts.get(("customer", customer_id))
        if cuc:
            customer = cuc["payload"]

    # Build a synthetic trigger for reply context
    intent_instruction = ""
    if intent == "accept":
        intent_instruction = (
            "\n\nCRITICAL: Merchant ACCEPTED. Do NOT ask another question. "
            "Switch to ACTION MODE: state exactly what you will do, give measurable scope (how many customers, time estimate), "
            "then ask for final CONFIRM."
        )
    elif intent == "question":
        intent_instruction = (
            "\n\nMerchant asked a question. Answer with specific facts from context. "
            "Advance conversation toward the action step."
        )

    reply_trigger = {
        "kind": "merchant_reply",
        "merchant_id": merchant_id,
        "customer_id": customer_id,
        "payload": {
            "merchant_message": req.message,
            "intent": intent,
            "turn_number": req.turn_number,
        },
        "urgency": 3,
        "suppression_key": f"reply:{conv_id}:t{req.turn_number}",
    }

    # Build reply prompt with intent instruction added
    ctx_json = build_context_json(category, merchant, reply_trigger, customer, conv["turns"])
    prompt = (REPLY_PROMPT_TEMPLATE + intent_instruction).replace("{CONTEXT_JSON}", ctx_json)

    try:
        result = call_gemini(prompt)
    except Exception as e:
        print(f"[REPLY ERROR] {e}")
        return {
            "action": "send",
            "body": "On it — give me just a moment to pull that together.",
            "cta": "none",
            "rationale": f"Fallback response due to error: {e}",
        }

    body = result.get("body", "")

    # Anti-repetition check
    past_vera_msgs = [t["message"] for t in conv["turns"] if t.get("from_role") == "vera"]
    if body in past_vera_msgs:
        body = body.rstrip(".") + " Aage kaise proceed karna hai?"

    # Save Vera's reply to history
    conv["turns"].append({
        "from_role": "vera",
        "message": body,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "action": "send",
        "body": body,
        "cta": result.get("cta", "open_ended"),
        "rationale": result.get("rationale", ""),
    }


@app.post("/v1/teardown")
def teardown():
    """Called by judge at end of test to wipe state."""
    contexts.clear()
    conversations.clear()
    suppressed.clear()
    return {"cleared": True, "ts": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────────────────
# Local run
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
