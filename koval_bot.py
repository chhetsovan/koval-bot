"""
Koval Bot - Telegram Group Bot (50 commands, protected content)
Install:  pip install -r requirements.txt
Run:      BOT_TOKEN=xxxx python koval_bot.py
Optional: ANTHROPIC_API_KEY=xxxx  (សម្រាប់ /ask, /summary និងជជែកឆ្លាតវៃ)
"""
import asyncio
import ast
import csv
import io
import math
import datetime as dt
import json
import operator
import os
import random
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import httpx
from telegram import ChatPermissions, Update
from telegram.ext import (Application, CommandHandler, ContextTypes, Defaults,
                          ExtBot, MessageHandler, filters)

AUTO_DELETE_SECONDS = 3 * 24 * 60 * 60  # លុបសាររបស់ bot បន្ទាប់ពី 3 ថ្ងៃ
NO_DELETE = {"sendPoll"}   # មិនលុប poll ព្រោះលុបហើយ vote ក៏បាត់

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
AI_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
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
HEADERS = {"User-Agent": "KovalBot/1.0"}


async def get_json(url, **params):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        r = await c.get(url, params=params, headers=HEADERS)
        r.raise_for_status()
        return r.json()


async def get_text(url):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        r = await c.get(url, headers=HEADERS)
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


ANSWER_SECONDS = 120  # អស់ពេលហើយបង្ហាញចម្លើយ


async def set_answer(u, c, ans, kind):
    token = dt.datetime.now().timestamp()
    c.chat_data["answer"] = (str(ans), kind, token)
    c.job_queue.run_once(_timeout_reveal, ANSWER_SECONDS, chat_id=u.effective_chat.id,
                         data={"token": token})


async def _timeout_reveal(ctx: ContextTypes.DEFAULT_TYPE):
    cd = ctx.application.chat_data.get(ctx.job.chat_id, {})
    ans = cd.get("answer")
    if ans and ans[2] == ctx.job.data["token"]:
        cd.pop("answer", None)
        await ctx.bot.send_message(ctx.job.chat_id, f"⏰ អស់ពេលហើយ! ចម្លើយគឺ: {ans[0]}")


async def reveal(u, c):
    ans = c.chat_data.pop("answer", None)
    if not ans:
        return await u.message.reply_text("មិនមានសំណួរដែលកំពុងរង់ចាំចម្លើយទេ")
    await u.message.reply_text(f"🔎 ចម្លើយគឺ: {ans[0]}")


async def riddle(u, c):
    q, a = random.choice(RIDDLES)
    await set_answer(u, c, a, "riddle")
    await u.message.reply_text(f"🧩 {q}\n(ឆ្លើយក្នុងក្រុមបាន!)")


# ---------------------------------------------------------------- [2] daily info
async def send_feed(u, title, url, n=5):
    try:
        items = await rss(url, n)
        await u.message.reply_text(title + "\n\n" + "\n\n".join(f"• {t}\n{l}" for t, l in items),
                                   disable_web_page_preview=True)
    except Exception:
        await u.message.reply_text("មិនអាចទាញព័ត៌មានបានទេ 😢")


KH_FEEDS = [("CEN", "https://cen.com.kh/feed"),
            ("Khmer Breaking News", "https://kbn.news/feed"),
            ("DAP News", "https://dap-news.com/feed")]


async def to_km(text):
    try:
        d = await get_json("https://api.mymemory.translated.net/get", q=text[:450], langpair="en|km")
        return d["responseData"]["translatedText"] or text
    except Exception:
        return text


async def news(u, c):
    lines = ["📰 ព័ត៌មានថ្ងៃនេះ", "", "🇰🇭 ព័ត៌មានខ្មែរ"]
    for name, url in KH_FEEDS:
        try:
            items = await rss(url, 3)
            lines.append(f"\n{name}:")
            lines += [f"• {t}\n{l}" for t, l in items]
        except Exception:
            lines.append(f"\n{name}: មិនអាចទាញបាន")
    try:
        items = await rss("https://feeds.bbci.co.uk/news/world/rss.xml", 3)
        titles = await asyncio.gather(*[to_km(t) for t, _ in items])
        lines.append("\n🌍 ព័ត៌មានពិភពលោក")
        lines += [f"• {tt}\n{l}" for tt, (_, l) in zip(titles, items)]
    except Exception:
        pass
    await u.message.reply_text("\n".join(lines), disable_web_page_preview=True)
