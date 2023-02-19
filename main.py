import asyncio
import pandas as pd
import ccxt.pro as ccxtpro
import logging
import traceback
from binance.um_futures import UMFutures
from consts import *
from datetime import datetime
import time
import sys



class Trader():
    def __init__(self):
        self.binance = UMFutures(key=API_KEY, secret=API_SECRET)
        self.status = NEUTRAL
        self.signal = None
        self.df = None
        self.now = None
        self.price = 0

    def candle_data(self, time_frame, req_limit):
        retry_count = 0
        while True: #리턴값이 없으면 0.25초 후 재요청
            candles = self.binance.klines("BTCUSDT", time_frame, limit=req_limit)
            if candles == None:
                time.sleep(0.25)
                retry_count += 1
            else:
                break
        df = pd.DataFrame(columns=['Open_time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close_time'])
        opentime, lopen, lhigh, llow, lclose, lvol, closetime = [], [], [], [], [], [], []

        for candle in candles:

            opentime.append(datetime.fromtimestamp(int(candle[0]) / 1000))
            lopen.append(float(candle[1]))
            lhigh.append(float(candle[2]))
            llow.append(float(candle[3]))
            lclose.append(float(candle[4]))
            lvol.append(float(candle[5]))
            closetime.append(datetime.fromtimestamp(int(candle[6]) / 1000))
            

        df['Open_time'] = opentime
        df['Open'] = lopen
        df['High'] = lhigh
        df['Low'] = llow
        df['Close'] = lclose
        df['Volume'] = lvol
        df['Close_time'] = closetime
        print(df)
        print('재시도 횟수:', retry_count)

        return df

    async def administrator(self):
        """
        실시간 가격 수신
        """

        exchange = ccxtpro.binance(config={
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })

        while True:
            self.now = datetime.now()
            res_price = await exchange.watch_ticker(SYMBOL)
            res_orderbook = await exchange.watch_order_book(TICKER)
            top_bid = float(res_orderbook['bids'][0][1])
            top_ask = float(res_orderbook['asks'][0][1])
            time_stamp = datetime.fromtimestamp(int(res_price['timestamp']) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            self.price = res_price['close']
            
            if str(self.now)[-9:-7] == '00':
                self.signal = self.signal_generator()

            print(time_stamp, 'price:',self.price,'signal:', self.signal)
            if self.signal != None:
                self.signal = None #나중에는 다른데로 옮겨야 됨


    def signal_generator(self):

        frame_num = int(TIME_FRAME[:-1])
        frame_text = TIME_FRAME[-1]
        redundancy = None
        signal = None
        try:
            if TIME_FRAME: # 시그널 확인 조건 체크
                if frame_text == 'm':
                    h_condition = True
                    m_condition = True if int(str(self.now)[-12:-10]) % frame_num == 0 else False
                elif frame_text == 'h':
                    h_condition = True if int(str(self.now)[-15:-13]) % frame_num == 0 else False
                    m_condition = True if int(str(self.now)[-12:-10]) == 0 else False

            if redundancy == None: # 2번 요청하지 않기 위한 리던던시
                if h_condition and m_condition:
                    self.df = trader.candle_data(TIME_FRAME, REQ_LIMIT)
                    candle_condition = self.df['Close'].iloc[-2] - self.df['Open'].iloc[-2]
                    if self.status == NEUTRAL:
                        if candle_condition < 0:
                            if self.df['Close'].iloc[-2] + (abs(candle_condition) * CONDITION_RATE) <= self.df['Close'].iloc[-1] <= self.df['Open'].iloc[-2]:
                                signal = LONG
                        elif candle_condition > 0:
                            if self.df['Close'].iloc[-2] - (abs(candle_condition) * CONDITION_RATE) >= self.df['Close'].iloc[-1] >= self.df['Open'].iloc[-2]:
                                signal = SHORT

                    elif self.status == LONG: # 진입평균가 1% ATR 추가해야됨
                        if candle_condition < 0:
                            if self.df['Close'].iloc[-2] + (abs(candle_condition) * CONDITION_RATE) <= self.df['Close'].iloc[-1] <= self.df['Open'].iloc[-2]:
                                signal = LONG

                    elif self.status == SHORT:
                        if candle_condition > 0:
                            if self.df['Close'].iloc[-2] - (abs(candle_condition) * CONDITION_RATE) >= self.df['Close'].iloc[-1] >= self.df['Open'].iloc[-2]:
                                signal = SHORT
                    redundancy = str(self.now)[:-7]
                else:
                    if redundancy != str(self.now)[:-7]:
                        redundancy = None

            return signal
            

        except Exception as e:
            print(e)

    def safe1(self):
        """"""
    
    def safe2(self):
        """"""

    async def run(self):
        tasks = [trader.administrator()]
        result = await asyncio.gather(*tasks)
        print(result)



if __name__ == "__main__":
    try:
        if not API_KEY or not API_SECRET:
            logging.error('Set API_KEY and API_SECRET')
        else:
            trader = Trader()
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.run(trader.run())
    except Exception as e:
        logging.error(traceback.format_exc())