"""
Koval Bot - Telegram Group Bot (50 commands)
Install:  pip install "python-telegram-bot[job-queue]" httpx
Run:      BOT_TOKEN=xxxx python koval_bot.py
Optional: ANTHROPIC_API_KEY=xxxx  (សម្រាប់ /ask, /summary និងជជែកឆ្លាតវៃ)
"""
import ast
import datetime as dt
import json
import operator
import os
import random
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import httpx
from telegram import ChatPermissions, Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
AI_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-5-5")
TZ = ZoneInfo("Asia/Phnom_Penh")
DATA_FILE = "koval_data.json"

SYSTEM = ("អ្នកគឺជា Bot ឈ្មោះ Koval ក្នុង Telegram Group។ ឆ្លើយជាភាសាខ្មែរ (ឬតាមភាសាដែលគេប្រើ) "
          "ស្និទ្ធស្នាល ខ្លី មិនលើស ៥ ប្រយោគ ប្រើ emoji សមរម្យ មិនប្រើពាក្យអសុរស។")

# ---------------------------------------------------------------- storage
try:
    with open(DATA_FILE, encoding="utf-8") as f:
        DATA = json.load(f)
except Exception:
    DATA = {}
for k in ("rules", "welcome", "scores", "stats", "warns", "birthdays", "daily"):
    DATA.setdefault(k, {})
HISTORY = {}  # chat_id -> last messages (in memory)


def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False)


# ---------------------------------------------------------------- helpers
async def get_json(url, **params):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        r = await c.get(url, params=params, headers={"User-Agent": "KovalBot/1.0"})
        r.raise_for_status()
        return r.json()


async def get_text(url):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        r = await c.get(url, headers={"User-Agent": "KovalBot/1.0"})
        r.raise_for_status()
        return r.text


async def ai(prompt, system=SYSTEM):
    if not AI_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": AI_KEY, "anthropic-version": "2023-06-01"},
                json={"model": AI_MODEL, "max_tokens": 700, "system": system,
                      "messages": [{"role": "user", "content": prompt}]})
            return r.json()["content"][0]["text"]
    except Exception:
        return None


async def is_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat, user = update.effective_chat, update.effective_user
    if chat.type == "private":
        return True
    m = await ctx.bot.get_chat_member(chat.id, user.id)
    return m.status in ("administrator", "creator")


def args_text(ctx):
    return " ".join(ctx.args).strip()


async def rss(url, n=5):
    root = ET.fromstring(await get_text(url))
    items = root.findall(".//item")[:n]
    return [(i.findtext("title", ""), i.findtext("link", "")) for i in items]


def add_score(chat_id, user, pts=1):
    s = DATA["scores"].setdefault(str(chat_id), {}).setdefault(
        str(user.id), {"name": user.first_name, "pts": 0})
    s["pts"] += pts
    s["name"] = user.first_name
    save()


# ---------------------------------------------------------------- content
JOKES = ["ហេតុអ្វីកុំព្យូទ័រមិនឃ្លាន? ព្រោះវាមាន Byte ជានិច្ច 😄",
         "គ្រូសួរ៖ បើអ្នកមាន ១០ ដុល្លារ ហើយខ្ចីខ្ញុំ ៥ ដុល្លារ អ្នកនៅសល់ប៉ុន្មាន? សិស្ស៖ ១០ ដុល្លារ លោកគ្រូ! 🤣",
         "ម្តាយសួរ៖ ហេតុអ្វីមិនរៀន? កូន៖ ព្រោះខ្ញុំខ្លាចចេះច្រើនជាងគ្រូ 😎",
         "ហេតុអ្វីទូរស័ព្ទទៅពេទ្យ? ព្រោះវាមាន Virus 🤒📱"]
RIDDLES = [("អ្វីដែលដើរមិនមានជើង ហើយយំមិនមានភ្នែក?", "ពពក"),
           ("អ្វីដែលកាន់តែយកចេញកាន់តែធំ?", "រណ្តៅ"),
           ("អ្វីដែលមានមាត់តែមិនញ៉ាំ មានគ្រែតែមិនដេក?", "ទន្លេ"),
           ("អ្វីដែលមានមួយក្បាលពីរភ្នែក?", "ម្ជុល")]
QUOTES = ["ជោគជ័យចាប់ផ្តើមពីជំហានតូចមួយ 🚶", "កុំបោះបង់ ព្រោះថ្ងៃស្អែកអាចជាថ្ងៃដ៏ល្អ ☀️",
          "ការខិតខំជាមេរៀនល្អជាងគេ 💪", "អ្នកដែលរៀនមិនដែលចាញ់ 📚",
          "ធ្លាក់ប្រាំពីរដង ក្រោកប្រាំបីដង 🔥"]
