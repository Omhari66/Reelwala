# WhatsApp conversation flow

Keep every message SHORT (under 300 characters), friendly, simple Hinglish by default (match the owner's chosen language). Use at most one emoji per message. Store all copy in `app/conversation/copy.py` as constants so it can be edited without touching logic.

## States
`NEW_USER -> ONBOARDING (name -> category -> language -> landmark -> brand colour) -> MENU_SETUP -> READY -> PROCESSING -> AWAITING_APPROVAL <-> REVISION -> READY`

## Global commands (work in any state)
`help`, `menu`, `status`, `cancel`, `restart`, `ok/yes/approve` (only in AWAITING_APPROVAL).

## Messages (Hinglish default)

**Greeting (NEW_USER)**
"Namaste! Main Reelwala hoon. Aap clips bhejiye, main ready Reel bana dunga. Pehle aapki dukaan ka naam batayein?"

**Category**: "Kaunsa business hai? 1) Food stall 2) Café/Restaurant 3) Bakery/Sweets 4) Other"
**Language**: "Reel mein kaunsi bhasha? 1) Hinglish 2) Hindi 3) English"
**Landmark**: "Aapki dukaan kahan hai? (jaise: XYZ College gate ke paas)"
**Brand colour**: "Reel ka rang? 1) Orange 2) Red 3) Yellow 4) Green 5) Blue" (map to hex in code)

**Menu setup**
"Apna menu ki photo bhejiye, ya aise likhiye: Momo 60, Combo 99"
After extraction: "Maine ye padha:\n- Veg Momo ₹60\n- Combo ₹99\nSahi hai? YES likhiye, ya correction bhejiye."

**Ready / no clips sent**
"Reel ke liye 3 clips film karein (phone seedha pakdein):\n1) Steam ya sizzle close-up (3 sec)\n2) Tayaar dish close-up (3 sec)\n3) Customer ko dete hue ya aapki smile (3 sec)\nPhir clips yahin bhej dein, aur likhein kya promote karna hai."

**Clips received**
"Mil gaye! Reel bana raha hoon, ~3 minute lagenge."

**Preview**
[video] + "Ye lijiye aapki Reel. Sahi hai to OK likhiye. Badlav chahiye to likhiye: 'price 129', 'chhota karo', 'naya hook'."

**Revision started**: "Theek hai, badal raha hoon."
**Revision limit**: "3 badlav ho chuke. Ye version final kar dein ya naye clips bhejein?"

**Approved**
[final video] + caption text + hashtags + "Instagram par post karte waqt trending audio chahein to wahin add kar sakte hain. Next Reel ke liye clips bhej dein!"

**Price mismatch (needs owner)**
"Aapne ₹129 likha par menu mein ₹99 hai. Kaunsa sahi hai? 99 ya 129?"

**Bad footage**
"Clips thode dark/hilte hue hain, isliye Reel weak banegi. Ek baar roshni mein, phone steady rakh kar film karein: [shot list]"

**Limit reached**: "Is mahine ki 10 Reels ho gayi. Agle mahine fir bhejiye!"
**Unknown message**: "Samajh nahi aaya. 'help' likhiye ya clips bhejiye."
**Error**: "Kuch gadbad ho gayi, hum dobara try kar rahe hain. 5 minute mein jawab milega."

## Rules
- Group all media received within 60 seconds of the last media into ONE campaign (debounce in worker, not in webhook).
- Voice notes: transcribe (faster-whisper, optional) then treat as text. If transcription disabled, reply asking for text.
- Images (non-menu) become 3-second clips.
- If owner message contains a price not in the menu, ask once before using it.
- Confirmation words (case-insensitive): ok, okay, yes, haan, ha, approve, done, theek hai, 👍.
- Cancel words: cancel, band karo, rehne do.
- Deduplicate by `provider_msg_id`. Process messages for one business sequentially (per-business lock).
- WhatsApp session window: if last owner message > 24h ago, only template messages are allowed (Meta). For Twilio sandbox just log a warning.
