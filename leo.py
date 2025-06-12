import random
import time
import json
import asyncio
import nest_asyncio
import re
import httpx
from faker import Faker
fake = Faker()
from threading import Timer
from telegram import Update, ChatMember, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, filters, InlineQueryHandler, CallbackQueryHandler
)

nest_asyncio.apply()

BOT_TOKEN = '8051926711:AAE9GVjJHdrG2JYBHIQCzE_MHMqyHWf1qkI'
ALLOWED_CHAT_ID = -1002693558851
ADMIN_ID = 5712886230
USER_DATA_FILE = "user_data.json"
bin_cache = {}

country_locale_map = {
    "germany": "de_DE",
    "us": "en_US",
    "usa": "en_US",
    "france": "fr_FR",
    "spain": "es_ES",
    "india": "en_IN",
    "russia": "ru_RU",
    "japan": "ja_JP",
    "china": "zh_CN",
    "brazil": "pt_BR",
    "italy": "it_IT",
    "canada": "en_CA",
    "australia": "en_AU",
    "uk": "en_GB",
    "mexico": "es_MX",
    "netherlands": "nl_NL",
    "turkey": "tr_TR",
    "poland": "pl_PL",
    "sweden": "sv_SE",
    "norway": "no_NO",
    "finland": "fi_FI",
    "denmark": "da_DK",
    "portugal": "pt_PT"
    # Add more as needed
}

def get_fake_address(country):
    locale = country_locale_map.get(country.lower())
    if not locale:
        return "Unsupported country. Please try another."
    fake = Faker(locale)
    address = fake.address().replace('\n', ', ')
    return f"Fake address for {country.title()}:\n{address}"

# --- AUTO-DELETE HELPER ---
async def delete_after_delay(msg, delay, context):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
    except Exception:
        pass  # Ignore errors if message is already deleted or can't be deleted

# ---- BIN Lookup ----
async def bin_lookup(bin_number: str):
    if bin_number in bin_cache:
        return bin_cache[bin_number]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(f"https://bins.su/lookup/{bin_number}")
                if r.status_code == 200:
                    d = r.json()
                    result = {
                        "info": f"{d.get('vendor', 'N/A').upper()} - {d.get('type', 'N/A').upper()} - {d.get('level', 'N/A')}",
                        "bank": d.get("bank", "Unknown Bank"),
                        "country": f"{d.get('country', 'Unknown Country')} - [{d.get('countryInfo', {}).get('emoji', '🏳️')}]"
                    }
                    bin_cache[bin_number] = result
                    return result
            except: pass
            try:
                r = await client.get(f"https://lookup.binlist.net/{bin_number}")
                if r.status_code == 200:
                    d = r.json()
                    result = {
                        "info": f"{d.get('scheme', 'N/A').upper()} - {d.get('type', 'N/A').upper()} - {d.get('brand', 'N/A')}",
                        "bank": d.get("bank", {}).get("name", "Unknown Bank"),
                        "country": f"{d.get('country', {}).get('name', 'Unknown Country')} - [{d.get('country', {}).get('emoji', '🏳️')}]"
                    }
                    bin_cache[bin_number] = result
                    return result
            except: pass
    except: pass
    result = {
        "info": "Unknown - Unknown - Unknown",
        "bank": "Unknown Bank",
        "country": "Unknown Country - [🏳️]"
    }
    bin_cache[bin_number] = result
    return result

def load_user_data():
    try:
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_data(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f)

user_data = load_user_data()

def get_credits(user_id: int):
    return user_data.get(str(user_id), {}).get("credits", 0)

def change_credits(user_id: int, amount: int):
    uid = str(user_id)
    if uid not in user_data:
        user_data[uid] = {"credits": 0, "last_daily": 0}
    user_data[uid]["credits"] = max(0, user_data[uid].get("credits", 0) + amount)
    save_user_data(user_data)

