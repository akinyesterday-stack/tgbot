import os
import telebot
from groq import Groq
from tavily import TavilyClient

GROQ_API_KEY = os.environ['GROQ_API_KEY']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TAVILY_API_KEY = os.environ['TAVILY_API_KEY']

client = Groq(api_key=GROQ_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)


def derin_arama(sorgu):
    """Tavily ile interneti detaylı tarar ve en alakalı sonuçları getirir"""
    try:
        response = tavily.search(
            query=sorgu,
            search_depth="advanced",
            max_results=5,
            include_answer=True
        )
        context = ""
        if response.get("answer"):
            context += f"Özet Cevap: {response['answer']}\n\n"
        for r in response.get("results", []):
            context += f"Kaynak: {r['title']}\nURL: {r['url']}\nİçerik: {r['content']}\n\n"
        return context
    except Exception as e:
        return f"Arama hatası: {e}"


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_query = message.text

    # 1. Adım: Tavily ile internetten güncel veri topla
    raw_data = derin_arama(user_query)

    # 2. Adım: Groq ile analiz ettir
    system_prompt = (
        "Sen dünyanın en zeki dijital asistanısın. Görevin, sana sunulan ham internet verilerini "
        "titizlikle incelemek ve kullanıcının sorusuna NOKTA ATIŞI cevap vermektir.\n\n"
        "KURALLAR:\n"
        "1. Eğer altın/dolar fiyatı soruluyorsa, veriler içindeki en güncel rakamı bul.\n"
        "2. Eğer uçak/otobüs bileti soruluyorsa, fiyat aralıklarını ve hangi sitelerde olduğunu listele.\n"
        "3. Asla 'bilmiyorum' deme, veriler içinde ipucu varsa onları kullan.\n"
        "4. Cevapların kısa, öz ve profesyonel olsun.\n"
        "5. Türkçe cevap ver."
    )

    combined_prompt = f"İNTERNETTEN GELEN CANLI VERİLER:\n{raw_data}\n\nKULLANICI SORUSU: {user_query}"

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": combined_prompt}
            ],
            temperature=0.2
        )
        final_answer = response.choices[0].message.content
        bot.reply_to(message, final_answer)
    except Exception as e:
        bot.reply_to(message, "Şu an sistemde bir yoğunluk var, lütfen tekrar sor.")


print("Süper Zeki Bot (Tavily) Başlatıldı!")
bot.infinity_polling()
