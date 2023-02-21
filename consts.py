import os

# BINANCE
API_KEY = os.getenv("BINANCE_API_KEY")  # TODO 반드시 설정해주세요
API_SECRET = os.getenv("BINANCE_SECRET_KEY")  # TODO 반드시 설정해주세요

# TRADING
SYMBOL = 'BTCUSDT'
TICKER = 'BTC/USDT'
TIME_FRAME = '1m'
REQ_LIMIT = 100 # 기본적으로 20개
LEVERAGE = 15
CONDITION_RATE = 0.05
GAP_PERCENT = 0.01
MARGIN_TYPE = 'ISOLATED'
LOOP_INTERVAL = 5 * 1  # 메인 루프 반복 시간(1분) 초단위
LOSS_CUT = -2  # 손절 라인
NEUTRAL = 'NEUTRAL'
LONG = 'LONG'
SHORT = 'SHORT'
DIVISION = 10
GENERAL_DIV = 4
SCALE_RATE = 1
MINIMUM_TRADE_RATE = 0.005

# BINANCE API 초당 0.44번 / 1일 160000 / 분당 1200 / 10초당 50 
# BINANCE time_frame_list = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'] ( d,w,M 은 적용 안돼서 안씀)

# 주문관련
SIGNAL_TO_OPEN_SIDE = {
    LONG: 'BUY',
    SHORT: 'SELL'
}

SIGNAL_TO_CLOSE_SIDE = {
    LONG: 'SELL',
    SHORT: 'BUY'
}

HEDGE_TO_OPEN_SIDE = {
    LONG: 'SELL',
    SHORT: 'BUY'
}

HEDGE_TO_CLOSE_SIDE = {
    LONG: 'BUY',
    SHORT: 'SELL'
}

# TELEGRAM
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_ALRGO_NOTICE_BOT_TOKEN")  # TODO 반드시 설정해주세요
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_ALRGO_NOTICE_BOT_CHAT_ID")  # TODO 반드시 설정해주세요
TELEGRAM_MESSAGE_MAX_SIZE = 4095  # 텔레그램 메시지 최대길이