def insufficient_credits_message():
    return (
        "Insufficient Credits ⚠️\n"
        "Error : You Have Insufficient Credits to Use Me.\n"
        "Recharge Credit For Using Me.\n"
        "━━━━━━━━━━━━━\n"
        "Dm : @Sanjai10_oct_2k03"
    )

def format_output(card_info, card_type, gateway, status, response, bin_data, checked_by):
    return (
        f"💳 Card: {card_info}\n"
        f"🏷 Card Type: {card_type}\n"
        f"🛠 Gateway: {gateway}\n"
        f"📊 Status: {status}\n"
        f"📣 Response: {response}\n"
        f"🏦 Bank: {bin_data.get('bank', 'N/A')}\n"
        f"🌐 Country: {bin_data.get('country', 'N/A')}\n"
        f"🔢 BIN Info: {bin_data.get('info', 'N/A')}\n"
        f"✅ Checked By: @{checked_by}\n"
        f"━━━━━━━━━━━━━"
    )

def simulate_card_auth(card_number: str):
    prefixes = {
        "4": "VISA",
        "5": "MASTERCARD",
        "37": "AMERICAN EXPRESS",
        "6": "DISCOVER"
    }
    card_type = "UNKNOWN"
    for pfx, ctype in prefixes.items():
        if card_number.startswith(pfx):
            card_type = ctype
            break
    outcomes = [
        {"status": "Approved ✅", "response": "Payment method added.", "gateway": "Stripe Auth"},
        {"status": "Decline ❌", "response": "Card was declined", "gateway": "Stripe Auth"},
        {"status": "OTP_REQUIRED ❎", "response": "OTP Required", "gateway": "Shopify Normal"},
        {"status": "Decline ❌", "response": "Insufficient funds", "gateway": "PayPal"},
        {"status": "Decline ❌", "response": "Card expired", "gateway": "Authorize.Net"},
        {"status": "Approved ✅", "response": "Transaction approved", "gateway": "CyberSource"},
    ]
    weights = [0.3, 0.4, 0.1, 0.1, 0.05, 0.05]
    choice = random.choices(outcomes, weights)[0]
    return card_type, choice["gateway"], choice["status"], choice["response"]

def generate_card(bin_number):
    card_num = bin_number
    while len(card_num) < 16:
        card_num += str(random.randint(0, 9))
    return card_num

# --- AUTO-DELETE WRAPPER FOR REPLIES ---
async def send_timed_reply(update: Update, text: str, **kwargs):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    msg = await update.message.reply_text(text, **kwargs)
    asyncio.create_task(delete_after_delay(msg, 300, update))
    return msg

# ---- All Command Handlers ----

async def cmd_chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    user_id = update.effective_user.id
    checked_by = update.effective_user.username or update.effective_user.first_name or "Unknown_User"
    if len(context.args) != 1:
        await send_timed_reply(update, "Usage: .chk ")
        return
    try:
        card_number, exp_month, exp_year, cvv = context.args[0].split('|')
    except:
        await send_timed_reply(update, "Invalid format. Use: 5123456789012345|12|25|123")
        return
    bin_data = await bin_lookup(card_number[:6])
    card_type, gateway, status, response = simulate_card_auth(card_number)
    output = format_output(card_number, card_type, gateway, status, response, bin_data, checked_by)
    await send_timed_reply(update, output)
    change_credits(user_id, -1)

async def cmd_vbv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    uid = str(update.effective_user.id)
    role = user_data.get(uid, {}).get("role", "free")
    if role != "premium" and update.effective_user.id != ADMIN_ID:
        await send_timed_reply(update, "❌ This is a premium command.\nContact admin to get premium access.")
        return
    if len(context.args) != 1:
        await send_timed_reply(update, "Usage: .vbv ")
        return
    card_number = context.args[0]
    vbv_status = random.choice(["VBV Enabled ✅", "VBV Not Enabled ❌"])
    bin_data = await bin_lookup(card_number[:6])
    await send_timed_reply(
        update,
        f"💳 Card: {card_number}\n"
        f"🔐 VBV: {vbv_status}\n"
        f"🏦 Bank: {bin_data['bank']}\n"
        f"🌐 Country: {bin_data['country']}\n"
        f"━━━━━━━━━━━━━"
    )

