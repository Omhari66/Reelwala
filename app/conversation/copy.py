"""Centralised copy text for WhatsApp conversation flow."""

GREETING = (
    "Namaste! Main Reelwala hoon. Aap clips bhejiye, main ready Reel bana dunga. "
    "Pehle aapki dukaan ka naam batayein?"
)
ASK_CATEGORY = "Kaunsa business hai? 1) Food stall 2) Café/Restaurant 3) Bakery/Sweets 4) Other"
ASK_LANGUAGE = "Reel mein kaunsi bhasha? 1) Hinglish 2) Hindi 3) English"
ASK_LANDMARK = "Aapki dukaan kahan hai? (jaise: XYZ College gate ke paas)"
ASK_BRAND_COLOR = "Reel ka rang? 1) Orange 2) Red 3) Yellow 4) Green 5) Blue"
MENU_SETUP = "Apna menu ki photo bhejiye, ya aise likhiye: Momo 60, Combo 99"
READY_NO_CLIPS = (
    "Reel ke liye 3 clips film karein (phone seedha pakdein):\n"
    "1) Steam ya sizzle close-up (3 sec)\n"
    "2) Tayaar dish close-up (3 sec)\n"
    "3) Customer ko dete hue ya aapki smile (3 sec)\n"
    "Phir clips yahin bhej dein, aur likhein kya promote karna hai."
)
CLIPS_RECEIVED = "Mil gaye! Reel bana raha hoon, ~3 minute lagenge."
REVISION_STARTED = "Theek hai, badal raha hoon."
REVISION_LIMIT = "3 badlav ho chuke. Ye version final kar dein ya naye clips bhejein?"
PRICE_MISMATCH = "Aapne ₹{owner_price} likha par menu mein ₹{menu_price} hai. Kaunsa sahi hai? {menu_price} ya {owner_price}?"
BAD_FOOTAGE = (
    "Clips thode dark/hilte hue hain, isliye Reel weak banegi. "
    "Ek baar roshni mein, phone steady rakh kar film karein: {tip}"
)
LIMIT_REACHED = "Is mahine ki 10 Reels ho gayi. Agle mahine fir bhejiye!"
MEDIA_TOO_LARGE = "Video file 50 MB se badi hai. Kripya chhoti clip bhejiye."
MEDIA_TOO_LONG = "Clip 60 second se zyada lambi hai. Reel ke liye 3-10 second ki short clip bhejiye."
JOB_IN_PROGRESS = "Aapki pichhli Reel abhi ban rahi hai. Kripya thoda intezaar karein."
UNKNOWN_MESSAGE = "Samajh nahi aaya. 'help' likhiye ya clips bhejiye."
GENERIC_ERROR = "Kuch gadbad ho gayi, hum dobara try kar rahe hain. 5 minute mein jawab milega."

CONFIRM_MENU_ITEMS = "Maine ye padha:\n{items}\nSahi hai? YES likhiye, ya correction bhejiye."
MENU_EMPTY = "Aapke menu mein abhi koi item nahi hai. Naye items likhiye, jaise: Momo 60, Combo 99"
HELP_MESSAGE = (
    "Reelwala commands:\n"
    "- 3 vertical clips bhejein Reel banane ke liye\n"
    "- 'menu': menu dekhne ya update karne ke liye\n"
    "- 'status': account status janne ke liye\n"
    "- 'restart': profile shuru se setup karne ke liye\n"
    "- 'cancel': current action cancel karne ke liye"
)
RESTART_CONFIRM = "Sab reset kar diya hai. " + GREETING
CANCEL_MESSAGE = "Cancelled. Jab tayaar hon, 'help' likhiye ya clips bhej dein."
STATUS_READY = "Aapki dukaan setup hai aur Reel banane ke liye ready hai! 3 vertical clips bhej dein."
STATUS_ONBOARDING = "Aapka setup chal raha hai. Kripya pichhle sawal ka jawab dein ya 'help' likhein."
VOICE_NOTE_DISABLED = "Voice note mila, par voice notes abhi supported nahi hain. Kripya apna message text mein likh kar bhejiye."


