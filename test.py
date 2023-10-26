import time
import math
import asyncio
import logging
import traceback
import pandas as pd
import ccxt
import ccxt.pro as ccxtpro
from ta import volatility
from datetime import datetime
from datetime import timedelta
from binance import client
from binance.error import ClientError
from binance.um_futures import UMFutures
from binance import AsyncClient, BinanceSocketManager
from binance.lib.utils import config_logging
from PyQt5.QtCore import QThread, pyqtSignal
from consts import *
import decorator


config_logging(logging, logging.INFO)

class Test():
    def __init__(self):
        self.binance = UMFutures(key=API_KEY, secret=API_SECRET)
        self.signal = None
        self.g_position = None
        
    def get_liquidation_percent(self):
        
        try:
            exchange = ccxt.binance(config={
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
            })
            self.signal = LONG
            self.g_position = 25000
            
            while True:
                positions = exchange.fetch_positions(symbols=[SYMBOL])

                if self.signal == LONG:
                    liquidation = float(positions[1]['info']['liquidationPrice'])
                elif self.signal == SHORT:
                    liquidation = float(positions[2]['info']['liquidationPrice'])

                self.liquidation_per = (liquidation - self.g_position) / self.g_position
                
                if self.liquidation_per != None:
                    break
                time.sleep(0.5)
                
            logging.info(self.liquidation_per)
        except Exception as e:
            logging.error(traceback.format_exc())
    
    def test_function(self):
        
        try:
            s = True
            d = False
            if s == True:
                s = True
            if d == False:
                d = False
                
            return [s, d]
        except Exception as e:
            logging.error(traceback.format_exc())
            
    @decorator.call_binance_api
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

        return df        
    

if __name__ == '__main__':
    now = datetime.now()
    test = Test()
    df = test.candle_data(TIME_FRAME,20)
    print(df)