async def cmd_slf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    uid = str(update.effective_user.id)
    role = user_data.get(uid, {}).get("role", "free")
    if role != "premium" and update.effective_user.id != ADMIN_ID:
        await send_timed_reply(update, "❌ This is a premium command.\nContact admin to get premium access.")
        return
    credits = get_credits(update.effective_user.id)
    await send_timed_reply(update, f"Hello {update.effective_user.first_name}, you have {credits} credits.")

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    change_credits(update.effective_user.id, 10)
    await send_timed_reply(update, "Admin recharge: 10 credits added.")

async def cmd_fake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    if len(context.args) != 1:
        await send_timed_reply(update, "Usage: .fake <country>")
        return
    country = context.args[0]
    locale = country_locale_map.get(country.lower())
    if not locale:
        await send_timed_reply(update, "Unsupported country. Please try another.")
        return
    fake = Faker(locale)
    full_name = fake.name()
    gender = fake.random_element(elements=("Male", "Female"))
    street = fake.street_address()
    city = fake.city()
    try:
        state = fake.state()
    except AttributeError:
        state = "-"
    try:
        postal_code = fake.postcode()
    except AttributeError:
        postal_code = "-"
    phone = fake.phone_number()
    country_name = fake.current_country() if hasattr(fake, "current_country") else country.title()
    email = fake.email()
    mail_box = "https://www.guerrillamail.com/"
    picture = f"https://randomuser.me/api/portraits/{'men' if gender == 'Male' else 'women'}/{random.randint(1,99)}.jpg"
    requested_by = update.effective_user.username or update.effective_user.first_name or "Unknown"
    output = (
        "Fake Info Created ✅\n"
        "━━━━━━━━━━━━━\n"
        f"[ϟ] Full Name : {full_name}\n"
        f"[ϟ] Gender : {gender}\n"
        f"[ϟ] Street : {street}\n"
        f"[ϟ] City : {city}\n"
        f"[ϟ] State : {state}\n"
        f"[ϟ] Postal Code : {postal_code}\n"
        f"[ϟ] Phone Number : {phone}\n"
        f"[ϟ] Country : {country_name}\n"
        f"[ϟ] Email : {email}\n"
        f"[ϟ] Mail Box : [Link]({mail_box})\n"
        f"[ϟ] Picture : [Pic]({picture})\n"
        "━━━━━━━━━━━━━\n"
        f"[ϟ] Req By : @{requested_by}\n"
        f"[⌥] Dev : 𝕊𝕒𝕟𝕛𝕦 - 🍀"
    )
    await send_timed_reply(update, output, parse_mode="Markdown")

