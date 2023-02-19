import time
from consts import *
import requests
import json
import util
import platform


def call_binance_api(original_func):
    """
    Binance API 호출하며 서버시간에러 발생시 처리 데코레이터
    """
    def wrapper(*args, **kwargs):
        url = "https://fapi.binance.com/fapi/v1/time"
        t = time.time() * 1000
        r = requests.get(url)
        result = json.loads(r.content)
        if abs(int(t) - result["serverTime"]) > 900:
            util.send_to_telegram("❗️Time diff occur!! {}".format(int(t) - result["serverTime"]))
            if platform.system() == "Windows":
                os.system('chcp 65001')
                os.system('dir/w')
                os.system('net stop w32time')
                os.system('w32tm /unregister')
                os.system('w32tm /register')
                os.system('net start w32time')
                os.system('w32tm /resync')
        return original_func(*args, **kwargs)
    return wrapper