async def tech(u, c): await send_feed(u, "💻 បច្ចេកវិទ្យា", "https://feeds.bbci.co.uk/news/technology/rss.xml")
ASIA_LEAGUES = [("🏆 AFC Champions League", "afc.champions"),
                ("🇹🇭 ថៃ (Thai League 1)", "tha.1"),
                ("🇻🇳 វៀតណាម (V.League 1)", "vnm.1")]


async def league_today(slug):
    d = await get_json(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard")
    rows = []
    for ev in d.get("events", [])[:8]:
        comp = ev["competitions"][0]
        a, b = comp["competitors"][0], comp["competitors"][1]
        score = f"{a.get('score', '-')} - {b.get('score', '-')}"
        status = ev["status"]["type"]["shortDetail"]
        rows.append(f"• {a['team']['displayName']} {score} {b['team']['displayName']} ({status})")
    return rows


async def sport(u, c):
    lines = ["⚽ កីឡា", "", "🌏 ការប្រកួតនៅអាស៊ីថ្ងៃនេះ"]
    for label, slug in ASIA_LEAGUES:
        try:
            rows = await league_today(slug)
            lines.append(f"\n{label}")
            lines += rows or ["  គ្មានការប្រកួតថ្ងៃនេះ"]
        except Exception:
            lines.append(f"\n{label}: មិនអាចទាញបាន")
    try:
        items = await rss("https://feeds.bbci.co.uk/sport/rss.xml", 3)
        titles = await asyncio.gather(*[to_km(t) for t, _ in items])
        lines.append("\n📰 ព័ត៌មានកីឡាពិភពលោក")
        lines += [f"• {tt}\n{l}" for tt, (_, l) in zip(titles, items)]
    except Exception:
        pass
    await u.message.reply_text("\n".join(lines), disable_web_page_preview=True)




WAIT_LOC = {}  # (chat_id, user_id) -> เวลาที่ขอตำแหน่ง


async def weather_at(lat, lon, name="ទីតាំងរបស់អ្នក"):
    w = await get_json("https://api.open-meteo.com/v1/forecast", latitude=lat,
                       longitude=lon, timezone="auto",
                       current="temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                       daily="temperature_2m_max,temperature_2m_min,precipitation_probability_max")
    cur, d = w["current"], w["daily"]
    return (f"🌤 អាកាសធាតុ {name}\n{WX.get(cur['weather_code'], 'មិនស្គាល់')}\n"
            f"🌡 {cur['temperature_2m']}°C (ខ្ពស់ {d['temperature_2m_max'][0]}° / ទាប {d['temperature_2m_min'][0]}°)\n"
            f"💧 សំណើម {cur['relative_humidity_2m']}%  💨 ខ្យល់ {cur['wind_speed_10m']} km/h\n"
            f"☔ ឱកាសភ្លៀង {d['precipitation_probability_max'][0]}%")


async def weather_text(city="Phnom Penh"):
    g = await get_json("https://geocoding-api.open-meteo.com/v1/search", name=city, count=1)
    if not g.get("results"):
        return "រកមិនឃើញទីក្រុងនេះទេ"
    p = g["results"][0]
    return await weather_at(p["latitude"], p["longitude"], p["name"])


async def weather(u, c):
    if args_text(c):
        try:
            return await u.message.reply_text(await weather_text(args_text(c)))
        except Exception:
            return await u.message.reply_text("មិនអាចទាញអាកាសធាតុបានទេ 😢")
    WAIT_LOC[(u.effective_chat.id, u.effective_user.id)] = dt.datetime.now(dt.timezone.utc)
    await u.message.reply_text(
        "📍 សូមផ្ញើទីតាំងរបស់អ្នកក្នុង ៥ នាទី៖\n"
        "ចុច 📎 → Location → Send Current Location\n"
        "ឬវាយ /weather <ឈ្មោះទីក្រុង> ក៏បាន")


async def on_location(u: Update, c: ContextTypes.DEFAULT_TYPE):
    key = (u.effective_chat.id, u.effective_user.id)
    asked = WAIT_LOC.pop(key, None)
    if not asked or (dt.datetime.now(dt.timezone.utc) - asked).total_seconds() > 300:
        return  # មិនបានស្នើសុំ /weather ទេ ដូច្នេះមិនឆ្លើយ
    loc = u.message.location
    try:
        await u.message.reply_text(await weather_at(loc.latitude, loc.longitude))
    except Exception:
        await u.message.reply_text("មិនអាចទាញអាកាសធាតុបានទេ 😢")


async def exchange(u, c):
    try:
        r = (await get_json("https://open.er-api.com/v6/latest/USD"))["rates"]
        lines = [f"1 USD = {r[k]:,.2f} {k}" for k in ("KHR", "THB", "VND", "EUR", "JPY", "CNY", "GBP")]
        await u.message.reply_text("💱 អត្រាប្តូរប្រាក់\n" + "\n".join(lines))
    except Exception:
        await u.message.reply_text("មិនអាចទាញអត្រាប្តូរប្រាក់បានទេ 😢")


TAEL_GRAM = 37.8          # 1 តម្លឹង ≈ 37.8 ក្រាម (ប្រហែលស្តង់ដារ tael) - អាចកែបាន
CHI_GRAM = TAEL_GRAM / 10  # 1 តម្លឹង = 10 ជី
HUN_GRAM = CHI_GRAM / 10   # 1 ជី = 10 ហ៊ុន
OZ_GRAM = 31.1035


TROY_G = 31.1035  # 1 troy ounce គិតជាក្រាម
METAL_UNITS = [("1 ក្រាម", 1), ("1 ជី (3.75g)", 3.75), ("1 តម្លឹង (37.5g)", 37.5), ("1 អោន្ស (Troy oz)", TROY_G)]


async def metal_price(sym):
    d = await get_json(f"https://api.gold-api.com/price/{sym}")
    return float(d.get("price") or d.get("priceUsd"))


# ⚠️ ទម្ងន់ឯកតាខ្មែរ (ត្រូវបញ្ជាក់ជាមួយហាងមាស)
HUN_GRAM = 1.875   # ហ៊ុន: សន្មត់ថាពាក់កណ្តាលជី
CHI_GRAM = 3.75    # ជី
TAEL_GRAM = 37.8   # តម្លឹង (tael)
GRAM_PER_OZ = 31.1035
GOLD_UNITS = [("ហ៊ុន", HUN_GRAM), ("ជី", CHI_GRAM), ("តម្លឹង", TAEL_GRAM)]
METALS = [("🥇 មាស", "XAU"), ("⚪ ផ្លាសទីន", "XPT"), ("🥈 ប្រាក់", "XAG")]


async def metal_usd_oz(sym):
    d = await get_json(f"https://api.gold-api.com/price/{sym}")
    return float(d["price"])


async def gold(u, c):
    try:
        khr = (await get_json("https://open.er-api.com/v6/latest/USD"))["rates"]["KHR"]
    except Exception:
        return await u.message.reply_text("មិនអាចទាញអត្រាប្តូរប្រាក់បានទេ 😢")
    out = ["💰 តម្លៃមាស ផ្លាសទីន និងប្រាក់", f"💱 1 USD = {khr:,.0f} រៀល"]
    for label, sym in METALS:
        try:
            oz = await metal_usd_oz(sym)
        except Exception:
            out.append(f"\n{label}: មិនអាចទាញបាន")
            continue
        out.append(f"\n{label} (1 Oz ≈ ${oz:,.2f})")
        for name, g in GOLD_UNITS:
            usd = oz / GRAM_PER_OZ * g
            out.append(f"• {name}: {usd * khr:,.0f} រៀល | ${usd:,.2f}")
    out.append("\n⚠️ តម្លៃប្រហាក់ប្រហែល មិនមែនតម្លៃហាងទេ")
    await u.message.reply_text("\n".join(out))


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
    await set_answer(u, c, a, "quiz")
    await u.message.reply_text(f"❓ Quiz: {q}")


async def guess(u, c):
    if "secret" not in c.chat_data:
        c.chat_data["secret"] = random.randint(1, 100)
    if not c.args or not c.args[0].isdigit():
        return await u.message.reply_text("🎯 ខ្ញុំគិតលេខ ១-១០០ ហើយ! វាយ /guess <លេខ>")
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
    await set_answer(u, c, w, "word")
    await u.message.reply_text(f"🔤 តម្រៀបអក្សរឱ្យត្រូវ: {s}")


async def math_game(u, c):
    a, b = random.randint(10, 99), random.randint(2, 20)
    op = random.choice(["+", "-", "x"])
    r = a + b if op == "+" else a - b if op == "-" else a * b
    await set_answer(u, c, str(r), "math")
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


POLL_GUIDE = (
    "📊 របៀបប្រើ /poll\n"
    "/poll សំណួរ | ជម្រើស១ | ជម្រើស២ | ...\n\n"
    "ឧទាហរណ៍:\n"
    "/poll ចូលចិត្តផ្លែឈើអ្វី? | ស្វាយ | ចេក | ម្នាស់\n\n"
    "ជម្រើសបន្ថែម (ដាក់មុនសំណួរ):\n"
    "-m  ➜ ជ្រើសបានច្រើនចម្លើយ\n"
    "-a  ➜ បោះឆ្នោតមិនបង្ហាញឈ្មោះ\n"
    "ឧទាហរណ៍: /poll -a -m ចង់ញ៉ាំអ្វី? | ភ្លាយ | ខ្លួច\n\n"
    "ដែនកំណត់: សំណួរ ≤ ៣០០ តួ, ជម្រើស ២–១០, ជម្រើសនីមួយៗ ≤ ១០០ តួ"
)


async def poll(u, c):
    raw = args_text(c)
    if not raw:
        return await u.message.reply_text(POLL_GUIDE)
    multi = anon = False
    while raw.startswith("-"):
        flag, _, raw = raw.partition(" ")
        raw = raw.strip()
        if flag == "-m":
            multi = True
        elif flag == "-a":
            anon = True
        else:
            return await u.message.reply_text(f"❌ មិនស្គាល់ជម្រើស {flag}\n\n" + POLL_GUIDE)
    parts = [x.strip() for x in raw.split("|") if x.strip()]
    if len(parts) < 3:
        return await u.message.reply_text("❌ ត្រូវមានសំណួរ និងយ៉ាងហោចណាស់ ២ ជម្រើស\n\n" + POLL_GUIDE)
    q, opts = parts[0], parts[1:]
    if len(q) > 300:
        return await u.message.reply_text("❌ សំណួរវែងពេក (អតិបរមា ៣០០ តួ)")
    if len(opts) > 10:
        return await u.message.reply_text("❌ ជម្រើសច្រើនពេក (អតិបរមា ១០)")
    if any(len(o) > 100 for o in opts):
        return await u.message.reply_text("❌ ជម្រើសមួយវែងពេក (អតិបរមា ១០០ តួ)")
    await u.effective_chat.send_poll(q, opts, is_anonymous=anon, allows_multiple_answers=multi)


async def rank(u, c):
    s = DATA["scores"].get(str(u.effective_chat.id), {})
    top = sorted(s.values(), key=lambda x: -x["pts"])[:10]
    if not top:
        return await u.message.reply_text("មិនទាន់មានពិន្ទុទេ! សាកលេង /quiz /math 🎮")
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    await u.message.reply_text("🏆 ចំណាត់ថ្នាក់\n" + "\n".join(f"{medals[i]} {x['name']}: {x['pts']}" for i, x in enumerate(top)))


# ---------------------------------------------------------------- [4] tools
def detect_lang(t):
    if any("\u1780" <= ch <= "\u17ff" for ch in t):
        return "km"
    if any("\u0e00" <= ch <= "\u0e7f" for ch in t):
        return "th"
    return "en"


async def _mymemory(text, src, dst):
    d = await get_json("https://api.mymemory.translated.net/get", q=text, langpair=f"{src}|{dst}")
    return d["responseData"]["translatedText"]


def detect_lang(t):
    if any("\u1780" <= ch <= "\u17ff" for ch in t):
        return "km"
    if any("\u0e00" <= ch <= "\u0e7f" for ch in t):
        return "th"
    return "en"


async def translate(u, c):
    # /translate <អត្ថបទ>            -> ខ្មែរ/ថៃ ទៅអង់គ្លេស, អង់គ្លេសទៅខ្មែរ
    # /translate th <អត្ថបទ>        -> អង់គ្លេស ទៅថៃ (ឬ km / en)
    args = list(c.args)
    target = None
    if args and args[0].lower() in ("km", "th", "en"):
        target = args.pop(0).lower()
    t = " ".join(args).strip() or (u.message.reply_to_message.text if u.message.reply_to_message else "")
    if not t:
        return await u.message.reply_text(
            "ប្រើ៖\n/translate <អត្ថបទ> (អង់គ្លេស ➜ ខ្មែរ, ខ្មែរ/ថៃ ➜ អង់គ្លេស)\n"
            "/translate th <អត្ថបទ> (អង់គ្លេស ➜ ថៃ)\n"
            "ឬ reply សារណាមួយ រួចវាយ /translate")
    src = detect_lang(t)
    if target is None:
        target = "en" if src != "en" else "km"
    if src == target:
        return await u.message.reply_text("ភាសាដើម និងភាសាគោលដៅដូចគ្នា ✏️")
    try:
        d = await get_json("https://api.mymemory.translated.net/get", q=t, langpair=f"{src}|{target}")
        out = d["responseData"]["translatedText"]
        names = {"km": "ខ្មែរ", "th": "ថៃ", "en": "អង់គ្លេស"}
        await u.message.reply_text(f"🌐 {names[src]} ➜ {names[target]}\n{out}")
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
    raw = args_text(c) or "cambodia"
    try:
        z = ZoneInfo(TZ_ALIAS.get(raw.lower(), raw))
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
        save()
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


# ---------------------------------------------------------------- [6] map & route
async def geocode(q):
    d = await get_json("https://nominatim.openstreetmap.org/search", q=q, format="json", limit=1,
                       **{"accept-language": "km,en"})
    if not d:
        return None
    r = d[0]
    name = ", ".join(r.get("display_name", q).split(", ")[:3])
    return float(r["lat"]), float(r["lon"]), name


def osm_link(lat, lon):
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}"


def gmaps_link(lat, lon):
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"


def gdir_link(a, b):
    return (f"https://www.google.com/maps/dir/?api=1&origin={a[0]},{a[1]}"
            f"&destination={b[0]},{b[1]}&travelmode=driving")


def haversine_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


async def map_cmd(u, c):
    q = args_text(c)
    if not q:
        return await u.message.reply_text("ប្រើ៖ /map ឈ្មោះកន្លែង\nឧទាហរណ៍: /map ស្វាយរៀង")
    try:
        g = await geocode(q)
    except Exception:
        g = None
    if not g:
        return await u.message.reply_text("រកមិនឃើញកន្លែងនេះទេ 🗺 សាកវាយឈ្មោះផ្សេង ឬបន្ថែមខេត្ត")
    lat, lon, name = g
    await u.message.reply_location(latitude=lat, longitude=lon)
    await u.message.reply_text(f"📍 {name}\n\n🗺 OpenStreetMap: {osm_link(lat, lon)}\n"
                               f"🌐 Google Maps: {gmaps_link(lat, lon)}", disable_web_page_preview=True)


async def route_cmd(u, c):
    raw = args_text(c)
    usage = "ប្រើ៖ /route ចំណុចចាប់ផ្តើម ទៅ ចំណុចចុងក្រោយ\nឧទាហរណ៍: /route ភ្នំពេញ ទៅ សៀមរាប"
    sep = next((x for x in (" ទៅ ", " to ", "->") if x in raw), None)
    if not sep:
        return await u.message.reply_text(usage)
    a_txt, b_txt = [x.strip() for x in raw.split(sep, 1)]
    if not a_txt or not b_txt:
        return await u.message.reply_text(usage)
    try:
        ga, gb = await geocode(a_txt), await geocode(b_txt)
    except Exception:
        ga = gb = None
    if not ga or not gb:
        return await u.message.reply_text("រកមិនឃើញចំណុចមួយ ឬទាំងពីរ 🗺 សាកវាយឈ្មោះផ្សេង")

    km = haversine_km(ga, gb)
    mins = None
    try:
        d = await get_json(f"https://router.project-osrm.org/route/v1/driving/"
                           f"{ga[1]},{ga[0]};{gb[1]},{gb[0]}", overview="false")
        r = d["routes"][0]
        km, mins = r["distance"] / 1000, r["duration"] / 60
    except Exception:
        pass

    await u.message.reply_location(latitude=ga[0], longitude=ga[1])
    await u.message.reply_location(latitude=gb[0], longitude=gb[1])
    if mins is not None:
        info = f"🛣 ចម្ងាយ ~{km:,.0f} km | ⏱ ~{mins / 60:.1f} ម៉ោង (ជិះឡាន)"
    else:
        info = f"🛣 ចម្ងាយបន្ទាត់ត្រង់ ~{km:,.0f} km (មិនអាចគណនាផ្លូវបាន)"
    await u.message.reply_text(
        f"{info}\n\n📍 ពី: {ga[2]}\n📍 ទៅ: {gb[2]}\n\n"
        f"🌐 ផ្លូវ Google Maps: {gdir_link(ga, gb)}\n"
        f"⚠️ ពេលវេលាប្រហាក់ប្រហែល ពឹងលើផ្លូវ និងចរាចរណ៍", disable_web_page_preview=True)


# ---------------------------------------------------------------- [7] international stocks
STOCKS = [("🚗 Tesla", "tsla.us"), ("🎮 NVIDIA", "nvda.us"), ("📘 Facebook (Meta)", "meta.us"),
          ("🔍 Google", "googl.us"), ("🍎 Apple", "aapl.us"), ("🪟 Microsoft", "msft.us"),
          ("📦 Amazon", "amzn.us"), ("🎬 Netflix", "nflx.us"), ("💻 Intel", "intc.us"),
          ("🛢 ប្រេងឆៅ WTI", "cl.f")]


async def stooq_quote(sym):
    text = await get_text(f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv")
    rows = list(csv.reader(io.StringIO(text.strip())))
    if len(rows) < 2 or rows[1][3] in ("N/D", ""):
        return None
    o, cl = float(rows[1][3]), float(rows[1][6])
    return cl, (cl - o) / o * 100


async def stock(u, c):
    wanted = args_text(c).lower()
    items = STOCKS
    if wanted:
        items = [x for x in STOCKS if wanted in x[1].lower() or wanted in x[0].lower()]
        if not items:
            return await u.message.reply_text("ប្រើ /stock ឬ /stock tsla | nvda | meta | googl | aapl | msft | amzn | nflx | intc | cl.f")
    lines = ["📈 តម្លៃភាគហ៊ុនអន្តរជាតិ (USD)", ""]
    for label, sym in items:
        try:
            q = await stooq_quote(sym)
        except Exception:
            q = None
        if q is None:
            lines.append(f"{label}: មិនអាចទាញបាន")
            continue
        price, pct = q
        arrow = "🟢 ▲" if pct >= 0 else "🔴 ▼"
        lines.append(f"{label}: ${price:,.2f}  {arrow} {pct:+.2f}%")
    lines.append("\n⚠️ តម្លៃអាចយឺតជាងការពិត ហើយ % គិតពីពេលបើកផ្សារ")
    await u.message.reply_text("\n".join(lines))


HELP = """🤖 Koval Bot - បញ្ជី Command
😄 ជជែក: /hello /joke /riddle /quote /roast /compliment /truth /dare /wouldyou /fact
📰 ព័ត៌មាន: /news /tech /sport /weather /exchange /gold /stock /crypto /today /holiday /trend
🎮 ល្បែង: /quiz /guess /dice /coin /rps /wordgame /math /story /poll /rank
🛠 ឧបករណ៍: /map /route /translate /define /calc /convert /remind /timer /time /summary /search /ask
👥 ក្រុម: /rules /welcome /birthday /admin /report /warn /mute /stats /daily /help"""


async def help_cmd(u, c): await u.message.reply_text(HELP)


# ---------------------------------------------------------------- text handler
async def on_text(u: Update, c: ContextTypes.DEFAULT_TYPE):
    m = u.message
    if not m or not m.text:
        return
    cid, usr = str(u.effective_chat.id), u.effective_user
    st = DATA["stats"].setdefault(cid, {}).setdefault(str(usr.id), {"name": usr.first_name, "n": 0})
    st["n"] += 1
    st["name"] = usr.first_name
    h = HISTORY.setdefault(u.effective_chat.id, [])
    h.append(f"{usr.first_name}: {m.text}")
    del h[:-200]
    if st["n"] % 20 == 0:
        save()
    ans = c.chat_data.get("answer")
    if ans:
        if m.text.strip().lower() == ans[0].lower():
            c.chat_data.pop("answer")
            add_score(u.effective_chat.id, usr, 2)
            return await m.reply_text(f"✅ ត្រូវហើយ {usr.first_name}! (+2 ពិន្ទុ)")
        return await m.reply_text(f"❌ ខុសហើយ {usr.first_name}! ព្យាយាមម្តងទៀត ឬវាយ /reveal ដើម្បីមើលចម្លើយ")
    me = c.bot.username
    replied = m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id == c.bot.id
    if u.effective_chat.type == "private" or f"@{me}".lower() in m.text.lower() or replied:
        q = m.text.replace(f"@{me}", "").strip()
        r = await ai(q)
        await m.reply_text(r or random.choice(["😄 ហ៊ាស! ខ្ញុំនៅទីនេះ វាយ /help មើលអ្វីដែលខ្ញុំអាចធ្វើបាន",
                                               "🤖 ហៅខ្ញុំមែនទេ? សាកវាយ /joke ឬ /quiz មើល!"]))


# ---------------------------------------------------------------- auto delete
class AutoDeleteBot(ExtBot):
    """គ្រប់សារដែល bot ផ្ញើ នឹងត្រូវលុបបន្ទាប់ពី AUTO_DELETE_SECONDS"""

    async def _post(self, endpoint, data=None, *args, **kwargs):
        result = await super()._post(endpoint, data, *args, **kwargs)
        if endpoint.startswith("send") and endpoint not in NO_DELETE and isinstance(result, dict):
            chat_id = result.get("chat", {}).get("id")
            msg_id = result.get("message_id")
            if chat_id and msg_id:
                asyncio.create_task(self._delete_later(chat_id, msg_id))
        return result

    async def _delete_later(self, chat_id, msg_id):
        await asyncio.sleep(AUTO_DELETE_SECONDS)
        try:
            await self.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass


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
    "reveal": reveal,
    "map": map_cmd, "route": route_cmd, "stock": stock,
}


def main():
    if not BOT_TOKEN:
        raise SystemExit("សូមកំណត់ BOT_TOKEN (export BOT_TOKEN=xxxx)")
    # protect_content=True ត្រូវបានអនុវត្តលើសារ bot ទាំងអស់ (reply, send_message, poll ...)
    # ដោយមិនចាំបាច់ដាក់ក្នុងគ្រប់ reply_text
    defaults = Defaults(tzinfo=TZ, protect_content=True)
    app = (Application.builder()
           .bot(AutoDeleteBot(token=BOT_TOKEN, defaults=defaults))
           .build())
    for name, fn in COMMANDS.items():
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member))
    app.add_handler(MessageHandler(filters.LOCATION, on_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.job_queue.run_daily(daily_job, dt.time(8, 0, tzinfo=TZ))
    print("Koval bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