async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    user_id = update.effective_user.id
    uid = str(user_id)
    now = int(time.time())
    user_entry = user_data.get(uid, {"credits": 0, "last_daily": 0})
    if now - user_entry.get("last_daily", 0) < 86400:
        await send_timed_reply(update, "You have already claimed your daily credits. Come back later.")
        return
    change_credits(user_id, 5)
    user_data[uid]["last_daily"] = now
    save_user_data(user_data)
    await send_timed_reply(update, "Daily credits claimed! You received 5 credits.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID: return
    help_text = """
╭━━━━━━━━━━━━━━━⪧
┃ ⚙️ 𝘾𝙊𝙈𝙈𝘼𝙉𝘿 𝙈𝙀𝙉𝙐
┣━━━━━━━━━━━━━━━⪧
🆓 𝙁𝙍𝙀𝙀 𝘾𝙊𝙈𝙈𝘼𝙉𝘿𝙎
┣ .chk
┣ .daily
┣ .info
┣ .plans
┣ .help
┣ .fake <country>
┣━━━━━━━━━━━━━━━━━⪧
💎 𝙋𝙍𝙀𝙈𝙄𝙐𝙈 𝘾𝙊𝙈𝙈𝘼𝙉𝘿𝙎
┣━━━━━━━━━━━━━━━━━⪧
┣ .vbv
┣ .mass
┣ .gen
┣ .bin
┣ .all
┣ .slf
┣━━━━━━━━━━━━━━━⪧
👑 𝘼𝘿𝙈𝙄𝙉 𝘾𝙊𝙈𝙈𝘼𝙉𝘿𝙎
┣━━━━━━━━━━━━━━━⪧
┣ .cr
┣ .setrole
╰━━━━━━━━━━━━━━━⪧
"""
    await send_timed_reply(update, help_text.strip())

async def cmd_cr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) != 2:
        await send_timed_reply(update, "Usage: .cr <user_id> <credits>")
        return
    try:
        user_id = int(context.args[0])
        credits = int(context.args[1])
        change_credits(user_id, credits)
        await send_timed_reply(update, f"✅ Credits updated successfully!")
    except Exception as e:
        await send_timed_reply(update, f"Error: {str(e)}")

async def cmd_mass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    uid = str(update.effective_user.id)
    role = user_data.get(uid, {}).get("role", "free")
    if role != "premium" and update.effective_user.id != ADMIN_ID:
        await send_timed_reply(update, "❌ This is a premium command.\nContact admin to get premium access.")
        return

    user_id = update.effective_user.id
    checked_by = update.effective_user.username or update.effective_user.first_name or "Unknown_User"
    cards = context.args

    if not cards:
        await send_timed_reply(update, "Usage: .mass <card1> <card2> ...")
        return

    if len(cards) > 20:
        cards = cards[:20]
        await send_timed_reply(update, "Only 20 cards allowed per check.")

    if get_credits(user_id) < len(cards) * 2:
        await send_timed_reply(update, insufficient_credits_message())
        return

    results = []
    valid_cards = []

    for card in cards:
        parts = card.split('|')
        if len(parts) != 4:
            results.append(f"Invalid format: {card}")
            continue
        card_number, mm, yy, cvv = parts
        valid_cards.append((card_number, mm, yy, cvv))

    for card_tuple in valid_cards:
        card_number, mm, yy, cvv = card_tuple
        bin_data = await bin_lookup(card_number[:6])
        card_info = f"{card_number}|{mm}|{yy}|{cvv}"
        card_type, gateway, status, response = simulate_card_auth(card_number)
        results.append(
            f"?? Card: {card_info}\n"
            f"?? {bin_data.get('bank', 'N/A')}\n"
            f"?? Status: {status}\n"
            f"?? Response: {response}\n"
            f"━━━━━━━━━━━━━"
        )
        change_credits(user_id, -2)

    # Send results in chunks if needed
    for chunk in [results[i:i+2] for i in range(0, len(results), 2)]:
        await send_timed_reply(update, "\n\n".join(chunk))


import random 

def get_deterministic_outcomes(card_number, all_auth_outcomes):
    # Use only digits from card_number for the seed
    seed = int(''.join(filter(str.isdigit, card_number)))
    rng = random.Random(seed)
    outcomes = all_auth_outcomes.copy()
    rng.shuffle(outcomes)
    return outcomes[:6]  # Show 6 varied outcomes per card