ROASTS = ["{n} ងងុយដេកជាងឆ្មាទៀត 😹", "{n} ឆាត់ម៉ោងលឿនជាង Wi-Fi ទៀត 🤭",
          "{n} ចូលចិត្តសន្យា ប៉ុន្តែយឺតជាងអណ្តើក 🐢"]
COMPLIMENTS = ["{n} ជាមនុស្សដ៏អស្ចារ្យ! 🌟", "{n} ញញឹមស្រស់ណាស់ 😊",
               "{n} ជាអ្នកដែលធ្វើឱ្យក្រុមកាន់តែសប្បាយ 🎉", "{n} ឆ្លាតខ្លាំងណាស់ 🧠"]
TRUTHS = ["អ្វីដែលអ្នកខ្មាសជាងគេ?", "មនុស្សដំបូងដែលអ្នកស្រលាញ់ជានរណា?",
          "កុហកធំបំផុតដែលអ្នកធ្លាប់និយាយ?", "ចំណូលចិត្តសម្ងាត់របស់អ្នកគឺអ្វី?"]
DARES = ["ផ្ញើសារសំឡេងច្រៀងចម្រៀង ១ ឃ្លា 🎤", "ដូរ Profile ជារូបកំប្លែង ១ ម៉ោង 🤡",
         "សរសើរមនុស្សម្នាក់ក្នុងក្រុម ៣ ឃ្លា 💬", "ផ្ញើ Sticker ដែលអ្នកចូលចិត្តបំផុត 😆"]
WOULDYOU = ["ជ្រើសរើស៖ មានលុយច្រើនតែគ្មានមិត្ត 💰 ឬ មានមិត្តច្រើនតែគ្មានលុយ 👫?",
            "ជ្រើសរើស៖ ហោះបាន ✈️ ឬ មើលមិនឃើញខ្លួន 👻?",
            "ជ្រើសរើស៖ ញ៉ាំតែមីមួយជីវិត 🍜 ឬ ញ៉ាំតែបាយមួយជីវិត 🍚?"]
FACTS = ["ទឹកឃ្មុំមិនដែលខូចទេ 🍯", "ត្រីមឹកមាន ៣ បេះដូង 🐙",
         "ប្រាសាទអង្គរវត្តជាសំណង់សាសនាធំបំផុតលើពិភពលោក 🛕",
         "ផ្កាយ Venus វិលបញ្ច្រាសទិសនឹងភពភាគច្រើន 🪐"]
QUIZ = [("រាជធានីនៃកម្ពុជាឈ្មោះអ្វី?", "ភ្នំពេញ"),
        ("១២ x ១២ ស្មើប៉ុន្មាន?", "144"),
        ("ទន្លេធំបំផុតក្នុងកម្ពុជាឈ្មោះអ្វី?", "មេគង្គ"),
        ("សប្តាហ៍មានប៉ុន្មានថ្ងៃ?", "7"),
        ("ភពណាជិតព្រះអាទិត្យជាងគេ?", "ពុធ")]
WORDS = ["python", "telegram", "cambodia", "angkor", "friend", "computer", "monkey", "rainbow"]
TZ_ALIAS = {"cambodia": "Asia/Phnom_Penh", "thailand": "Asia/Bangkok", "japan": "Asia/Tokyo",
            "china": "Asia/Shanghai", "korea": "Asia/Seoul", "usa": "America/New_York",
            "uk": "Europe/London", "france": "Europe/Paris", "australia": "Australia/Sydney"}
WX = {0: "ថ្លា ☀️", 1: "ភាគច្រើនថ្លា 🌤", 2: "មានពពកខ្លះ ⛅", 3: "ស្រទាប់ពពក ☁️", 45: "អ័ព្ទ 🌫",
      51: "ភ្លៀងរលឹម 🌦", 61: "ភ្លៀង 🌧", 63: "ភ្លៀងខ្លាំង 🌧", 80: "ភ្លៀងស្រោច 🌦", 95: "ផ្គររន្ទះ ⛈"}
HOLIDAYS_KH = {"01-01": "ទិវាចូលឆ្នាំសកល", "01-07": "ទិវាជ័យជម្នះលើរបបប្រល័យពូជសាសន៍",
               "03-08": "ទិវានារីអន្តរជាតិ", "05-01": "ទិវាពលកម្មអន្តរជាតិ",
               "06-18": "ព្រះពិសាខបូជា (ព្រះរាជសម្ភពព្រះមហាក្សត្រិយានី)",
               "09-24": "ទិវារដ្ឋធម្មនុញ្ញ", "10-29": "ព្រះរាជពិធីគ្រងរាជ្យ",
               "11-09": "ទិវាបុណ្យឯករាជ្យជាតិ", "12-10": "ទិវាសិទ្ធិមនុស្ស"}


