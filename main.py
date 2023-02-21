import time
import asyncio
import logging
import traceback
import pandas as pd
import ccxt.pro as ccxtpro
from ta import volatility
from datetime import datetime
from binance import AsyncClient, BinanceSocketManager
from binance.um_futures import UMFutures
from binance.lib.utils import config_logging
from consts import *
import decorator


config_logging(logging, logging.INFO)

class Trader():
    def __init__(self):
        #관리자 전역변수
        self.binance = UMFutures(key=API_KEY, secret=API_SECRET)
        self.status = NEUTRAL
        self.now = None
        self.price = 0
        self.redundancy = None

        #시그날 전역변수
        self.signal = None
        self.df = None
        self.close_price = None
        self.atr = None
        self.order_minimum_space = None
        
        #진입관리 매니지먼트 전역변수
        self.general = False
        self.general_stage = None
        self.general_orderlist = {}
        self.general_pricelist = {}
        


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
        df['Atr'] = volatility.average_true_range(high=df['High'],low=df['Low'],close=df['Close'])
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
            res_price = await exchange.watch_ticker(SYMBOL)
            res_orderbook = await exchange.watch_order_book(TICKER)
            top_bid = float(res_orderbook['bids'][0][1])
            top_ask = float(res_orderbook['asks'][0][1])
            time_stamp = datetime.fromtimestamp(int(res_price['timestamp']) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            self.now = time_stamp
            self.price = res_price['close']
            
            if str(self.now)[-2:] == '00':
                if self.redundancy == None: # 2번 요청하지 않기 위한 리던던시
                    self.signal = self.signal_generator()
                    self.redundancy = str(self.now)[:-2]
                else:
                    if self.redundancy != str(self.now)[:-2]:
                        self.redundancy = None
            self.general_management()

            print(time_stamp, 'price:',self.price,'signal:', self.signal)


    def signal_generator(self):

        frame_num = int(TIME_FRAME[:-1])
        frame_text = TIME_FRAME[-1]
        result = {}
        try:
            if self.general == False:
                if TIME_FRAME: # 시그널 확인 조건 체크
                    if frame_text == 'm':
                        h_condition = True
                        m_condition = True if int(str(self.now)[-5:-3]) % frame_num == 0 else False
                    elif frame_text == 'h':
                        h_condition = True if int(str(self.now)[-8:-6]) % frame_num == 0 else False
                        m_condition = True if int(str(self.now)[-5:-3]) == 0 else False

                    if h_condition and m_condition:
                        self.df = trader.candle_data(TIME_FRAME, REQ_LIMIT)
                        candle_condition = self.df['Close'].iloc[-2] - self.df['Open'].iloc[-2]
                        if self.status == NEUTRAL:
                            if candle_condition < 0:
                                if self.df['Close'].iloc[-2] + (abs(candle_condition) * CONDITION_RATE) <= self.df['Close'].iloc[-1] <= self.df['Open'].iloc[-2]:
                                    result['signal'] = LONG
                            elif candle_condition > 0:
                                if self.df['Close'].iloc[-2] - (abs(candle_condition) * CONDITION_RATE) >= self.df['Close'].iloc[-1] >= self.df['Open'].iloc[-2]:
                                    result['signal'] = SHORT

                        elif self.status == LONG: # 진입평균가 1% ATR 추가해야됨
                            if candle_condition < 0:
                                if self.df['Close'].iloc[-2] + (abs(candle_condition) * CONDITION_RATE) <= self.df['Close'].iloc[-1] <= self.df['Open'].iloc[-2]:
                                    result['signal'] = LONG
                        elif self.status == SHORT:
                            if candle_condition > 0:
                                if self.df['Close'].iloc[-2] - (abs(candle_condition) * CONDITION_RATE) >= self.df['Close'].iloc[-1] >= self.df['Open'].iloc[-2]:
                                    result['signal'] = SHORT
                        
                        result['close_price'] = self.df['Close'].iloc[-1]
                        result['atr'] = self.df['Atr'].iloc[-1]
                        result['mingap'] = (result['close_price']*GAP_PERCENT if result['close_price'] >= result['atr'] else result['atr'])/GENERAL_DIV
                        
                    return result
            
        except Exception as e:
            logging.error(traceback.format_exc())

    def general_management(self):

        if self.general == False and self.signal:
            self.general = True
        
        if self.general == True:#매니지먼트가 실행중인지 확인
            #실행중이라면
                if self.general_orderlist == {}: #주문이 있는지 확인
                    """"""
                    test = self.close_price
                    #주문이 없다면
                        # self.general_order(self.signal[0], 24700, 0.001,"test11") #G주문
                    #주문이 있다면 (겟뉴오더 클라이언트 오더아이디가 제너럴이 있는지 확인)
                        #패스(체결 기다림)

            #실행중이 아니라면
                #패스
            
    
    @decorator.call_binance_api
    def general_order(self, signal, order_price, qty, coid):

        order = self.binance.new_order(
            symbol=SYMBOL,
            type="LIMIT",
            side=SIGNAL_TO_OPEN_SIDE[signal],
            PositionSide=[signal],
            price=order_price,
            quantity=qty,
            timeInForce="GTC",
            newClientOrderId=coid
        )
        self.general_orderlist['{coid}'] = order['orderId'] #주문 후 오더리스트에 오더 저장

    def safe1(self):
        """"""
    
    def safe2(self):
        """"""

    async def run(self):
        tasks = [trader.administrator()]
        result = await asyncio.gather(*tasks)
        print(result)

    async def test(self):
        trader.general_order(LONG, 24700, 0.001,"test11")



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