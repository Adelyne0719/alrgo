from consts import *
import telegram  # TODO pip install python-telegram-bot
import time

bot = None


def send_to_telegram(message):
   """
   텔레그램 메시지 전송함수, 최대 3회 재전송 수행
   :param message:
   :return:
   """
   global bot
   if not bot:
       if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
           bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
       else:
           raise Exception("conts.py > TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 넣어주세요!")

   retries = 0
   max_retries = 3

   while retries < max_retries and bot:
       try:
           bot.send_message(text=message[:TELEGRAM_MESSAGE_MAX_SIZE], chat_id=TELEGRAM_CHAT_ID)
           return True
       except telegram.error.TimedOut as timeout:
           time.sleep(5 * retries)
           retries += 1
           print("Telegram got a error! retry...")
       except Exception as e:
           bot = None
           retries = max_retries

   if retries == max_retries:
       bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
       print("Telegram failed to retry...")