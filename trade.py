import time
import math
import asyncio
import logging
import traceback
import pandas as pd
import ccxt
import ccxt.pro as ccxtpro
import decorator
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


#로그 파일 시간자동입력 클래스
class CustomFileHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding=None, delay=False):
        now = datetime.now()
        timestamp = now.strftime('%Y%m%d%H%M%S')
        base_dir = os.path.dirname(filename)
        base_name = os.path.basename(filename)
        new_filename = f"{timestamp}_{base_name}"
        new_filepath = os.path.join(base_dir, new_filename)
        
        super().__init__(new_filepath, mode=mode, encoding=encoding, delay=delay)

# 로거 생성 및 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Formatter 설정 (시간 포함)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# 콘솔 핸들러 생성 및 추가
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 파일 핸들러 생성 및 추가 (filemode='w' 적용)
file_handler = CustomFileHandler('alrgo\logs\log.txt', mode='a')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


#트레이드 클래스
class Trader(QThread):
    def __init__(self):
        #전역변수
        super().__init__()
        self.binance = UMFutures(key=API_KEY, secret=API_SECRET)
        self.status = NEUTRAL
        self.division = None
        self.position = None
        self.entry_list = None
        self.signal_history = None
        self.g_position = None
        self.h_position = None
        self.lastest_g_order = None
        self.liquidation_per = None
        self.signal = None
        self.price = None
        self.top_ask = None
        self.top_bid = None
        self.cycle = None
        self.now = None
        self.check_time = None
        self.redundancy = None
        self.min_qty = None
        self.decimal = None
        self.spread = None
        self.spare_pnl = 0
        self.is_init_success = False
        self.init_data() #첫 실행시 입력 위한것

        #entry 변수
        self.stg = None
        self.unit = None
        self.pre_h = None
        self.pre_h_exit = None
        self.g_detail_count = None
        self.h_detail_count = None
        self.signal_time = None
        self.g_avg_price = None
        self.h_avg_price = None
        self.g_total_qty = None
        self.h_total_qty = None
        self.general_price = None
        self.general_qty = None
        self.hedge_price = None
        self.hedge_qty = None
        self.g_entry_order_count = None
        self.h_entry_order_count = None
        self.next_price = None
        self.g_prep = [] # dv 의 stg 를 5개로 나누눈 수량위해 만듦
        self.h_prep = []
        self.g_order_price = [] # prep의 체결을 가져옴
        self.g_order_qty = []
        self.h_order_price = []
        self.h_order_qty = []
        self.hedge_list = []
        self.g_history = {}
        self.h_history = {}
        self.g_entry_history = {}
        self.h_entry_history = {}
        self.g_slippage = 0
        self.h_slippage = 0
        self.t_slippage = 0
        self.g_entry_order_check = False
        self.h_entry_order_check = False


    def init_data(self):
        """
        트레이딩에 필요한 기능 초기화
        :return:
        """
        try:
            logging.info('init_data starts')
            # 초기화할 기능
            self.set_leverage()  # 레버리지 설정
            self.set_margin_type()  # 마진타입 설정
            self.get_position()  # 포지션 조회
            self.get_balance()  # 잔고 조회
            self.get_min_order_qty()  # 최소주문수량 조회
            self.get_min_balance_calculator()  # 최소 필요수량 계산 (바이낸스버전)
            self.get_spread()  # 스프레드 조회
            self.signal_history = {}
            self.is_init_success = True  # 초기화함수 완료
        except Exception as e:
            logging.error(traceback.format_exc())

    #엔트리 리셋(지금상태는0단계일때만)
    def entry_reset(self):
        self.signal = None
        self.stg = None
        self.unit = None
        self.g_detail_count = None
        self.h_detail_count = None
        self.signal_time = None
        self.g_avg_price = None
        self.h_avg_price = None
        self.g_total_qty = None
        self.h_total_qty = None
        self.general_price = None
        self.general_qty = None
        self.hedge_price = None
        self.hedge_qty = None
        self.g_entry_order_count = None
        self.h_entry_order_count = None
        self.next_price = None
        self.g_prep = []
        self.h_prep = []
        self.g_order_price = []
        self.g_order_qty = []
        self.h_order_price = []
        self.h_order_qty = []
        self.hedge_list = []
        self.g_history = {}
        self.h_history = {}
        self.g_slippage = 0
        self.h_slippage = 0
        self.t_slippage = 0
        self.g_entry_order_check = False
        self.h_entry_order_check = False
        if self.pre_h != None:
            if self.status == LONG:
                if self.pre_h['price'] < self.price:
                    self.pre_h_exit_order(self,side=self.status,qty=self.pre_h['qty'])
            elif self.status == SHORT:
                if self.pre_h['price'] > self.price:
                    self.pre_h_exit_order(self,side=self.status,qty=self.pre_h['qty'])

    #사이클리셋
    def cycle_reset(self):
        """
        사이클 끝났을 때 필요 기능 초기화
        """
        try:
            logging.info('Cycle reset')
            self.get_balance()
            self.get_position()
            self.status = NEUTRAL
        except Exception as e:
            logging.error(traceback.format_exc())

    #레버리지설정
    @decorator.call_binance_api
    def set_leverage(self):
        """
        레버리지 설정
        :return:
        """
        try:
            logging.info('set_leverage starts')
            self.position = self.binance.get_position_risk(symbol=SYMBOL)
            cur_long_leverage = self.position[0]['leverage']
            cur_short_leverage = self.position[1]['leverage']
            cur_long_positionAmt = self.position[0]['positionAmt']
            cur_short_positionAmt = self.position[1]['positionAmt']
            if abs(float(cur_long_positionAmt)) + abs(float(cur_short_positionAmt)) == 0:
                if cur_long_leverage or cur_short_leverage != LEVERAGE:
                    res = self.binance.change_leverage(symbol=SYMBOL, leverage=LEVERAGE, recvWindow=6000)
                    logging.info(res)
                else:
                    logging.info('leverage :', LEVERAGE)
            else:
                raise ValueError
                
        except ValueError as ve:
            logging.info('Need to close position')
            logging.error(traceback.format_exc())
        except Exception as e:
            logging.error(traceback.format_exc())

    #마진타입설정
    @decorator.call_binance_api
    def set_margin_type(self):
        """
        마진타입 설정
        :return:
        """
        try:
            logging.info('set_margin_type starts')
            cur_margintype = self.position[0]['marginType']
            upr = cur_margintype.upper()
            if upr != MARGIN_TYPE:
                res = self.binance.change_margin_type(symbol=SYMBOL, marginType=MARGIN_TYPE, recvWindow=6000)
                logging.info(res)
            else:
                logging.info('margin_type is checked')
        except Exception as e:
            logging.error(traceback.format_exc())

    #밸런스확인
    @decorator.call_binance_api
    def get_balance(self):
        """
        잔고 조회
        :return:
        """
        try:
            logging.info('get_balance')
            res = self.binance.account(recvWindow=6000)
            res_ = list(filter(lambda a: a['asset'] == 'USDT', res['assets']))
            self.balance = res_[0]['availableBalance']
            self.balance = 16000 #테스트용 지워야함
            logging.info(self.balance)
        except Exception as e:
            logging.error(traceback.format_exc())

    #포지션확인
    @decorator.call_binance_api
    def get_position(self):
        """
        포지션 조회
        :return:
        """
        try:
            logging.info('get_position')
            res = self.binance.account(recvWindow=6000)
            res = list(filter(lambda a: a['symbol'] == SYMBOL, res['positions']))
            self.position = res if len(res) > 0 and float(res[1]['positionAmt']) != 0 else None
            logging.info(self.position)
        except Exception as e:
            logging.error(traceback.format_exc())

    #거래가능금액 계산기
    @decorator.call_binance_api
    def get_min_balance_calculator(self):
        try:
            logging.info('needed balance')
            need = sum(G_RATE_LIST)*self.min_qty
            price = float(self.get_price())
            result = need*CONST*price/LEVERAGE/(RATE_LIST[2] if RATE_LIST[2] < 1 else 1)*1.05
            result = format(result, '.4f')
            logging.info(result)
        except Exception as e:
            logging.error(traceback.format_exc())

    #최소주문금액확인
    @decorator.call_binance_api
    def get_min_order_qty(self):
        """
        최소주문수량 조회
        """
        try:
            logging.info('get_minimum_order_qty')
            exinfo = self.binance.exchange_info() # 심볼코인 정보 요청 API
            exinfo_filter = list(filter(lambda a: a['symbol'] == SYMBOL, exinfo['symbols']))
            limit_exinfo = exinfo_filter[0]['filters'][1]
            self.min_qty = float(limit_exinfo['minQty']) #리미트 주문시 최소주문 수량
            decimal = str(self.min_qty).index('.')
            self.decimal = len(str(self.min_qty)[decimal+1:])
            logging.info(self.min_qty)
        except Exception as e:
            logging.error(traceback.format_exc())

    #스프레드 확인
    @decorator.call_binance_api
    def get_spread(self):
        try:
            logging.info('check spread')
            price = str(float(self.get_price()))
            idx = price.index('.')
            spread = price[idx+1:]
            self.spread = len(spread)
            logging.info(self.spread)
        except Exception as e:
            logging.error(traceback.format_exc())

    #시그널 발생기
    def signal_generator(self):

        try:
            if self.signal == None:
                result = self.signal
                safe1 = self.safe_manager(price=self.price,safe1=SAFE1_PER)
                if safe1 == True:
                    print('safe1발동 시그널생성')
                    result = {}
                    result['Signal']
                    result['Close'] = self.price
                    result['Atr'] = result['Close']*GAP_PERCENT
                    result['Mingap'] = (result['Close']*GAP_PERCENT if result['Close']*GAP_PERCENT >= result['Atr'] else result['Atr'])/GENERAL_STG
                else:
                    if str(self.now)[-5:-3] != str(self.check_time) and self.check_time != None:
                        if self.redundancy == None: # 2번 요청하지 않기 위한 리던던시
                            if TIME_FRAME: # 시그널 확인 조건 체크
                                frame_num = int(TIME_FRAME[:-1])
                                frame_text = TIME_FRAME[-1]
                                if frame_text == 'm':
                                    h_condition = True
                                    m_condition = True if int(str(self.now)[-5:-3]) % frame_num == 0 else False
                                elif frame_text == 'h':
                                    h_condition = True if int(str(self.now)[-8:-6]) % frame_num == 0 else False
                                    m_condition = True if int(str(self.now)[-5:-3]) == 0 else False

                                if h_condition and m_condition:
                                    print(self.now,'safe1 발동안함 시그널 체크')
                                    self.df = self.candle_data(TIME_FRAME, REQ_LIMIT)
                                    result = {}
                                    result['Close'] = self.df['Close'].iloc[-1]
                                    result['Atr'] = float(format(self.df['Atr'].iloc[-1],'.{}f'.format(self.decimal)))
                                    result['Mingap'] = float(format(((result['Close']*GAP_PERCENT) if result['Close']*GAP_PERCENT >= result['Atr'] else result['Atr'])/GENERAL_STG,'.{}f'.format(self.decimal)))
                                    candle_condition = self.df['Close'].iloc[-3] - self.df['Open'].iloc[-3]
                                    candle_condition2 = self.df['Close'].iloc[-2] - self.df['Open'].iloc[-3]
                                    last_close = self.df['Close'].iloc[-1]
                                    last_open = self.df['Open'].iloc[-1]
                                    last2_close = self.df['Close'].iloc[-2]
                                    last2_open = self.df['Open'].iloc[-2] # 테스트 확인용
                                    if self.status == NEUTRAL:
                                        if candle_condition < 0:
                                            if self.df['Close'].iloc[-2] + (abs(candle_condition) * CONDITION_RATE) <= self.df['Close'].iloc[-1] <= self.df['Open'].iloc[-2]:
                                                result['Signal'] = LONG
                                            else:
                                                result = None
                                        elif candle_condition > 0:
                                            if self.df['Close'].iloc[-2] - (abs(candle_condition) * CONDITION_RATE) >= self.df['Close'].iloc[-1] >= self.df['Open'].iloc[-2]:
                                                result['Signal'] = SHORT
                                            else:
                                                result = None
                                        else:
                                            print('candle_con1-1 :',candle_condition) #테스트용
                                            result = None
                                    elif self.status == LONG: # 진입가 1% ATR 추가해야됨(완료)
                                        if self.lastest_g_order - self.signal_history[max(self.signal_history.keys())]['Mingap']*GENERAL_STG >= result['Close']: #최소 주문가능거리보다 밑인가?
                                            if candle_condition <= 0: # 이전봉이 음봉인가?
                                                if self.df['Close'].iloc[-2] + (abs(candle_condition) * CONDITION_RATE) <= self.df['Close'].iloc[-1] <= self.df['Open'].iloc[-2]: #5% 안에 드는가?
                                                    if self.pre_h == None: #pre_h가 없는가?
                                                        print('long - pre_h 없음')
                                                        result['Signal'] = LONG
                                                    else:
                                                        if self.check_signal(price=self.price, fomula=(self.pre_h['price'])): # pre_h가 있는경우에는 그보다 낮은가격에서만 시그널 생성
                                                            print('long - pre_h 조건충족')
                                                            result['Signal'] = LONG
                                                        else:
                                                            print('long - pre_h 조건미충족')
                                                            result = None
                                                else:
                                                    logging.info(f'long - 봉조건 불충족/last_open:{last_open} last_close:{last_close} last2_open:{last2_open} last2_close:{last2_close}')
                                                    result = None
                                            else:
                                                logging.info(f'long - 이전봉이 양봉/last_open:{last_open} last_close:{last_close} last2_open:{last2_open} last2_close:{last2_close}')
                                                result = None
                                        else:
                                            print('long - 최소거리미달(', self.lastest_g_order - self.signal_history[max(self.signal_history.keys())]['Mingap']*GENERAL_STG,')')
                                            result = None

                                    elif self.status == SHORT:
                                        if self.lastest_g_order + self.signal_history[max(self.signal_history.keys())]['Mingap']*GENERAL_STG <= result['Close']:
                                            if candle_condition >= 0:
                                                if self.df['Close'].iloc[-2] - (abs(candle_condition) * CONDITION_RATE) >= self.df['Close'].iloc[-1] >= self.df['Open'].iloc[-2]:
                                                    if self.pre_h == None:
                                                        print('short - pre_h 없음 :',candle_condition2)
                                                        result['Signal'] = SHORT
                                                    else:
                                                        if self.check_signal(price=self.price, fomula=(self.pre_h['price'])):
                                                            print('short - pre_h 조건충족 :',candle_condition2)
                                                            result['Signal'] = SHORT
                                                        else:
                                                            print('short - pre_h 조건미충족')
                                                            result = None
                                                else:
                                                    logging.info(f'short - 봉조건 불충족/last_open:{last_open} last_close:{last_close} last2_open:{last2_open} last2_close:{last2_close}')
                                                    result = None
                                            else:
                                                logging.info(f'short - 이전봉이 음봉/last_open:{last_open} last_close:{last_close} last2_open:{last2_open} last2_close:{last2_close}')
                                                result = None
                                        else:
                                            print('short - 최소거리미달(', self.lastest_g_order + self.signal_history[max(self.signal_history.keys())]['Mingap']*GENERAL_STG,')')
                                            result = None


                                    if REVERSE_SIGNAL == True: #리버스 시그날
                                        if result != None:
                                            if result['Signal'] == LONG:
                                                result['Signal'] = SHORT
                                            elif result['Signal'] == SHORT:
                                                result['Signal'] = LONG
                                    if result != None:
                                        if self.status == LONG: # 진행중일때 반대쪽 시그널 무시
                                            if result['Signal'] == SHORT:
                                                result = None
                                        elif self.status == SHORT:
                                            if result['Signal'] == LONG:
                                                result = None


                            self.redundancy = str(self.now)
                    else:
                        if self.redundancy != str(self.now):
                            self.redundancy = None
            else:
                result = self.signal
            
            if self.signal == None:
                if result != None:
                    logging.info(f'@@@{self.now}시그널발생:{result}@@@')
                    if self.division == None:
                        self.signal_history[0] = result
                    else:
                        self.signal_history[self.division] = result
                    print(self.now, result) #시그널 발생시 시간과 시그널 찍음
            

            return result
            
        except Exception as e:
            logging.error(traceback.format_exc())

    #시그널 확인
    def check_signal(self,price,fomula=None):
        s_price = price
        s_fomula = fomula
        if s_fomula == None:
            if self.signal['Signal'] == LONG:
                s_fomula = self.general_price[self.stg] - self.h_slippage
            elif self.signal['Signal'] == SHORT:
                s_fomula = self.general_price[self.stg] + self.h_slippage

        if self.signal != None:
            if self.signal['Signal'] == LONG:
                if s_price <= s_fomula:
                    result = True
                else:
                    result = False
            elif self.signal['Signal'] == SHORT:
                if s_price >= s_fomula:
                    result = True
                else:
                    result = False
        else:
            if self.status == LONG:
                if s_price <= s_fomula:
                    result = True
                else:
                    result = False
            elif self.status == SHORT:
                if s_price >= s_fomula:
                    result = True
                else:
                    result = False

        # if fomula == None:
        #     print(self.now, result, s_price)
        
        return result

    #캔들정보확인
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

    #리스트 생성기
    def create_entry_list(self):
            
            try:
                logging.info('create_entry_list')
                pre_entry_list = []
                entry_list = {}
                able_balance = float(self.balance)*0.95
                price = self.signal['Close']
                able_coin = able_balance / float(price) * LEVERAGE

                for div in range(DIVISION):
                    if div == 0:
                        pre_entry_list.append(float(format(LEVERAGE*able_balance/(price*CONST), '.{}f'.format(self.decimal))))
                    else:
                        pre_entry_list.append(float(format(sum(pre_entry_list)*RATE_LIST[div], '.{}f'.format(self.decimal))))
                
                for i in range(len(pre_entry_list)):
                    entry_list[i] = pre_entry_list[i]
                
                if entry_list[1] < sum(G_RATE_LIST)*self.min_qty:
                    raise ValueError
                
                entry_list[0] = 0.005 #테스트용 지워야함
                logging.info(entry_list)
                return entry_list
            
            except ValueError:
                print('Not enough balance')
            except Exception as e:
                logging.error(traceback.format_exc())

    #1회성 가격 검색
    def get_price(self):
        coin_info = self.binance.ticker_price(SYMBOL)
        coin_price = coin_info['price'] # coin_info['close'] == coin_info['last'] 

        return coin_price

    #비연동 가격수신매니저
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
            await asyncio.sleep(0.1)
            res_price = await exchange.watch_ticker(SYMBOL)
            res_orderbook = await exchange.watch_order_book(TICKER)
            self.top_bid = float(res_orderbook['bids'][0][1])
            self.top_ask = float(res_orderbook['asks'][0][1])
            time_stamp = datetime.fromtimestamp(int(res_price['timestamp']) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            self.now = time_stamp
            self.price = res_price['close']
            self.signal = self.signal_generator()
            self.check_time = str(self.now)[-5:-3]

    #체결관리
    async def order_handler(self):
        """
        주문관리
        """
        
        client = await AsyncClient.create(API_KEY, API_SECRET)
        bm = BinanceSocketManager(client)
        ts = bm.futures_user_socket()

        async with ts as tscm:
            while True:#변경해야됨
                try:
                    event = await tscm.recv()
                    if event['e'] == 'ORDER_TRADE_UPDATE' and event['o']['X'] == 'FILLED': #Limit에서 새로 주문넣었을때는 NEW로 구분가능
                        if event['o']['o'] == MARKET and event['o']['c'] == 'pre_h':
                            self.pre_h = {}
                            self.pre_h['price'] = float(event['o']['ap'])
                            self.pre_h['qty'] = float(event['o']['q'])
                            self.order_close_catcher(event)
                        elif event['o']['o'] == MARKET and event['o']['c'] == 'pre_h_exit':
                            self.pre_h['exit_price'] = float(event['o']['ap'])
                            self.order_close_catcher(event)
                        elif event['o']['o'] == MARKET and event['o']['c'] == 'entry_g':
                            self.g_order_price.append(float(event['o']['ap']))
                            self.g_order_qty.append(float(event['o']['q']))
                            self.order_close_catcher(event)
                        elif event['o']['o'] == MARKET and event['o']['c'] == 'entry_h':
                            self.h_order_price.append(float(event['o']['ap']))
                            self.h_order_qty.append(float(event['o']['q']))
                            self.order_close_catcher(event)
                    # if event['e'] == 'ORDER_TRADE_UPDATE' and event['o']['X'] == 'NEW':
                        # if event['o']['o'] == LIMIT and event['o']['ps'] == SHORT: #gw_order 주문
                        #     self.g_order_id = event['o']['i']
                        # elif event['o']['o'] == LIMIT and event['o']['ps'] == SHORT: #gw_order 체결
                        #     self.g_order_status = True
                        # elif event['o']['o'] == MARKET and event['o']['ps'] == LONG: #p_order 체결
                        #     self.p_order_status = True
                        # elif event['o']['o'] == MARKET and event['o']['ps'] == SHORT: 
                        #     if event['o']['c'] == "entry": # entry_order 체결
                        #         self.standard_price = float(event['o']['ap'])
                        #     else: # gf_order 체결
                        #         self.last_order_price = float(event['o']['ap'] )
                    # elif event['e'] == 'ORDER_TRADE_UPDATE' and event['o']['X'] == 'CANCELED':
                    #     if event['o']['o'] == LIMIT and event['o']['ps'] == SHORT: #gw_order 취소
                    #         self.g_order_id = None
                    #     elif event['o']['o'] == LIMIT and event['o']['ps'] == LONG: #p_order 취소
                    #         self.p_order_id = None

                except Exception as e:
                    logging.error(traceback.format_exc())

    def order_close_catcher(self,close_data):
        data = close_data
        if data['o']['c'] == 'entry_g':
            logging.info('time: %s symbol: %s side: %s price: %s size: %s type: %s / %s status: %s division: %d -%d g_count: %d',
            datetime.fromtimestamp(int(data['T']) / 1000).strftime('%Y-%m-%d %H:%M:%S'),
            data['o']['s'],
            data['o']['ps'],
            data['o']['ap'],
            data['o']['q'],
            data['o']['o'],
            data['o']['c'],
            data['o']['X'],
            self.division,
            self.stg,
            self.g_detail_count)
        
        elif data['o']['c'] == 'entry_h':    
            logging.info('time: %s symbol: %s side: %s price: %s size: %s type: %s / %s status: %s division: %d -%d h_count: %d',
            datetime.fromtimestamp(int(data['T']) / 1000).strftime('%Y-%m-%d %H:%M:%S'),
            data['o']['s'],
            data['o']['ps'],
            data['o']['ap'],
            data['o']['q'],
            data['o']['o'],
            data['o']['c'],
            data['o']['X'],
            self.division,
            self.stg,
            self.h_detail_count)

            #원래는 print로 했을 때 제대로 동작한 코드임 로깅으로 바꾸면서 수정
            # logging.info('time:', datetime.fromtimestamp(int(data['T']) / 1000).strftime('%Y-%m-%d %H:%M:%S'), 
            #     'symbol:', data['o']['s'], 
            #     'side:', data['o']['ps'],
            #     'price:', data['o']['ap'],
            #     'size:', data['o']['q'],
            #     'type:', data['o']['o'],'/', data['o']['c'],
            #     'status:', data['o']['X'],
            #     'division:', self.division, '-', self.stg,
            #     'g_count:', self.g_detail_count
            #     )

            # logging.info('time:', datetime.fromtimestamp(int(data['T']) / 1000).strftime('%Y-%m-%d %H:%M:%S'), 
            #     'symbol:', data['o']['s'], 
            #     'side:', data['o']['ps'],
            #     'price:', data['o']['ap'],
            #     'size:', data['o']['q'],
            #     'type:', data['o']['o'],'/', data['o']['c'],
            #     'status:', data['o']['X'],
            #     'division:', self.division, '-', self.stg,
            #     'h_count:', self.h_detail_count
            #     )



    #제너럴 내부가격 생성함수
    def general_price_creator(self,signal):
        try:
            logging.info('create general price')
            gpc_signal = signal
            result = {}
            if self.division == 0: #최초진입일 경우
                result['Signal'] = gpc_signal['Close']
                result[0] = gpc_signal['Close']
            else: #디비전이 1 이상일 경우
                if signal['Signal'] == LONG: #시그널이 롱인경우
                    for i in range(GENERAL_STG+1):
                        if i == 0:
                            result['Signal'] = gpc_signal['Close'] #시그널가격입력
                        else:
                            p = gpc_signal['Close'] - (gpc_signal['Mingap']) * (i) #시그널에서부터 민갭만큼 떨어트려서 간격설정
                            result[i-1] = float(format(p,'.{}f'.format(self.spread)))

                elif signal['Signal'] == SHORT:
                    for i in range(GENERAL_STG+1):
                        if i == 0:
                            result['Signal'] = gpc_signal['Close']
                        else:
                            p = gpc_signal['Close'] + (gpc_signal['Mingap']) * (i+1)
                            result[i-1] = float(format(p,'.{}f'.format(self.spread)))
            logging.info(result)
            return result
        except Exception as e:
            logging.error(traceback.format_exc())
    
    #제너럴 내부수량 생성함수
    def general_qty_creator(self, signal, qty):
        try:
            logging.info('create general qty')
            gqc_signal = signal
            gqc_qty = qty
            self.unit = float(format(gqc_qty/sum(G_RATE_LIST),'.{}f'.format(self.decimal)))
            result = {}
            if self.division == 0:
                result[0] = gqc_qty
            else:
                for i in range(GENERAL_STG):
                    result[i] = self.unit*G_RATE_LIST[i]
                rest = float(format(gqc_qty-sum(result.values()),'.{}f'.format(self.decimal)))
                if rest > 0:
                    rest_d = int(format((rest/self.min_qty),'.{}f'.format(0)))
                    count = 0
                    for l in range(rest_d):
                        if count < 2:
                            result[i] = float(format((result[i]+self.min_qty),'.{}f'.format(self.decimal)))
                            rest_d -= 1
                            count += 1
                        else:
                            result[i-1] = float(format((result[i-1]+self.min_qty),'.{}f'.format(self.decimal)))
                            rest_d -= 1
                            count = 0

            logging.info(result)
            return result
        except Exception as e:
            logging.error(traceback.format_exc())

    #헷지 내부수량 생성함수
    def hedge_qty_creator(self,g_qty):
        try:
            logging.info('create hedge qty')
            result = {}
            gq = g_qty
            gqty = 0
            for g in range(len(gq)):
                gqty += gq[g]
            div = 0
            for d in range(DIVISION-1):
                div += d
            rate = (100 - H_RATE)/div
            h_qty = float(format((gqty * (100 - rate*(self.division-1))*0.01),'.{}f'.format(self.decimal)))
            unit_hqty = float(format(((h_qty//(HEDGE_STG*0.1**self.decimal))*0.1**self.decimal),'.{}f'.format(self.decimal)))
            rest = HEDGE_STG - int(((h_qty-(unit_hqty*HEDGE_STG))*10**self.decimal))
            if self.division == 0:
                result[0] = 0
            else:
                for i in range(HEDGE_STG):
                    if i == 0:
                        if self.pre_h != None:
                            result[i] = float(format((unit_hqty - self.pre_h['qty']),'.{}f'.format(self.decimal)))
                        else:
                            result[i] = unit_hqty
                    else:
                        if unit_hqty*HEDGE_STG != h_qty:
                            if i < rest:
                                result[i] = unit_hqty
                            else:
                                result[i] = float(format((unit_hqty + self.min_qty),'.{}f'.format(self.decimal)))
                        else:
                            result[i] = unit_hqty
            logging.info(result)
            return result
        except Exception as e:
            logging.error(traceback.format_exc())
    
    #프리H 주문 넣는 함수
    @decorator.call_binance_api
    async def pre_h_order(self, signal, price, qty):
        
        try:
            pre_h_qty = qty
            pre_h_qty = float(format(pre_h_qty/2,'.{}f'.format(self.decimal)))
            logging.info('pre_h_order')
            order = self.binance.new_order(
                symbol=SYMBOL,
                type=MARKET,
                side=HEDGE_TO_OPEN_SIDE[signal],
                PositionSide=HEDGE_TO_POSITION_SIDE[signal],
                quantity=pre_h_qty,
                newClientOrderId='pre_h'
            )
            while True:
                await asyncio.sleep(0.01)
                if self.pre_h != None:
                    break
            slical = 0
            if self.signal != None:
                slical = float(format((self.pre_h['price'] - self.signal['Close']),'.{}f'.format(self.spread)))
                self.h_position['AEP'] = self.pre_h['price']
            self.h_slippage += slical
            self.hedge_qty[0] = qty
            print(signal,'order_price:',price,'avg_price:',self.pre_h['price'],'slippage:',slical,'qty:',qty)
        except Exception as e:
            logging.error(traceback.format_exc())

    #프리H 주문 종료하는 함수 - 이것도 사용안하네
    async def pre_h_exit_order(self,side,qty):

        try:
            logging.info('pre_h_exit')
            if self.pre_h != None:
                pre_h_exit_order = self.binance.new_order(
                    symbol=SYMBOL,
                    type=MARKET,
                    side=HEDGE_TO_CLOSE_SIDE[side],
                    PositionSide=HEDGE_TO_POSITION_SIDE[side],
                    quantity=qty,
                    newClientOrderId='pre_h_exit'
                )
                while True:
                    await asyncio.sleep(0.01)
                    if self.pre_h_exit != None:
                        break
                if self.status == LONG:
                    pnl= self.pre_h['price'] - self.pre_h_exit['Exit_price']
                    self.spare_pnl += pnl
                    self.pre_h_exit = None
                    self.hedge_qty[0] = float(format(self.hedge_qty[0] + qty,'.{}f'.format(self.decimal)))
                    self.pre_h = None
                elif self.status == SHORT:
                    pnl= self.pre_h_exit['Exit_price'] - self.pre_h['price']
                    self.spare_pnl += pnl
                    self.pre_h_exit = None
                    self.hedge_qty[0] = float(format(self.hedge_qty[0] + qty,'.{}f'.format(self.decimal)))
                    self.pre_h = None
                print('order_price:',self.price,'avg_price:',self.pre_h_exit['Exit_price'],'qty:',qty)
        except Exception as e:
            logging.error(traceback.format_exc())

    #g_엔트리 주문 준비
    def g_entry_preparation(self, qty):
        try:
            logging.info('g_prep')
            detail_list = []
            ent_qty = float(f'{(qty//(ENTRY_ORDER_COUNT*self.min_qty))*self.min_qty:.{self.decimal}f}')
            rest = float(f'{qty%(ENTRY_ORDER_COUNT*self.min_qty):.{self.decimal}f}')
            
            if ent_qty != 0: # 0은 5분할 미만이라는 얘기. (0.004)
                if self.g_prep == []:
                    self.g_entry_order_count = ENTRY_ORDER_COUNT
                for i in range(ENTRY_ORDER_COUNT):
                    if rest != 0: # 나머지가 있다면
                        if i >= ENTRY_ORDER_COUNT - int(rest*10**self.decimal): # 나머지가 몇인지 확인해 골고루 퍼트림
                            plus = float(f'{ent_qty+self.min_qty:.{self.decimal}f}')
                            detail_list.append(plus)
                        else:
                            detail_list.append(ent_qty)
                    else:
                        detail_list.append(ent_qty)
            else:
                if self.g_prep == []:
                    self.g_entry_order_count = int(rest*10**self.decimal)
                    for i in range(int(float(rest)*10**self.decimal)):
                        detail_list.append(self.min_qty)
                else:
                    self.g_entry_order_count = len(self.g_prep)
                    adj_qty = float(f'{qty//len(self.g_prep):.{self.decimal}f}')
                    rest = float(f'{qty - adj_qty*len(self.g_prep):.{self.decimal}f}')
                    add = self.min_qty
                    for i in range(len(self.g_prep)):
                        if i == int(float(rest)*10**self.decimal):
                            add += rest
                        detail_list.append(add)

            logging.info(detail_list)
            return detail_list
            
        except Exception as e:
            logging.error(traceback.format_exc())
            
    def h_entry_preparation(self, qty):
        try:
            logging.info('h_prep')
            detail_list = []
            if self.pre_h != None and self.stg == 0:
                qty = qty - self.pre_h['qty']
            ent_qty = float(f'{(qty//(ENTRY_ORDER_COUNT*self.min_qty))*self.min_qty:.{self.decimal}f}')
            rest = float(f'{qty%(ENTRY_ORDER_COUNT*self.min_qty):.{self.decimal}f}')
            
            if ent_qty != 0: # 0은 5분할 미만이라는 얘기. (0.004)
                if self.h_prep == []:
                    self.h_entry_order_count = ENTRY_ORDER_COUNT
                for i in range(ENTRY_ORDER_COUNT):
                    if rest != 0: # 나머지가 있다면
                        if i >= ENTRY_ORDER_COUNT - int(rest*10**self.decimal): # 나머지가 몇인지 확인해 골고루 퍼트림
                            plus = float(f'{ent_qty+self.min_qty:.{self.decimal}f}')
                            detail_list.append(plus)
                        else:
                            detail_list.append(ent_qty)
                    else:
                        detail_list.append(ent_qty)
            else:
                if self.h_prep == []:
                    self.h_entry_order_count = int(rest*10**self.decimal)
                    for i in range(int(float(rest)*10**self.decimal)):
                        detail_list.append(self.min_qty)
                else:
                    self.h_entry_order_count = len(self.h_prep)
                    adj_qty = float(f'{qty//len(self.h_prep):.{self.decimal}f}')
                    rest = float(f'{qty - adj_qty*len(self.h_prep):.{self.decimal}f}')
                    add = self.min_qty
                    for i in range(len(self.h_prep)):
                        if i == int(float(rest)*10**self.decimal):
                            add += rest
                        detail_list.append(add)

            logging.info(detail_list)
            return detail_list
            
        except Exception as e:
            logging.error(traceback.format_exc())

    #g_엔트리 주문 넣는 함수
    @decorator.call_binance_api
    async def g_entry_order(self, signal, g_qty):
        
        try:
            g_ent_qty = g_qty
            logging.info(f'entry_g({self.g_detail_count})')
            if signal == LONG:
                if self.top_ask > g_ent_qty:
                    g_order = self.binance.new_order(
                        symbol=SYMBOL,
                        type=MARKET,
                        side=SIGNAL_TO_OPEN_SIDE[signal],
                        PositionSide=[signal],
                        quantity=g_ent_qty,
                        newClientOrderId='entry_g'
                    )
                    self.g_entry_order_check = True
                    while self.g_entry_order_check == True:
                        await asyncio.sleep(0.1)
                        if len(self.g_order_price) > self.g_detail_count:
                            break #주문 체결데이터가 입력되길 기다림
            elif signal == SHORT:
                if self.top_ask > g_ent_qty:
                    g_order = self.binance.new_order(
                        symbol=SYMBOL,
                        type=MARKET,
                        side=SIGNAL_TO_OPEN_SIDE[signal],
                        PositionSide=[signal],
                        quantity=g_ent_qty,
                        newClientOrderId='entry_g'
                    )
                    self.g_entry_order_check = True
                    while self.g_entry_order_check == True:
                        await asyncio.sleep(0.1)
                        if len(self.g_order_price) > self.g_detail_count:
                            logging.info(f'entry_g({self.g_detail_count})주문결과 order_price:{self.price}, order_qty:{g_ent_qty}')
                            break #주문 체결데이터가 입력되길 기다림
        except Exception as e:
            logging.error(traceback.format_exc())
            
    #h_엔트리 주문 넣는 함수
    @decorator.call_binance_api
    async def h_entry_order(self, signal, h_qty):
        
        try:
            h_ent_qty = h_qty
            logging.info(f'entry_h({self.h_detail_count})')
            if signal == LONG:
                if self.top_bid > h_ent_qty:
                    if self.division > 0:
                        h_order = self.binance.new_order(
                            symbol=SYMBOL,
                            type=MARKET,
                            side=HEDGE_TO_OPEN_SIDE[signal],
                            PositionSide=HEDGE_TO_POSITION_SIDE[signal],
                            quantity=h_ent_qty,
                            newClientOrderId='entry_h'            
                    ) #주문을 하고
                    self.h_entry_order_check = True
                    while self.h_entry_order_check == True:
                        await asyncio.sleep(0.1)
                        if len(self.h_order_price) > self.h_detail_count:
                            break #주문 체결데이터가 입력되길 기다림
            elif signal == SHORT:
                if self.top_bid > h_ent_qty:
                    if self.division > 0:
                        h_order = self.binance.new_order(
                            symbol=SYMBOL,
                            type=MARKET,
                            side=HEDGE_TO_OPEN_SIDE[signal],
                            PositionSide=HEDGE_TO_POSITION_SIDE[signal],
                            quantity=h_ent_qty,
                            newClientOrderId='entry_h'
                        ) #주문을 하고
                    self.h_entry_order_check = True
                    while self.h_entry_order_check == True:
                        await asyncio.sleep(0.1)
                        if len(self.h_order_price) > self.h_detail_count:
                            logging.info(f'entry_h({self.h_detail_count})주문결과 order_price:{self.price}, order_qty:{h_ent_qty}')
                            break #주문 체결데이터가 입력되길 기다림
        except Exception as e:
            logging.error(traceback.format_exc())

    #히스토리 입력 (스테이지의 최대5주문)
    def history_creator(self):
        g_cal = 0
        for i in range(len(self.g_order_price)):
            g_cal += self.g_order_price[i]*self.g_order_qty[i]
        g_qty = float(format(sum(self.g_order_qty),'.{}f'.format(self.decimal)))
        g_price = float(format(g_cal/g_qty,'.{}f'.format(self.spread)))
        self.g_history[self.stg] = {'price':g_price,'qty':g_qty}
        self.g_order_price = []
        self.g_order_qty = []
        if self.h_order_qty != []:
            h_cal = 0
            for i in range(len(self.h_order_price)):
                h_cal += self.h_order_price[i]*self.h_order_qty[i]
            h_qty = float(format(sum(self.h_order_qty),'.{}f'.format(self.decimal)))
            h_price = float(format(h_cal/h_qty,'.{}f'.format(self.spread)))
            self.h_history[self.stg] = {'price':h_price,'qty':h_qty}
            self.h_order_price = []
            self.h_order_qty = []
            
    #엔트리 히스토리 입력 (디비전의 4스테이지)
    def entry_history_creator(self):
        self.g_entry_history[f'div:{self.division}'] = {} #딕셔너리 생성
        for i in range(len(self.g_history)):# 체결한 숫자만큼 엔트리 히스토리 생성
            self.g_entry_history[f'div:{self.division}'][i] = {'price':self.g_history[i]['price'],'qty':self.g_history[i]['qty']}

        self.h_entry_history[f'div:{self.division}'] = {} #딕셔너리 생성
        if self.h_history != None: #히스토리가 있어야됨
            if self.pre_h != None: #프리H 가 있으면 삽입
                self.h_entry_history[f'div:{self.division}']['pre_h'] = {'price':self.pre_h['price'], 'qty':self.pre_h['qty']}
            for i in range(len(self.h_history)):
                self.h_entry_history[f'div:{self.division}'][i] = {'price':self.g_history[i]['price'],'qty':self.g_history[i]['qty']}
        

    #엔트리 진입평균가 계산 - 어 이거 왜 사용안하지
    def entry_avg_price(self):
        try:
            logging.info('now entry avg price (g/h)')
            if self.g_avg_price == None and self.h_avg_price == None:
                self.g_avg_price = 0
                self.g_total_qty = 0
                self.h_avg_price = 0
                self.h_total_qty = 0
            if self.division == 0:
                if self.g_order_price != [] and self.g_order_qty != []:
                    add = 0
                    for i in range(len(self.g_order_price)):
                        add += self.g_order_price[i]*self.g_order_qty[i]
                    self.g_avg_price = add / sum(self.g_order_qty)
            elif self.division > 0:
                if self.g_order_price != [] and self.g_order_qty != []:
                    g_add = 0
                    for i in range(len(self.g_order_price)):
                        g_add += self.g_order_price[i]*self.g_order_qty[i]
                    self.g_avg_price = g_add / sum(self.g_order_qty)
                if self.h_order_price != [] and self.h_order_qty != []:
                    h_add = 0
                    for i in range(len(self.h_order_price)):
                        h_add += self.h_order_price[i]*self.h_order_qty[i]
                    self.h_avg_price = h_add / sum(self.h_order_qty)

            logging.info(f'g_avg_price:{self.g_avg_price}')
            logging.info(f'h_avg_price:{self.h_avg_price}')
        except Exception as e:
            logging.error(traceback.format_exc())
    
    #Dv 모든 주문 체결시 포지션 업데이트
    def position_update(self):
        try:
            logging.info('now history avg price')
            if self.division == 0:
                self.g_position = {}
                self.h_position = {}
                self.g_position['AEP'] = float(format(self.g_history[0]['price'],'.{}f'.format(self.spread)))
                self.g_position['QTY'] = float(format(self.g_history[0]['qty'],'.{}f'.format(self.decimal)))
            else:
                g_avg = 0
                g_qty = 0
                h_avg = 0
                h_qty = 0
                for g in range(len(self.g_history)):
                    g_avg += self.g_history[g]['price']*self.g_history[g]['qty']
                    g_qty += self.g_history[g]['qty']
                for h in range(len(self.h_history)):
                    h_avg += self.h_history[h]['price']*self.h_history[h]['qty']
                    h_qty += self.h_history[h]['qty']
                gavg = g_avg/g_qty
                havg = h_avg/h_qty
                self.g_position['AEP'] = ((self.g_position['AEP'] if len(self.g_position) != 0 else 0) * self.g_position['QTY'] + gavg*g_qty) / (self.g_position['QTY'] + g_qty)
                self.g_position['QTY'] = (self.g_position['QTY'] if len(self.g_position) != 0 else 0) + g_qty
                self.h_position['AEP'] = ((self.h_position['AEP'] if len(self.h_position) != 0 else 0) * self.h_position['QTY'] + havg*h_qty) / (self.h_position['QTY'] + h_qty)
                self.h_position['QTY'] = (self.h_position['QTY'] if len(self.h_position) != 0 else 0) + h_qty #입력된게 있으면 그걸사용하지만 없으면 0을 입력해 hqty가 추가될 수 있게 해준다.

            logging.info(f'Dv:{self.division}, g_position:{self.g_position}')
            logging.info(f'Dv:{self.division}, h_position:{self.h_position}')
        except Exception as e:
            logging.error(traceback.format_exc())

    #엔트리 슬리피지 계산
    def entry_slippage(self):
        try:
            logging.info('slippage check')
            g_sli = self.g_slippage
            h_sli = self.h_slippage
            
            g_diff = float(format(self.g_history[self.stg]['price'] - self.general_price[self.stg],'.{}f'.format(self.spread)))
            self.g_history[self.stg]['slippage'] = g_diff
            if self.signal['Signal'] == LONG:
                if g_diff < 0:
                    self.g_slippage += g_diff
            elif self.signal['Signal'] == SHORT:
                if g_diff > 0:
                    self.g_slippage += g_diff
            
            h_diff = float(format(self.h_history[self.stg]['price'] - self.g_history[self.stg]['price'],'.{}f'.format(self.spread)))
            self.h_history[self.stg]['slippage'] = h_diff
            if self.signal['Signal'] == LONG:
                if h_diff > 0:
                    self.h_slippage += h_diff
            elif self.signal['Signal'] == SHORT:
                if h_diff < 0:
                    self.h_slippage += h_diff
            
            self.t_slippage = float(format(self.g_slippage + self.h_slippage,'.{}f'.format(self.spread)))
                    
            g_change = float(format(self.g_slippage - g_sli,'.{}f'.format(self.spread)))
            h_change = float(format(self.h_slippage - h_sli,'.{}f'.format(self.spread)))
            
            logging.info(f'slippage check 결과:{self.division}-{self.stg}/g_diff:{g_diff},g_sli변화량:{g_change}/h_diff:{h_diff},h_sli변화량:{h_change}/t_sli:{self.t_slippage}')
            logging.info(f'general_price:{self.general_price[self.stg]}')
            logging.info(f'g_history:{self.g_history[self.stg]}')
            logging.info(f'h_history:{self.h_history[self.stg]}')
        except Exception as e:
            logging.error(traceback.format_exc())
            
    def get_liquidation_percent(self):
        
        try:
            logging.info('get_liquidation_percent')
            exchange = ccxt.binance(config={
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
            })
            while True:
                positions = exchange.fetch_positions(symbols=[SYMBOL])

                if self.signal['Signal'] == LONG:
                    liquidation = float(positions[0]['info']['liquidationPrice'])
                elif self.signal['Signal'] == SHORT:
                    liquidation = float(positions[1]['info']['liquidationPrice'])

                self.liquidation_per = (liquidation - self.g_position['AEP']) / self.g_position['AEP']
                
                if self.liquidation_per != None:
                    break
                time.sleep(0.5)
                
            logging.info(self.liquidation_per)
        except Exception as e:
            logging.error(traceback.format_exc())
            
    def order_ratio_control(self):
        if self.g_detail_count == 0 and self.h_detail_count == 0:
            g = True
            h = True
            #한개만 0인 상황은 아마 안생길거임
        else:
            g = self.g_entry_order_count - self.g_detail_count
            h = self.h_entry_order_count - self.h_detail_count
            
            g = True if g != 0 else False
            h = True if h != 0 else False
        
        return [g, h]

    #진입 매니저
    async def entry_manager(self):
        """
        """
        try: 
            while True:
                await asyncio.sleep(0.05)
                if self.check_time != None:
                    if str(self.check_time[-5:-3]) == '00' or str(self.check_time[-5:-3]) == '30':
                        print(self.now,'진입 매니저 작동중')
                        await asyncio.sleep(0.5)
                #safe2가 발동되었는지 확인후 주문하는 것.
                price = self.price #현재 가격을 확인하고
                safe2 = self.safe_manager(price=price,safe2=SAFE2_PER)
                if safe2 == True:
                    print('safe2 발동')
                    pass
                    """전부다사"""
                else:
                    if self.pre_h == None: #시그널이 없을때도 진입해야되기 때문에 여기에.
                        if self.division != None:
                            if self.division > 0:
                                if self.general_qty == None:
                                    self.general_qty = self.general_qty_creator(signal=self.status, qty=self.entry_list[self.division])
                                    self.hedge_qty = self.hedge_qty_creator(g_qty=self.general_qty)
                                await self.pre_h_order(signal=self.status, qty=self.hedge_qty[0], price=price)
                    if self.signal != None: #시그널이 생성되어있다면
                        if self.signal_time == None:
                            cur_time = datetime.now()
                            self.signal_time = cur_time + timedelta(minutes=int(TIME_FRAME[:-1])*5)
                        if self.division == None:
                            self.division = 0
                            self.entry_list = self.create_entry_list()
                            if self.stg == None: #stg를 확인해서 None인걸 확인한다면
                                self.stg = 0 #최초인 0을 입력해주고
                                self.general_price = self.general_price_creator(signal=self.signal)#진입가격표를 만든다.
                                self.general_qty = self.general_qty_creator(signal=self.signal, qty=self.entry_list[self.division])
                                self.hedge_qty = self.hedge_qty_creator(g_qty=self.general_qty)
                                print(self.now,'진입준비완료0')
                        else:
                            if self.division == 0:
                                if self.stg == None: #stg를 확인해서 None인걸 확인한다면
                                    self.stg = 0 #최초인 0을 입력해주고
                                    self.general_price = self.general_price_creator(signal=self.signal)#진입가격표를 만든다.
                                    self.general_qty = self.general_qty_creator(signal=self.signal, qty=self.entry_list[self.division])
                                    self.hedge_qty = self.hedge_qty_creator(g_qty=self.general_qty)
                                    print(self.now,'진입준비완료2')
                                if self.stg == 0: #None이 아닐경우 0인지 확인해서
                                    if len(self.g_history) == self.stg : #g주문이 없는지확인하고 없다면
                                        if self.g_prep == []: #나눠서 주문함
                                            self.g_prep = self.g_entry_preparation(qty=self.general_qty[self.stg])
                                            self.g_detail_count = 0
                                        if self.g_detail_count < self.g_entry_order_count:
                                            await self.g_entry_order(signal=self.signal['Signal'], g_qty=self.g_prep[self.g_detail_count])#G1주문하는 함수
                                            if self.g_entry_order_check == True:
                                                self.g_detail_count += 1
                                                self.g_entry_order_check = False
                                        elif self.g_detail_count == self.g_entry_order_count: #5번째 주문까지 됐는지 확인 후 stg 올리는것으로 변경, 첫번째는 g밖에 없음
                                            self.lastest_g_order = self.g_order_price[-1]
                                            self.history_creator()
                                            self.entry_history_creator()
                                            self.position_update()
                                            self.get_liquidation_percent() #최초에 1회만
                                            self.status = self.signal['Signal']
                                            self.division += 1
                                            self.entry_reset()
                                            # G1 이 전부 체결 됐으면 liquidation price 확인해서 self.safe_per 입력해줘야함
                                            logging.info('-----첫 gh 진입완료 dv1 추가-----')
                                            print(self.now,'첫 gh 진입 완료 dv1 추가')

                            elif self.division > 0:
                                if self.stg == None: #stg를 확인해서 None인걸 확인한다면
                                    self.stg = 0 #최초인 0을 입력해주고
                                    self.general_price = self.general_price_creator(signal=self.signal)#진입가격표를 만든다.
                                    self.next_price = self.general_price[0]
                                    print(self.now,'next_price 설정:', self.general_price[0])
                                    if self.general_qty == None:
                                        self.general_qty = self.general_qty_creator(signal=self.signal, qty=self.entry_list[self.division])
                                        self.hedge_qty = self.hedge_qty_creator(g_qty=self.general_qty)
                                    print(self.now,'진입준비완료3-첫g진입대기중')
                                if self.stg == 0: #None이 아닐경우 0인지 확인해서
                                    if self.pre_h == None: # stg가 0이라면 pre_h 주문이 있는지 확인하고 없다면 주문해줌.
                                        await self.pre_h_order(signal=self.signal['Signal'],price=price,qty=self.hedge_qty[0])
                                        print(self.now,"pre_h 완료")
                                    else: #pre h가 있다면
                                        if len(self.g_history) == self.stg : # pre_h 주문이 있다면 완료된 g주문이 없는지확인하고 없다면
                                            if self.check_signal(price=price): #딕셔너리기 때문에 값그대로 넣어야 0이 선택됨
                                                if self.g_prep == []: #최초 인경우 gprep 만들어주고 카운트 0 넣어줌
                                                    self.g_detail_count = 0
                                                    self.h_detail_count = 0
                                                    self.g_prep = self.g_entry_preparation(qty=self.general_qty[self.stg])
                                                    self.h_prep = self.h_entry_preparation(qty=self.hedge_qty[self.stg])
                                                if self.g_detail_count < self.g_entry_order_count or self.h_detail_count < self.h_entry_order_count:
                                                    orc = self.order_ratio_control()
                                                    logging.info(f'orc:{orc},price:{self.price}')
                                                    if len(self.g_prep) > self.g_detail_count:
                                                        if orc[0]:
                                                            await self.g_entry_order(signal=self.signal['Signal'], g_qty=self.g_prep[self.g_detail_count])#G1
                                                            if self.g_entry_order_check == True:
                                                                self.g_detail_count += 1
                                                                self.g_entry_order_check = False
                                                    if len(self.h_prep) > self.h_detail_count:
                                                        if orc[1]:
                                                            await self.h_entry_order(signal=self.signal['Signal'], h_qty=self.h_prep[self.h_detail_count])#H1 주문하는 함수
                                                            if self.h_entry_order_check == True:
                                                                self.h_detail_count += 1
                                                                self.h_entry_order_check = False
                                                    print(self.now,'체크포인트1:','g:',self.g_detail_count,'/',self.g_entry_order_count,'h:', self.h_detail_count,'/',self.h_entry_order_count)
                                                elif self.g_detail_count == self.g_entry_order_count and self.h_detail_count == self.h_entry_order_count: #g와 h 모두 주문완료 됐는지 확인 후 stg 올리는것으로 변경
                                                    self.history_creator()
                                                    self.entry_slippage()
                                                    self.g_detail_count = None
                                                    self.h_detail_count = None
                                                    self.g_prep = []
                                                    self.h_prep = []
                                                    print(self.now,'Dv:',self.division,'-',self.stg,'gh 진입 완료') 
                                                    self.next_price = float(format((self.general_price[self.stg] - self.t_slippage) if self.signal['Signal'] == LONG else (self.general_price[self.stg] + self.t_slippage),'.{}f'.format(self.spread)))
                                                    self.stg += 1
                                                    logging.info(f'next price:{self.next_price}')
                                            else:
                                                if self.g_history == {}:
                                                    if (self.g_detail_count == None and self.h_detail_count == None) or (self.g_detail_count == 0 and self.h_detail_count == 0):
                                                        cur_time = datetime.now()
                                                        if cur_time > self.signal_time:
                                                            self.entry_reset()
                                                            if self.division == 0: #디비전 되돌리기
                                                                self.division = None
                                                            else:
                                                                del self.signal_history[f'{self.division}']
                                                            print(self.now,'25분체결안됨 취소')
                                                        #초기화 함수 시그널 취소
                                                #5개봉동안 g1함수가 발동되지 않는다면 pre_h가 수익중이면 없애면서 종료 손실중이면 리미트주문넣고종료
                                                
                                elif 0 < self.stg < GENERAL_STG: #stg 가 0 보다 클경우
                                    if len(self.g_history) == self.stg : # 완료된 g주문이 현재 단계와 같으면 
                                        if self.check_signal(price=price): #딕셔너리기 때문에 값그대로 넣어야 0이 선택됨
                                            if self.g_prep == []: #최초 인경우 gprep 만들어주고 카운트 0 넣어줌
                                                self.g_detail_count = 0
                                                self.h_detail_count = 0
                                                self.g_prep = self.g_entry_preparation(qty=self.general_qty[self.stg])
                                                self.h_prep = self.h_entry_preparation(qty=self.hedge_qty[self.stg])
                                            if self.g_detail_count < self.g_entry_order_count or self.h_detail_count < self.h_entry_order_count:
                                                orc = self.order_ratio_control()
                                                if len(self.g_prep) > self.g_detail_count:
                                                    if orc[0]:
                                                        await self.g_entry_order(signal=self.signal['Signal'], g_qty=self.g_prep[self.g_detail_count])#G 주문하는 함수
                                                        if self.g_entry_order_check == True:
                                                            self.g_detail_count += 1
                                                            self.g_entry_order_check = False
                                                if len(self.h_prep) > self.h_detail_count:
                                                    if orc[1]:
                                                        await self.h_entry_order(signal=self.signal['Signal'], h_qty=self.h_prep[self.h_detail_count])#G 주문하는 함수
                                                        if self.h_entry_order_check == True:
                                                            self.h_detail_count += 1
                                                            self.h_entry_order_check = False
                                            elif self.g_detail_count == self.g_entry_order_count and self.h_detail_count == self.h_entry_order_count: #5번째 주문까지 됐는지 확인 후 stg 올리는것으로 변경
                                                self.history_creator()
                                                self.entry_slippage()
                                                self.g_detail_count = None
                                                self.h_detail_count = None
                                                self.g_prep = []
                                                self.h_prep = []
                                                print(self.now, 'Dv:',self.division,'-',self.stg,'gh 진입 완료') #마지막엔 stg1 추가 안함 0 1 2 3 - 4가되면 키값 넘어감
                                                self.next_price = float(format((self.general_price[self.stg] - self.t_slippage) if self.signal['Signal'] == LONG else (self.general_price[self.stg] + self.t_slippage),'.{}f'.format(self.spread)))
                                                self.stg += 1
                                                logging.info(f'next price:{self.next_price}')
                                                # G1 이 전부 체결 됐으면 liquidation price 확인해서 self.safe_per 입력해줘야함
                                
                                elif self.stg == GENERAL_STG: # 마지막 주문까지 모두 완료된경우
                                    self.position_update()
                                    self.pre_h = None # 정상적으로 dv에 편입된경우임
                                    self.division += 1
                                    self.entry_reset()
                                    #g 모든주문의 평균진입가가 필요
                                    print(self.now,'마지막gh진입완료 시그널종료')
                                    logging.info(f'Dv:{self.division}')

                            elif self.division == DIVISION:
                                pass #나중에 마지노선 터지는거 넣어야됨
                    else:
                        pass #시그널이 없을때 그냥 패스하는중
                
                if self.division != None:
                    if self.division >= 3:
                        print(self.now,'테스트 한계 Dv 도달 - 종료(',self.now,')')
                        continue

        except Exception as e:
            logging.error(traceback.format_exc())


    async def exit_manager(self):
        """
        """

    #세이프 감지 함수
    def safe_manager(self,price,safe1=None,safe2=None):
        """
        """
        try:
            if self.g_position == None:
                result = False
            else:
                if safe1 != None and self.division != 0:
                    safe1_per = 1 + self.liquidation_per*SAFE1_PER
                    price = price
                    if self.status == LONG:
                        if price <= self.g_position['AEP'] * safe1_per:
                            logging.info('----safe 1 감지----')
                            result = True
                    elif self.status == SHORT:
                        if price >= self.g_position['AEP'] * safe1_per:
                            logging.info('----safe 1 감지----')
                            result = True
                    else:
                        result = False
                else:
                    result = False

                if safe2 != None and self.division != 0:
                    safe2_per = 1 + self.liquidation_per*SAFE2_PER
                    price = price
                    if self.status == LONG:
                        if price <= self.g_position['AEP'] * safe2_per:
                            logging.info('----safe 2 감지----')
                            result = True
                    elif self.status == SHORT:
                        if price >= self.g_position['AEP'] * safe2_per:
                            logging.info('----safe 2 감지----')
                            result = True
                    else:
                        result = False
                else:
                    result = False
            
            return result
        except Exception as e:
            logging.error(traceback.format_exc())


    # async def main(self):
    #     tasks = [trader.administrator(),trader.order_handler(),trader.entry_manager()]
    #     result = await asyncio.gather(*tasks)
    #     print(result)
        
    def run(self):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(
            asyncio.gather(
                self.administrator(),
                self.order_handler(),
                self.entry_manager()
            )
        )
        self.loop.close()
        
if __name__ == '__main__':
    trade = Trader()
    trade.run()


# try:
#     if not API_KEY or not API_SECRET:
#         logging.error('Set API_KEY and API_SECRET')
#     else:
#         trader = Trader()
#         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#         asyncio.run(trader.main())
# except Exception as e:
#     logging.error(traceback.format_exc())