async def cmd_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    uid = str(update.effective_user.id)
    role = user_data.get(uid, {}).get("role", "free")
    if role != "premium" and update.effective_user.id != ADMIN_ID:
        await send_timed_reply(update, "❌ This is a premium command.\nContact admin to get premium access.")
        return
    user_id = update.effective_user.id
    checked_by = update.effective_user.username or update.effective_user.first_name or "Unknown_User"
    if len(context.args) != 1:
        await send_timed_reply(update, "Usage: .all ")
        return
    try:
        card_number, mm, yy, cvv = context.args[0].split('|')
    except:
        await send_timed_reply(update, "Usage: .all ")
        return
    if len(yy) == 4:
        yy = yy[2:]
    if get_credits(user_id) < 6:
        await send_timed_reply(update, insufficient_credits_message())
        return
    bin_data = await bin_lookup(card_number[:6])
    card_info = f"{card_number}|{mm}|{yy}|{cvv}"

    all_auth_outcomes = [
        {"gateway": "Stripe Auth", "status": "Approved ✅", "response": "Payment method added."},
        {"gateway": "Stripe Auth", "status": "Decline ❌", "response": "Card was declined"},
        {"gateway": "Stripe Auth", "status": "Pending ⏳", "response": "Awaiting 3DS authentication"},
        {"gateway": "Stripe Auth", "status": "Captured 💸", "response": "Funds captured successfully"},
        {"gateway": "Stripe Auth", "status": "Refunded ♻️", "response": "Transaction refunded"},
        {"gateway": "Stripe Auth", "status": "Voided 🗑️", "response": "Authorization voided"},
        {"gateway": "Stripe Auth", "status": "Network Error ⚠️", "response": "Provider network error"},
        {"gateway": "Shopify Normal", "status": "OTP_REQUIRED ❎", "response": "OTP Required"},
        {"gateway": "PayPal", "status": "Decline ❌", "response": "Insufficient funds"},
        {"gateway": "PayPal", "status": "Approved ✅", "response": "Transaction completed"},
        {"gateway": "Authorize.Net", "status": "Decline ❌", "response": "Card expired"},
        {"gateway": "Authorize.Net", "status": "Voided 🗑️", "response": "Authorization voided"},
        {"gateway": "CyberSource", "status": "Approved ✅", "response": "Transaction approved"},
        {"gateway": "CyberSource", "status": "Refunded ♻️", "response": "Refund processed"},
        {"gateway": "Razorpay", "status": "Decline ❌", "response": "Bank declined transaction"},
        {"gateway": "Razorpay", "status": "Pending ⏳", "response": "Awaiting bank response"},
        {"gateway": "Braintree", "status": "Approved ✅", "response": "Funds captured successfully"},
        {"gateway": "Worldpay", "status": "Pending ⏳", "response": "Awaiting bank response"},
        {"gateway": "Adyen", "status": "Decline ❌", "response": "Suspected fraud"},
        {"gateway": "Adyen", "status": "Approved ✅", "response": "Payment authorized"},
        {"gateway": "Mock Provider", "status": "Failed ❌", "response": "Provider network error"},
        {"gateway": "Mock Provider", "status": "Succeed ✅", "response": "Authorization succeeded"},
        {"gateway": "Mock Provider", "status": "Reversed 🔄", "response": "Transaction reversed"},
    ]

    # Get a deterministic, but random-looking, subset of outcomes for this card
    outcomes_to_show = get_deterministic_outcomes(card_number, all_auth_outcomes)

    outputs = []
    for outcome in outcomes_to_show:
        outputs.append(
            format_output(
                card_info,
                "UNKNOWN",
                outcome["gateway"],
                outcome["status"],
                outcome["response"],
                bin_data,
                checked_by
            )
        )

    change_credits(user_id, -6)
    for chunk in [outputs[i:i+2] for i in range(0, len(outputs), 2)]:
        await send_timed_reply(update, "\n\n".join(chunk))