# ---------------------------------------------------------------- [1] chat fun
async def hello(u, c):
    await u.message.reply_text(f"សួស្តី {u.effective_user.first_name}! 👋 ខ្ញុំគឺ Koval សូមស្វាគមន៍ 🎉")


async def joke(u, c): await u.message.reply_text(random.choice(JOKES))
async def quote(u, c): await u.message.reply_text(random.choice(QUOTES))
async def fact(u, c): await u.message.reply_text("💡 " + random.choice(FACTS))
async def truth(u, c): await u.message.reply_text("🫣 Truth: " + random.choice(TRUTHS))
async def dare(u, c): await u.message.reply_text("😈 Dare: " + random.choice(DARES))
async def wouldyou(u, c): await u.message.reply_text("🤔 " + random.choice(WOULDYOU))


def target_name(u):
    r = u.message.reply_to_message
    return (r.from_user.first_name if r else u.effective_user.first_name)


async def roast(u, c): await u.message.reply_text(random.choice(ROASTS).format(n=target_name(u)))
async def compliment(u, c): await u.message.reply_text(random.choice(COMPLIMENTS).format(n=target_name(u)))


async def riddle(u, c):
    q, a = random.choice(RIDDLES)
    c.chat_data["answer"] = (a, "riddle")
    await u.message.reply_text(f"🧩 {q}\n(ឆ្លើយក្នុងក្រុមបាន!)")


# ---------------------------------------------------------------- [2] daily info
async def news(u, c):
    try:
        items = await rss("https://feeds.bbci.co.uk/news/world/rss.xml")
        await u.message.reply_text("📰 ព័ត៌មានថ្ងៃនេះ (BBC)\n\n" + "\n\n".join(f"• {t}\n{l}" for t, l in items),
                                   disable_web_page_preview=True)
    except Exception:
        await u.message.reply_text("មិនអាចទាញព័ត៌មានបានទេ 😢")


async def tech(u, c):
    try:
        items = await rss("https://feeds.bbci.co.uk/news/technology/rss.xml")
        await u.message.reply_text("💻 បច្ចេកវិទ្យា\n\n" + "\n\n".join(f"• {t}\n{l}" for t, l in items),
                                   disable_web_page_preview=True)
    except Exception:
        await u.message.reply_text("មិនអាចទាញព័ត៌មានបានទេ 😢")


async def sport(u, c):
    try:
        items = await rss("https://feeds.bbci.co.uk/sport/rss.xml")
        await u.message.reply_text("⚽ កីឡា\n\n" + "\n\n".join(f"• {t}\n{l}" for t, l in items),
                                   disable_web_page_preview=True)
    except Exception:
        await u.message.reply_text("មិនអាចទាញព័ត៌មានកីឡាបានទេ 😢")


