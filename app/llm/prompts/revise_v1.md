# revise_v1 (text/structured)
Convert the owner's WhatsApp message (Hinglish, Hindi, or English) into a RevisionRequest JSON.

Context given: current plan summary, business menu prices.

Mapping examples:
- "ok", "haan", "theek hai", "👍", "post kar dunga" -> {"approve": true}
- "price 129", "rate 129 kar do", "₹129" -> {"price_inr": 129}
- "chhota karo", "shorter", "thoda chota" -> {"shorter": true}
- "lamba karo", "longer" -> {"longer": true}
- "naya hook", "hook change", "different start" -> {"regenerate_hook": true}
- "text mein 'Aaj hi aao' likho" -> {"text_change": "Aaj hi aao"}
- "cancel", "rehne do" -> {"cancel": true}
- Anything unrelated or unclear -> {"unclear": true}

Rules: return ONLY JSON. Multiple changes in one message are allowed. Never set price_inr unless a number clearly refers to price. Do not interpret as approval unless the owner clearly approves.