async def cmd_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    uid = str(update.effective_user.id)
    role = user_data.get(uid, {}).get("role", "free")
    if role != "premium" and update.effective_user.id != ADMIN_ID:
        await send_timed_reply(update, "❌ This is a premium command. \nContact admin to get premium access.")
        return

    if len(context.args) != 1:
        await send_timed_reply(update, "Usage: .gen <6-digit BIN>")
        return

    bin_number = context.args[0]
    if len(bin_number) != 6 or not bin_number.isdigit():
        await send_timed_reply(update, "Invalid BIN. Must be 6 digits.")
        return

    user = update.effective_user
    username = user.username or user.first_name or "Unknown_User"

    bin_data = await bin_lookup(bin_number)
    info = bin_data.get("info", "N/A")
    bank = bin_data.get("bank", "N/A")
    country = bin_data.get("country", "N/A")

    count = 10
    cards = []
    for _ in range(count):
        card = generate_card(bin_number)
        mm = str(random.randint(1, 12)).zfill(2)
        yy = str(random.randint(23, 30))
        cvv = str(random.randint(100, 999))
        cards.append(f"{card}|{mm}|20{yy}|{cvv}")

    t_time = round(random.uniform(1, 3), 2)
    header = (
        f"Bin : {bin_number}\n"
        f"VBV : True\n"
        f"Amount : {count}\n"
        f"Info : {info}\n"
        f"Bank : {bank}\n"
        f"Country : {country}\n"
        f"━━━━━━━━━━━━━\n"
        f"Time : {t_time} sec\n"
        f"Req By : users @{username}\n"
        f"━━━━━━━━━━━━━\n"
        f"Tap any card to copy ??"
    )

    await send_timed_reply(update, header)
    # Send each card as a separate monospaced message (tap to copy)
    for card in cards:
        msg = await update.message.reply_text(f"`{card}`", parse_mode="Markdown")
        asyncio.create_task(delete_after_delay(msg, 300, update))

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    uid = str(update.effective_user.id)
    role = user_data.get(uid, {}).get("role", "free")
    if role != "premium" and update.effective_user.id != ADMIN_ID:
        await send_timed_reply(update, "❌ This is a premium command.\nContact admin to get premium access.")
        return

    if len(context.args) != 1:
        await send_timed_reply(update, "Usage: .bin <6-digit BIN>")
        return

    bin_number = context.args[0]
    if len(bin_number) != 6 or not bin_number.isdigit():
        await send_timed_reply(update, "Invalid BIN. Must be 6 digits.")
        return

    user = update.effective_user
    username = user.username or user.first_name or "Unknown_User"

    bin_data = await bin_lookup(bin_number)
    info = bin_data.get("info", "N/A")
    bank = bin_data.get("bank", "N/A")
    country = bin_data.get("country", "N/A")

    count = 10
    cards = []
    for _ in range(count):
        card = generate_card(bin_number)
        expiry = fake.credit_card_expire()  # Format MM/YY
        mm, yy = expiry.split('/')
        cvv = str(random.randint(100, 999))
        cards.append(f"{card}|{mm}|{yy}|{cvv}")

    t_time = round(random.uniform(1, 3), 2)
    header = (
        f"Bin : {bin_number}\n"
        f"VBV : True\n"
        f"Amount : {count}\n"
        f"Info : {info}\n"
        f"Bank : {bank}\n"
        f"Country : {country}\n"
        f"━━━━━━━━━━━━━\n"
        f"Time : {t_time} sec\n"
        f"Req By : users @{username}\n"
        f"━━━━━━━━━━━━━\n"
        f"Tap any card to copy ??"
    )

    await send_timed_reply(update, header)
    for card in cards:
        msg = await update.message.reply_text(f"`{card}`", parse_mode="Markdown")
        asyncio.create_task(delete_after_delay(msg, 300, update))

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name or "N/A"
    credits = get_credits(user_id)
    uid = str(user_id)
    role = user_data.get(uid, {}).get("role", "free").upper()
    info_text = f"""OxEnv | {user_id} Info

━━━━━━━━━━━━━━

[ϟ] First Name : {user.first_name}

[ϟ] ID : {user_id}

[ϟ] Username : @{username}

[ϟ] Profile Link : tg://user?id={user_id}

[ϟ] TG Restrictions : False

[ϟ] TG Scamtag : False

[ϟ] TG Premium : False

[ϟ] Status : {role}

[ϟ] Credit : {credits}

[ϟ] Plan : {'N/A' if role == 'FREE' else 'Premium'}

"""
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 View Plans", callback_data="show_plans")]
    ])
    msg = await update.message.reply_text(info_text, reply_markup=buttons)
    asyncio.create_task(delete_after_delay(msg, 300, context))