async def weather_text(city="Phnom Penh"):
    g = await get_json("https://geocoding-api.open-meteo.com/v1/search", name=city, count=1)
    if not g.get("results"):
        return "រកមិនឃើញទីក្រុងនេះទេ"
    p = g["results"][0]
    w = await get_json("https://api.open-meteo.com/v1/forecast", latitude=p["latitude"],
                       longitude=p["longitude"], timezone="auto",
                       current="temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                       daily="temperature_2m_max,temperature_2m_min,precipitation_probability_max")
    cur, d = w["current"], w["daily"]
    return (f"🌤 អាកាសធាតុ {p['name']}\n{WX.get(cur['weather_code'], 'មិនស្គាល់')}\n"
            f"🌡 {cur['temperature_2m']}°C (ខ្ពស់ {d['temperature_2m_max'][0]}° / ទាប {d['temperature_2m_min'][0]}°)\n"
            f"💧 សំណើម {cur['relative_humidity_2m']}%  💨 ខ្យល់ {cur['wind_speed_10m']} km/h\n"
            f"☔ ឱកាសភ្លៀង {d['precipitation_probability_max'][0]}%")


async def weather(u, c):
    try:
        await u.message.reply_text(await weather_text(args_text(c) or "Phnom Penh"))
    except Exception:
        await u.message.reply_text("មិនអាចទាញអាកាសធាតុបានទេ 😢")


async def exchange(u, c):
    try:
        r = (await get_json("https://open.er-api.com/v6/latest/USD"))["rates"]
        lines = [f"1 USD = {r[k]:,.2f} {k}" for k in ("KHR", "THB", "VND", "EUR", "JPY", "CNY", "GBP")]
        await u.message.reply_text("💱 អត្រាប្តូរប្រាក់\n" + "\n".join(lines))
    except Exception:
        await u.message.reply_text("មិនអាចទាញអត្រាប្តូរប្រាក់បានទេ 😢")


async def gold(u, c):
    try:
        d = await get_json("https://api.coingecko.com/api/v3/simple/price",
                           ids="pax-gold", vs_currencies="usd")
        usd = d["pax-gold"]["usd"]
        await u.message.reply_text(f"🥇 មាស ≈ ${usd:,.2f} / ounce\n(បានមកពី PAXG ជាតម្លៃប្រហាក់ប្រហែល)")
    except Exception:
        await u.message.reply_text("មិនអាចទាញតម្លៃមាសបានទេ 😢")


async def crypto(u, c):
    try:
        ids = "bitcoin,ethereum,binancecoin,solana,ripple"
        d = await get_json("https://api.coingecko.com/api/v3/simple/price", ids=ids,
                           vs_currencies="usd", include_24hr_change="true")
        lines = [f"{k.title()}: ${v['usd']:,.2f} ({v['usd_24h_change']:+.1f}%)" for k, v in d.items()]
        await u.message.reply_text("🪙 Crypto\n" + "\n".join(lines))
    except Exception:
        await u.message.reply_text("មិនអាចទាញតម្លៃ Crypto បានទេ 😢")


async def today(u, c):
    try:
        n = dt.datetime.now(TZ)
        d = await get_json(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{n.month:02d}/{n.day:02d}")
        e = random.choice(d["events"])
        await u.message.reply_text(f"📜 ថ្ងៃនេះក្នុងប្រវត្តិសាស្ត្រ\n{e['year']}: {e['text']}")
    except Exception:
        await u.message.reply_text("មិនអាចទាញប្រវត្តិសាស្ត្របានទេ 😢")


async def holiday(u, c):
    n = dt.datetime.now(TZ)
    up = sorted((k, v) for k, v in HOLIDAYS_KH.items() if k >= n.strftime("%m-%d"))
    up = up[:3] or sorted(HOLIDAYS_KH.items())[:3]
    await u.message.reply_text("🎌 ថ្ងៃបុណ្យជិតមកដល់\n" + "\n".join(f"• {k}: {v}" for k, v in up))


async def trend(u, c):
    try:
        y = dt.datetime.now(TZ) - dt.timedelta(days=1)
        d = await get_json("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/"
                           f"all-access/{y.year}/{y.month:02d}/{y.day:02d}")
        arts = [a["article"].replace("_", " ") for a in d["items"][0]["articles"]
                if not a["article"].startswith(("Main_Page", "Special:", "Wikipedia:"))][:7]
        await u.message.reply_text("🔥 កំពុងពេញនិយម (Wikipedia)\n" + "\n".join(f"{i+1}. {a}" for i, a in enumerate(arts)))
    except Exception:
        await u.message.reply_text("មិនអាចទាញប្រធានបទពេញនិយមបានទេ 😢")


# ---------------------------------------------------------------- [3] games
async def quiz(u, c):
    q, a = random.choice(QUIZ)
    c.chat_data["answer"] = (a, "quiz")
    await u.message.reply_text(f"❓ Quiz: {q}")


async def guess(u, c):
    if not c.args or not c.args[0].isdigit():
        c.chat_data["secret"] = random.randint(1, 100)
        return await u.message.reply_text("🎯 ខ្ញុំគិតលេខ ១-១០០ ហើយ! វាយ /guess <លេខ>")
    if "secret" not in c.chat_data:
        c.chat_data["secret"] = random.randint(1, 100)
    g, s = int(c.args[0]), c.chat_data["secret"]
    if g == s:
        add_score(u.effective_chat.id, u.effective_user, 3)
        c.chat_data.pop("secret")
        await u.message.reply_text(f"🎉 ត្រូវហើយ! លេខគឺ {s} (+3 ពិន្ទុ)")
    else:
        await u.message.reply_text("⬆️ ធំជាងនេះ" if g < s else "⬇️ តូចជាងនេះ")


async def dice(u, c): await u.message.reply_dice()
async def coin(u, c): await u.message.reply_text(random.choice(["🪙 ក្បាល", "🪙 កន្ទុយ"]))


async def rps(u, c):
    m = {"rock": "ថ្ម", "paper": "ក្រដាស", "scissors": "កន្ត្រៃ", "ថ្ម": "ថ្ម", "ក្រដាស": "ក្រដាស", "កន្ត្រៃ": "កន្ត្រៃ"}
    me = m.get(args_text(c).lower())
    if not me:
        return await u.message.reply_text("ប្រើ /rps ថ្ម | កន្ត្រៃ | ក្រដាស")
    bot = random.choice(["ថ្ម", "ក្រដាស", "កន្ត្រៃ"])
    win = {("ថ្ម", "កន្ត្រៃ"), ("កន្ត្រៃ", "ក្រដាស"), ("ក្រដាស", "ថ្ម")}
    if me == bot:
        res = "ស្មើគ្នា 🤝"
    elif (me, bot) in win:
        res = "អ្នកឈ្នះ! 🎉"
        add_score(u.effective_chat.id, u.effective_user)
    else:
        res = "Koval ឈ្នះ 😎"
    await u.message.reply_text(f"អ្នក: {me} | Koval: {bot}\n{res}")


async def wordgame(u, c):
    w = random.choice(WORDS)
    s = "".join(random.sample(w, len(w)))
    c.chat_data["answer"] = (w, "word")
    await u.message.reply_text(f"🔤 តម្រៀបអក្សរឱ្យត្រូវ: {s}")


async def math_game(u, c):
    a, b = random.randint(10, 99), random.randint(2, 20)
    op = random.choice(["+", "-", "x"])
    r = a + b if op == "+" else a - b if op == "-" else a * b
    c.chat_data["answer"] = (str(r), "math")
    await u.message.reply_text(f"🧮 {a} {op} {b} = ?")


async def story(u, c):
    st = c.chat_data.setdefault("story", [])
    t = args_text(c)
    if t == "reset":
        st.clear()
        return await u.message.reply_text("🗑 លុបរឿងហើយ")
    if t:
        st.append(t)
    await u.message.reply_text("📖 " + (" ".join(st) if st else "រឿងនៅទទេ! វាយ /story <ប្រយោគ> ដើម្បីចាប់ផ្តើម"))


async def poll(u, c):
    parts = [p.strip() for p in args_text(c).split("|") if p.strip()]
    if len(parts) < 3:
        return await u.message.reply_text("ប្រើ: /poll សំណួរ | ជម្រើស១ | ជម្រើស២")
    await u.effective_chat.send_poll(parts[0], parts[1:10], is_anonymous=False)


async def rank(u, c):
    s = DATA["scores"].get(str(u.effective_chat.id), {})
    top = sorted(s.values(), key=lambda x: -x["pts"])[:10]
    if not top:
        return await u.message.reply_text("មិនទាន់មានពិន្ទុទេ! សាកលេង /quiz /math 🎮")
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    await u.message.reply_text("🏆 ចំណាត់ថ្នាក់\n" + "\n".join(f"{medals[i]} {x['name']}: {x['pts']}" for i, x in enumerate(top)))


# ---------------------------------------------------------------- [4] tools
async def translate(u, c):
    t = args_text(c) or (u.message.reply_to_message.text if u.message.reply_to_message else "")
    if not t:
        return await u.message.reply_text("ប្រើ /translate <អត្ថបទ> (ឬ reply សារ)")
    pair = "km|en" if any("\u1780" <= ch <= "\u17ff" for ch in t) else "en|km"
    try:
        d = await get_json("https://api.mymemory.translated.net/get", q=t, langpair=pair)
        await u.message.reply_text("🌐 " + d["responseData"]["translatedText"])
    except Exception:
        await u.message.reply_text("បកប្រែមិនបានទេ 😢")


async def define(u, c):
    w = args_text(c)
    if not w:
        return await u.message.reply_text("ប្រើ /define <word>")
    try:
        d = await get_json(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}")
        m = d[0]["meanings"][0]
        await u.message.reply_text(f"📘 {w} ({m['partOfSpeech']})\n{m['definitions'][0]['definition']}")
    except Exception:
        await u.message.reply_text("រកមិនឃើញន័យពាក្យនេះទេ")


OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.Mod: operator.mod}


def safe_eval(n):
    if isinstance(n, ast.Expression):
        return safe_eval(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in OPS:
        l, r = safe_eval(n.left), safe_eval(n.right)
        if isinstance(n.op, ast.Pow) and abs(r) > 100:
            raise ValueError
        return OPS[type(n.op)](l, r)
    if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
        return OPS[type(n.op)](safe_eval(n.operand))
    raise ValueError


async def calc(u, c):
    try:
        r = safe_eval(ast.parse(args_text(c).replace("x", "*").replace("^", "**"), mode="eval"))
        await u.message.reply_text(f"🧮 = {r:,}")
    except Exception:
        await u.message.reply_text("ប្រើ /calc 12*(3+4)")


async def convert(u, c):
    try:
        v, a, b = float(c.args[0]), c.args[1].upper(), c.args[2].upper()
        units = {("KM", "MI"): 0.621371, ("MI", "KM"): 1.609344, ("KG", "LB"): 2.204623,
                 ("LB", "KG"): 0.453592, ("M", "FT"): 3.28084, ("FT", "M"): 0.3048}
        if (a, b) in units:
            return await u.message.reply_text(f"📐 {v} {a} = {v * units[(a, b)]:.2f} {b}")
        if (a, b) == ("C", "F"):
            return await u.message.reply_text(f"🌡 {v}°C = {v * 9 / 5 + 32:.1f}°F")
        if (a, b) == ("F", "C"):
            return await u.message.reply_text(f"🌡 {v}°F = {(v - 32) * 5 / 9:.1f}°C")
        r = (await get_json(f"https://open.er-api.com/v6/latest/{a}"))["rates"][b]
        await u.message.reply_text(f"💱 {v:,} {a} = {v * r:,.2f} {b}")
    except Exception:
        await u.message.reply_text("ប្រើ /convert 10 USD KHR  ឬ  /convert 5 km mi")


async def _fire(ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(ctx.job.chat_id, ctx.job.data)


async def remind(u, c):
    try:
        mins = float(c.args[0])
        text = " ".join(c.args[1:]) or "ដល់ពេលហើយ!"
        c.job_queue.run_once(_fire, mins * 60, chat_id=u.effective_chat.id,
                             data=f"⏰ {u.effective_user.first_name}: {text}")
        await u.message.reply_text(f"✅ នឹងរំលឹកក្នុង {mins:g} នាទី")
    except Exception:
        await u.message.reply_text("ប្រើ /remind <នាទី> <អត្ថបទ>")


async def timer(u, c):
    try:
        s = int(c.args[0])
        c.job_queue.run_once(_fire, s, chat_id=u.effective_chat.id, data="⏳ អស់ម៉ោងហើយ! 🔔")
        await u.message.reply_text(f"⏳ ចាប់ផ្តើមរាប់ថយក្រោយ {s} វិនាទី")
    except Exception:
        await u.message.reply_text("ប្រើ /timer <វិនាទី>")


async def time_cmd(u, c):
    name = args_text(c).lower().replace(" ", "_") or "cambodia"
    try:
        z = ZoneInfo(TZ_ALIAS.get(name, args_text(c) or "Asia/Phnom_Penh"))
        await u.message.reply_text(f"🕒 {dt.datetime.now(z):%Y-%m-%d %H:%M:%S} ({z.key})")
    except Exception:
        await u.message.reply_text("ប្រើ /time cambodia | japan | usa | Europe/London")


async def summary(u, c):
    h = HISTORY.get(u.effective_chat.id, [])
    if len(h) < 5:
        return await u.message.reply_text("សារមិនទាន់គ្រប់គ្រាន់សម្រាប់សង្ខេប")
    r = await ai("សង្ខេបការសន្ទនានេះជា ៣-៥ ចំណុច:\n" + "\n".join(h[-60:]))
    await u.message.reply_text(r or f"📝 មានសារ {len(h)} ក្នុងអង្គចងចាំ (ត្រូវការ ANTHROPIC_API_KEY ដើម្បីសង្ខេប)")


async def search(u, c):
    q = args_text(c)
    if not q:
        return await u.message.reply_text("ប្រើ /search <ពាក្យ>")
    try:
        d = await get_json("https://en.wikipedia.org/w/api.php", action="query", list="search",
                           srsearch=q, format="json", srlimit=3)
        out = [f"• {r['title']}\nhttps://en.wikipedia.org/wiki/{r['title'].replace(' ', '_')}"
               for r in d["query"]["search"]]
        await u.message.reply_text("🔎 លទ្ធផល\n" + ("\n".join(out) or "រកមិនឃើញ"), disable_web_page_preview=True)
    except Exception:
        await u.message.reply_text("ស្វែងរកមិនបានទេ 😢")


async def ask(u, c):
    q = args_text(c) or (u.message.reply_to_message.text if u.message.reply_to_message else "")
    if not q:
        return await u.message.reply_text("ប្រើ /ask <សំណួរ>")
    await u.effective_chat.send_action("typing")
    r = await ai(q)
    await u.message.reply_text(r or "🤖 ត្រូវការ ANTHROPIC_API_KEY ដើម្បីប្រើ /ask")


# ---------------------------------------------------------------- [5] group mgmt
async def rules(u, c):
    cid = str(u.effective_chat.id)
    if c.args and await is_admin(u, c):
        DATA["rules"][cid] = args_text(c)
        save()
        return await u.message.reply_text("✅ បានកំណត់ច្បាប់ក្រុម")
    await u.message.reply_text("📜 ច្បាប់ក្រុម\n" + DATA["rules"].get(
        cid, "១. គោរពគ្នា\n២. មិនផ្សាយមិនពិត\n៣. មិន Spam\n(admin: /rules <អត្ថបទ> ដើម្បីកែ)"))


async def welcome(u, c):
    if c.args and await is_admin(u, c):
        DATA["welcome"][str(u.effective_chat.id)] = args_text(c)
        save()
        return await u.message.reply_text("✅ បានកំណត់សារស្វាគមន៍ (ប្រើ {name} ជាឈ្មោះ)")
    await u.message.reply_text(DATA["welcome"].get(str(u.effective_chat.id), "សារ: សូមស្វាគមន៍ {name}! 🎉"))


async def on_new_member(u, c):
    t = DATA["welcome"].get(str(u.effective_chat.id), "សូមស្វាគមន៍ {name} មកកាន់ក្រុម! 🎉 វាយ /rules មើលច្បាប់")
    for m in u.message.new_chat_members:
        if not m.is_bot:
            await u.message.reply_text(t.replace("{name}", m.first_name))


async def birthday(u, c):
    cid = str(u.effective_chat.id)
    b = DATA["birthdays"].setdefault(cid, {})
    if c.args:
        try:
            d, m = args_text(c).split("-")
            dt.date(2000, int(m), int(d))
            b[str(u.effective_user.id)] = {"name": u.effective_user.first_name, "date": f"{int(d):02d}-{int(m):02d}"}
            save()
            return await u.message.reply_text("🎂 បានកត់ត្រាថ្ងៃកំណើតរបស់អ្នក!")
        except Exception:
            return await u.message.reply_text("ប្រើ /birthday DD-MM (ឧ. /birthday 15-04)")
    await u.message.reply_text("🎂 ថ្ងៃកំណើតសមាជិក\n" + ("\n".join(f"• {v['name']}: {v['date']}" for v in b.values())
                                                     or "មិនទាន់មាន! វាយ /birthday DD-MM"))


async def admin_list(u, c):
    a = await c.bot.get_chat_administrators(u.effective_chat.id)
    await u.message.reply_text("👮 អ្នកគ្រប់គ្រង\n" + "\n".join(
        f"• {x.user.first_name}" + (f" (@{x.user.username})" if x.user.username else "") for x in a if not x.user.is_bot))


async def report(u, c):
    r = u.message.reply_to_message
    if not r:
        return await u.message.reply_text("Reply សារដែលចង់រាយការណ៍ រួចវាយ /report")
    a = await c.bot.get_chat_administrators(u.effective_chat.id)
    tags = " ".join(f"@{x.user.username}" for x in a if x.user.username and not x.user.is_bot)
    await r.reply_text(f"🚨 សារនេះត្រូវបានរាយការណ៍ {tags}")


async def warn(u, c):
    if not await is_admin(u, c):
        return await u.message.reply_text("⛔ សម្រាប់ admin ប៉ុណ្ណោះ")
    r = u.message.reply_to_message
    if not r:
        return await u.message.reply_text("Reply សមាជិកដែលចង់ព្រមាន")
    k = f"{u.effective_chat.id}:{r.from_user.id}"
    DATA["warns"][k] = DATA["warns"].get(k, 0) + 1
    save()
    n = DATA["warns"][k]
    await u.message.reply_text(f"⚠️ {r.from_user.first_name} ត្រូវបានព្រមាន ({n}/3)")
    if n >= 3:
        DATA["warns"][k] = 0
        await c.bot.restrict_chat_member(u.effective_chat.id, r.from_user.id,
                                         ChatPermissions(can_send_messages=False),
                                         until_date=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1))
        await u.message.reply_text("🔇 បិទសំឡេង ១ ម៉ោង (ព្រមាន ៣ ដង)")


async def mute(u, c):
    if not await is_admin(u, c):
        return await u.message.reply_text("⛔ សម្រាប់ admin ប៉ុណ្ណោះ")
    r = u.message.reply_to_message
    if not r:
        return await u.message.reply_text("Reply សមាជិក រួចវាយ /mute <នាទី>")
    mins = int(c.args[0]) if c.args and c.args[0].isdigit() else 10
    try:
        await c.bot.restrict_chat_member(u.effective_chat.id, r.from_user.id,
                                         ChatPermissions(can_send_messages=False),
                                         until_date=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=mins))
        await u.message.reply_text(f"🔇 {r.from_user.first_name} ត្រូវបានបិទសំឡេង {mins} នាទី")
    except Exception:
        await u.message.reply_text("ធ្វើមិនបាន (Bot ត្រូវតែជា admin)")


async def stats(u, c):
    s = DATA["stats"].get(str(u.effective_chat.id), {})
    top = sorted(s.values(), key=lambda x: -x["n"])[:5]
    total = sum(x["n"] for x in s.values())
    await u.message.reply_text(f"📊 ស្ថិតិក្រុម\nសារសរុប: {total}\nសមាជិកសកម្ម: {len(s)}\n\nTop 5:\n" +
                               "\n".join(f"{i+1}. {x['name']}: {x['n']}" for i, x in enumerate(top)))


async def build_daily(chat_id):
    parts = ["☀️ អរុណសួស្តី! សេចក្តីសង្ខេបប្រចាំថ្ងៃ\n", "💬 " + random.choice(QUOTES)]
    try:
        parts.append("\n" + await weather_text())
    except Exception:
        pass
    try:
        parts.append("\n📰 ព័ត៌មាន\n" + "\n".join(f"• {t}" for t, _ in await rss("https://feeds.bbci.co.uk/news/world/rss.xml", 3)))
    except Exception:
        pass
    today_s = dt.datetime.now(TZ).strftime("%d-%m")
    bd = [v["name"] for v in DATA["birthdays"].get(str(chat_id), {}).values() if v["date"] == today_s]
    if bd:
        parts.append("\n🎂 ជូនពរថ្ងៃកំណើត: " + ", ".join(bd) + " 🎉")
    return "\n".join(parts)


async def daily_job(ctx: ContextTypes.DEFAULT_TYPE):
    for cid in list(DATA["daily"]):
        try:
            await ctx.bot.send_message(int(cid), await build_daily(cid))
        except Exception:
            pass


async def daily(u, c):
    cid = str(u.effective_chat.id)
    a = args_text(c).lower()
    if a in ("on", "off") and await is_admin(u, c):
        if a == "on":
            DATA["daily"][cid] = True
        else:
            DATA["daily"].pop(cid, None)
        save()
        return await u.message.reply_text(f"✅ សេចក្តីសង្ខេបម៉ោង ៨ ព្រឹក: {a.upper()}")
    await u.message.reply_text(await build_daily(cid))


HELP = """🤖 Koval Bot - បញ្ជី Command
😄 ជជែក: /hello /joke /riddle /quote /roast /compliment /truth /dare /wouldyou /fact
📰 ព័ត៌មាន: /news /tech /sport /weather /exchange /gold /crypto /today /holiday /trend
🎮 ល្បែង: /quiz /guess /dice /coin /rps /wordgame /math /story /poll /rank
🛠 ឧបករណ៍: /translate /define /calc /convert /remind /timer /time /summary /search /ask
👥 ក្រុម: /rules /welcome /birthday /admin /report /warn /mute /stats /daily /help"""


async def help_cmd(u, c): await u.message.reply_text(HELP)


# ---------------------------------------------------------------- text handler
async def on_text(u: Update, c: ContextTypes.DEFAULT_TYPE):
    m = u.message
    if not m or not m.text:
        return
    cid, usr = str(u.effective_chat.id), u.effective_user
    # stats + history
    st = DATA["stats"].setdefault(cid, {}).setdefault(str(usr.id), {"name": usr.first_name, "n": 0})
    st["n"] += 1
    st["name"] = usr.first_name
    h = HISTORY.setdefault(u.effective_chat.id, [])
    h.append(f"{usr.first_name}: {m.text}")
    del h[:-200]
    if st["n"] % 20 == 0:
        save()
    # answer checking for quiz/riddle/math/word
    ans = c.chat_data.get("answer")
    if ans and m.text.strip().lower() == ans[0].lower():
        c.chat_data.pop("answer")
        add_score(u.effective_chat.id, usr, 2)
        return await m.reply_text(f"🎉 {usr.first_name} ឆ្លើយត្រូវ! (+2 ពិន្ទុ)")
    # chat when mentioned or replied to
    me = c.bot.username
    replied = m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id == c.bot.id
    if u.effective_chat.type == "private" or f"@{me}".lower() in m.text.lower() or replied:
        q = m.text.replace(f"@{me}", "").strip()
        r = await ai(q)
        await m.reply_text(r or random.choice(["😄 ហ៊ាស! ខ្ញុំនៅទីនេះ វាយ /help មើលអ្វីដែលខ្ញុំអាចធ្វើបាន",
                                               "🤖 ហៅខ្ញុំមែនទេ? សាកវាយ /joke ឬ /quiz មើល!"]))


# ---------------------------------------------------------------- main
COMMANDS = {
    "hello": hello, "joke": joke, "riddle": riddle, "quote": quote, "roast": roast,
    "compliment": compliment, "truth": truth, "dare": dare, "wouldyou": wouldyou, "fact": fact,
    "news": news, "tech": tech, "sport": sport, "weather": weather, "exchange": exchange,
    "gold": gold, "crypto": crypto, "today": today, "holiday": holiday, "trend": trend,
    "quiz": quiz, "guess": guess, "dice": dice, "coin": coin, "rps": rps,
    "wordgame": wordgame, "math": math_game, "story": story, "poll": poll, "rank": rank,
    "translate": translate, "define": define, "calc": calc, "convert": convert, "remind": remind,
    "timer": timer, "time": time_cmd, "summary": summary, "search": search, "ask": ask,
    "rules": rules, "welcome": welcome, "birthday": birthday, "admin": admin_list, "report": report,
    "warn": warn, "mute": mute, "stats": stats, "daily": daily, "help": help_cmd, "start": help_cmd,
}


def main():
    if not BOT_TOKEN:
        raise SystemExit("សូមកំណត់ BOT_TOKEN (export BOT_TOKEN=xxxx)")
    app = Application.builder().token(BOT_TOKEN).build()
    for name, fn in COMMANDS.items():
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.job_queue.run_daily(daily_job, dt.time(8, 0, tzinfo=TZ))
    print("Koval bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
