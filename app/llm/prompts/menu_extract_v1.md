# menu_extract_v1 (vision or text)
Extract menu items and prices from the photo or text. Indian menus: prices are in rupees; "60/-", "₹60", "Rs 60" all mean 60.

Return ONLY JSON: {"items": [{"name": str, "price_inr": int|null}], "uncertain": [str]}
Rules: never guess an unreadable price (use null and add the item name to "uncertain"). Keep item names as written, fix obvious spelling only. If half/full prices exist, make two items: "Momo (Half)" and "Momo (Full)". Ignore phone numbers, addresses, and slogans.