async def cmd_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await show_plans(update, context)

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans_text = """
💎 PREMIUM ACCESS PLANS 💳
━━━━━━━━━━━━━━
• ₹20 → 100 credits
• ₹50 → 250 credits
• ₹100 → 1000 credits
• ₹200 → Unlimited credits
━━━━━━━━━━━━━━
🔗 Contact: @Sanjai10_oct_2k03 to upgrade your plan.
"""
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(plans_text)
    else:
        await send_timed_reply(update, plans_text)

async def cmd_setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) != 2:
        await send_timed_reply(update, "Usage: .setrole <user_id> <role>")
        return
    user_id, role = context.args
    if role not in ['free', 'premium']:
        await send_timed_reply(update, "Role must be 'free' or 'premium'.")
        return
    uid = str(user_id)
    if uid not in user_data:
        user_data[uid] = {"credits": 0, "last_daily": 0}
    user_data[uid]["role"] = role
    save_user_data(user_data)
    await send_timed_reply(update, f"✅ Role for user {user_id} set to {role}.")

async def dot_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    if not update.message.text.startswith('.'):
        return
    parts = update.message.text[1:].split()
    command, context.args = parts[0], parts[1:]
    commands = {
        "chk": cmd_chk,
        "vbv": cmd_vbv,
        "mass": cmd_mass,
        "all": cmd_all,
        "slf": cmd_slf,
        "daily": cmd_daily,
        "info": cmd_info,
        "plans": cmd_plans,
        "help": cmd_help,
        "cr": cmd_cr,
        "gen": cmd_gen,
        "bin": cmd_bin,
        "setrole": cmd_setrole,
        "fake": cmd_fake,
    }
    handler = commands.get(command.lower())
    if handler:
        await handler(update, context)

async def on_user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        uid = str(member.id)
        if uid not in user_data:
            user_data[uid] = {"credits": 5, "last_daily": 0}
        save_user_data(user_data)
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Welcome {member.full_name}! You have been awarded 5 free credits to start."
        )
        asyncio.create_task(delete_after_delay(msg, 300, context))

async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if result.new_chat_member.status == ChatMember.MEMBER and result.chat.id == ALLOWED_CHAT_ID:
        msg = await context.bot.send_message(
            chat_id=result.chat.id,
            text=f"Welcome {result.new_chat_member.user.full_name} to the group!"
        )
        asyncio.create_task(delete_after_delay(msg, 300, context))
    elif result.old_chat_member.status == ChatMember.MEMBER and result.new_chat_member.status in ['left', 'kicked']:
        msg = await context.bot.send_message(
            chat_id=result.chat.id,
            text=f"Goodbye {result.old_chat_member.user.full_name}."
        )
        asyncio.create_task(delete_after_delay(msg, 300, context))

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS & filters.Chat(ALLOWED_CHAT_ID), on_user_join))
    app.add_handler(MessageHandler(filters.TEXT & filters.Chat(ALLOWED_CHAT_ID), dot_commands))
    app.add_handler(CommandHandler("cr", cmd_cr))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("gen", cmd_gen))
    app.add_handler(CommandHandler("bin", cmd_bin))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("plans", cmd_plans))
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(show_plans, pattern="^show_plans$"))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    print("Bot started...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except RuntimeError:
        pass
