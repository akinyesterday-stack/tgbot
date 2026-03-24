import os
import telebot
import requests
from groq import Groq
from tavily import TavilyClient

GROQ_API_KEY = os.environ['GROQ_API_KEY']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TAVILY_API_KEY = os.environ['TAVILY_API_KEY']

client = Groq(api_key=GROQ_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)


def web_ara(sorgu):
    """Tavily ile hızlı internet araması yapar"""
    try:
        response = tavily.search(
            query=sorgu,
            search_depth="basic",
            max_results=5,
            include_answer=True
        )
        context = ""
        if response.get("answer"):
            context += f"Özet: {response['answer']}\n\n"
        for r in response.get("results", []):
            context += f"Kaynak: {r['title']}\nURL: {r['url']}\nİçerik: {r['content']}\n\n"
        return context
    except Exception as e:
        return f"Arama hatası: {e}"


def siteyi_oku(url):
    """Jina AI ile verilen URL'nin içeriğini okur ve analiz eder"""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"Accept": "text/plain"}
        response = requests.get(jina_url, headers=headers, timeout=15)
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


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    bot.send_chat_action(message.chat.id, 'typing')
    text = message.text.strip()

    try:
        # URL içeriyorsa siteye gir ve analiz et
        if any(text.startswith(p) for p in ["http://", "https://", "www."]) or \
           ("." in text and " " not in text):
            bot.send_message(message.chat.id, "🌐 Site okunuyor...")
            icerik = siteyi_oku(text)
            sistem = (
                "Sen bir web analiz uzmanısın. Verilen site içeriğini Türkçe olarak "
                "özetle, önemli bilgileri çıkar ve kullanıcıya net şekilde sun."
            )
            yanit = groq_analiz(sistem, f"Site içeriği:\n{icerik}\n\nBu siteyi analiz et ve özetle.")
        else:
            # Normal sorularda internette ara
            arama = web_ara(text)
            sistem = (
                "Sen hızlı ve zeki bir asistansın. İnternet verilerini kullanarak "
                "kullanıcının sorusuna kısa, net ve Türkçe cevap ver. "
                "Fiyat/tarih gibi somut bilgiler varsa mutlaka belirt. Asla uydurma."
            )
            yanit = groq_analiz(sistem, f"İnternet verileri:\n{arama}\n\nSoru: {text}")

        bot.reply_to(message, yanit)

    except Exception as e:
        bot.reply_to(message, "Şu an yoğunluk var, tekrar dene.")


print("⚡ Hızlı Bot (Jina + Tavily + Groq Instant) Başlatıldı!")
bot.infinity_polling()
