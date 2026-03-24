import os
import threading
import telebot
import requests
from groq import Groq
from tavily import TavilyClient
from telebot import types
from flask import Flask, request, jsonify
from flask_cors import CORS

GROQ_API_KEY = os.environ['GROQ_API_KEY']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TAVILY_API_KEY = os.environ['TAVILY_API_KEY']
OWNER_ID = int(os.environ.get('OWNER_ID', '0'))
ADMIN_SECRET = os.environ.get('ADMIN_SECRET', 'akinaltun2024')
PORT = int(os.environ.get('PORT', 5000))

client = Groq(api_key=GROQ_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

lock = threading.Lock()
approved_users = set()
pending_users = {}  # user_id -> dict(id, name, message)

# --- Flask Admin API ---
app = Flask(__name__)
CORS(app)


def check_auth():
    return request.headers.get('X-Admin-Secret', '') == ADMIN_SECRET


@app.route('/')
def index():
    return "Bot Admin API çalışıyor."


@app.route('/api/users', methods=['GET'])
def get_users():
    if not check_auth():
        return jsonify({'error': 'Yetkisiz erişim'}), 401
    with lock:
        pending = list(pending_users.values())
        approved = list(approved_users)
    return jsonify({'pending': pending, 'approved': approved})


@app.route('/api/approve', methods=['POST'])
def approve_user():
    if not check_auth():
        return jsonify({'error': 'Yetkisiz erişim'}), 401
    user_id = int(request.json.get('user_id'))
    with lock:
        approved_users.add(user_id)
        pending_users.pop(user_id, None)
    try:
        bot.send_message(user_id, "✅ Erişiminiz onaylandı! Artık sorularınızı sorabilirsiniz.")
    except Exception:
        pass
    return jsonify({'success': True})


@app.route('/api/reject', methods=['POST'])
def reject_user():
    if not check_auth():
        return jsonify({'error': 'Yetkisiz erişim'}), 401
    user_id = int(request.json.get('user_id'))
    with lock:
        pending_users.pop(user_id, None)
        approved_users.discard(user_id)
    try:
        bot.send_message(user_id, "❌ Erişim talebiniz reddedildi.")
    except Exception:
        pass
    return jsonify({'success': True})


@app.route('/api/remove', methods=['POST'])
def remove_user():
    if not check_auth():
        return jsonify({'error': 'Yetkisiz erişim'}), 401
    user_id = int(request.json.get('user_id'))
    with lock:
        approved_users.discard(user_id)
    return jsonify({'success': True})


# --- Bot Fonksiyonları ---
def web_ara(sorgu):
    try:
        response = tavily.search(query=sorgu, search_depth="basic", max_results=5, include_answer=True)
        context = ""
        if response.get("answer"):
            context += f"Özet: {response['answer']}\n\n"
        for r in response.get("results", []):
            context += f"Kaynak: {r['title']}\nURL: {r['url']}\nİçerik: {r['content']}\n\n"
        return context
    except Exception as e:
        return f"Arama hatası: {e}"


def siteyi_oku(url):
    try:
        if not url.startswith("http"):
            url = "https://" + url
        response = requests.get(f"https://r.jina.ai/{url}", headers={"Accept": "text/plain"}, timeout=15)
        return response.text[:4000]
    except Exception as e:
        return f"Site okunamadı: {e}"


def groq_analiz(sistem, kullanici_sorusu):
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": sistem},
            {"role": "user", "content": kullanici_sorusu}
        ],
        temperature=0.2,
        max_tokens=1024
    )
    return response.choices[0].message.content


def yanit_uret(message):
    text = message.text.strip()
    if any(text.startswith(p) for p in ["http://", "https://", "www."]) or \
       ("." in text and " " not in text):
        bot.send_message(message.chat.id, "🌐 Site okunuyor...")
        icerik = siteyi_oku(text)
        sistem = "Sen bir web analiz uzmanısın. Verilen site içeriğini Türkçe olarak özetle."
        yanit = groq_analiz(sistem, f"Site içeriği:\n{icerik}\n\nBu siteyi analiz et ve özetle.")
    else:
        arama = web_ara(text)
        sistem = (
            "Sen hızlı ve zeki bir asistansın. İnternet verilerini kullanarak "
            "kullanıcının sorusuna kısa, net ve Türkçe cevap ver. Asla uydurma."
        )
        yanit = groq_analiz(sistem, f"İnternet verileri:\n{arama}\n\nSoru: {text}")
    bot.reply_to(message, yanit)


@bot.message_handler(commands=["myid"])
def handle_myid(message):
    bot.reply_to(message, f"Senin Telegram ID'n: `{message.from_user.id}`", parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("onayla_") or call.data.startswith("reddet_"))
def handle_approval(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Bu butonu kullanma yetkin yok.")
        return
    parts = call.data.split("_")
    action = parts[0]
    user_id = int(parts[1])
    if action == "onayla":
        with lock:
            approved_users.add(user_id)
            pending_users.pop(user_id, None)
        bot.answer_callback_query(call.id, "Kullanıcı onaylandı ✅")
        bot.edit_message_text(f"{call.message.text}\n\n✅ ONAYLANDI", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(user_id, "✅ Erişiminiz onaylandı! Artık sorularınızı sorabilirsiniz.")
        except Exception:
            pass
    else:
        with lock:
            pending_users.pop(user_id, None)
            approved_users.discard(user_id)
        bot.answer_callback_query(call.id, "Kullanıcı reddedildi ❌")
        bot.edit_message_text(f"{call.message.text}\n\n❌ REDDEDİLDİ", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(user_id, "❌ Erişim talebiniz reddedildi.")
        except Exception:
            pass


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    if message.text and message.text.startswith("/"):
        return

    if user_id == OWNER_ID:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            yanit_uret(message)
        except Exception as e:
            bot.reply_to(message, f"Hata: {str(e)}")
        return

    with lock:
        is_approved = user_id in approved_users
        is_pending = user_id in pending_users

    if is_approved:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            yanit_uret(message)
        except Exception as e:
            bot.reply_to(message, f"Hata: {str(e)}")
        return

    if is_pending:
        bot.reply_to(message, "⏳ Talebiniz inceleniyor, lütfen bekleyin.")
        return

    with lock:
        pending_users[user_id] = {
            'id': user_id,
            'name': f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip(),
            'username': message.from_user.username or '',
            'message': message.text
        }

    bot.reply_to(
        message,
        "Efendimm kıymetli komutan düşmanın gazabı intikamın yeryüzündeki kılıcı "
        "haşmetli komutan Akın Altun'a sormam lazım 🗡️"
    )

    if OWNER_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Onayla", callback_data=f"onayla_{user_id}"),
            types.InlineKeyboardButton("❌ Reddet", callback_data=f"reddet_{user_id}")
        )
        bot.send_message(
            OWNER_ID,
            f"🔔 Yeni erişim talebi!\n\n"
            f"👤 İsim: {message.from_user.first_name} {message.from_user.last_name or ''}\n"
            f"🆔 ID: {user_id}\n"
            f"📝 Mesaj: {message.text}\n\n"
            f"Ne yapılsın?",
            reply_markup=markup
        )


def run_flask():
    app.run(host='0.0.0.0', port=PORT)


print("🛡️ Bot + Admin API Başlatıldı!")
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
bot.infinity_polling()
