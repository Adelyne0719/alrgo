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
from consts import *
import decorator

config_logging(logging, logging.INFO)

class Trader():
    def __init__(self):
        #전역변수
        self.binance = UMFutures(key=API_KEY, secret=API_SECRET)
        self.status = NEUTRAL
        self.division = None
        self.position = None
        self.entry_list = None
        self.g_position = None
        self.h_position = None
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
        self.pre_h = None
        self.pre_h_exit = None
        self.unit = None
        self.signal_time = None
        self.g_order_price = []
        self.g_order_qty = []
        self.h_order_price = []
        self.h_order_qty = []
        self.g_history = {}
        self.h_history = {}
        self.general_price = []
        self.hedge_list = []
        self.h_slippage = 0



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
            self.is_init_success = True  # 초기화함수 완료
        except Exception as e:
            logging.error(traceback.format_exc())

    #엔트리 리셋(지금상태는0단계일때만)
    def entry_reset(self):
        self.signal = None
        self.stg = None
        self.unit = None
        self.signal_time = None
        self.g_order_price = []
        self.g_order_qty = []
        self.h_order_price = []
        self.h_order_qty = []
        self.g_history = {}
        self.h_history = {}
        self.general_price = []
        self.hedge_list = []
        self.h_slippage = 0
        if self.status == LONG:
            if self.pre_h['Price'] < self.price:
                self.pre_h_exit_order(self,side=self.status,qty=self.pre_h['Qty'])
                self.pre_h = None
                self.pre_h_exit = None
        elif self.status == SHORT:
            if self.pre_h['Price'] > self.price:
                self.pre_h_exit_order(self,side=self.status,qty=self.pre_h['Qty'])
                self.pre_h = None
                self.pre_h_exit = None

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
                logging.info('Need to close position')
        
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
            self.balance = 11000 #테스트용 지워야함
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
                    result = {}
                    result['Signal']
                    result['Close'] = self.price
                    result['Atr'] = result['Close']*GAP_PERCENT
                    result['Mingap'] = (result['Close']*GAP_PERCENT if result['Close'] >= result['Atr'] else result['Atr'])/GENERAL_DIV
                else:
                    if str(self.now)[-5:-3] != self.check_time and self.check_time != None:
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
                                    self.df = self.candle_data(TIME_FRAME, REQ_LIMIT)
                                    result = {}
                                    result['Close'] = self.df['Close'].iloc[-1]
                                    result['Atr'] = self.df['Atr'].iloc[-1]
                                    result['Mingap'] = (result['Close']*GAP_PERCENT if result['Close'] >= result['Atr'] else result['Atr'])/GENERAL_DIV
                                    candle_condition = self.df['Close'].iloc[-2] - self.df['Open'].iloc[-2]
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
                                    elif self.status == LONG: # 진입가 1% ATR 추가해야됨(완료)
                                        if candle_condition < 0:
                                            if self.g_position['AEP'] - result['Mingap']*GENERAL_DIV <= result['Close']:
                                                if self.df['Close'].iloc[-2] + (abs(candle_condition) * CONDITION_RATE) <= self.df['Close'].iloc[-1] <= self.df['Open'].iloc[-2]:
                                                    result['Signal'] = LONG
                                                else:
                                                    result = None
                                    elif self.status == SHORT:
                                        if candle_condition > 0:
                                            if self.g_position['AEP'] + result['Mingap']*GENERAL_DIV >= result['Close']:
                                                if self.df['Close'].iloc[-2] - (abs(candle_condition) * CONDITION_RATE) >= self.df['Close'].iloc[-1] >= self.df['Open'].iloc[-2]:
                                                    result['Signal'] = SHORT
                                                else:
                                                    result = None
                            self.redundancy = str(self.now)[:-2]
                        else:
                            if self.redundancy != str(self.now)[:-2]:
                                self.redundancy = None
            else:
                result = self.signal
                
            return result
            
        except Exception as e:
            logging.error(traceback.format_exc())

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
                entry_list = {}
                able_balance = float(self.balance)*0.95
                price = self.signal['Close']
                able_coin = able_balance / float(price) * LEVERAGE

                for div in range(DIVISION):
                    if div == 0:
                        entry_list[div] = float(format(LEVERAGE*float(self.balance)/(price*CONST),'{}f'.format(self.decimal)))
                    else:
                        entry_list[div] = float(format(sum(entry_list)*RATE_LIST[div],'{}f'.format(self.decimal)))
                
                if entry_list[1] < sum(G_RATE_LIST)*self.min_qty:
                    raise ValueError
                
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

    #비연동 매니저
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
            

            print(time_stamp, 'price:',self.price,'signal:', self.signal)
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
                    if event['e'] == 'ORDER_TRADE_UPDATE' and event['o']['X'] == 'FILLED':
                        if event['o']['o'] == MARKET and event['o']['c'] == 'pre_h':
                            self.pre_h['Price'] = float(event['o']['ap'])
                            self.pre_h['Qty'] = float(event['o']['q'])
                        elif event['o']['o'] == MARKET and event['o']['c'] == 'pre_h_exit':
                            self.pre_h['Exit_price'] = float(event['o']['ap'])
                        elif event['o']['o'] == MARKET and event['o']['c'] == 'entry_g':
                            self.g_order_price.append(float(event['o']['ap']))
                            self.g_order_qty.append(float(event['o']['q']))
                        elif event['o']['o'] == MARKET and event['o']['c'] == 'entry_h':
                            self.h_order_price.append(float(event['o']['ap']))
                            self.h_order_qty.append(float(event['o']['q']))
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
                    print(event)

                except Exception as e:
                    logging.error(traceback.format_exc())

    #제너럴 내부가격 생성함수
    def general_price_creator(self,signal):
        try:
            logging.info('create general price')
            gpc_signal = signal
            result = {}
            if signal['Signal'] == LONG:
                for i in range(GENERAL_DIV+1):
                    if i == 0:
                        result['Signal'] = gpc_signal['Close']
                    else:
                        p = gpc_signal['Close'] - gpc_signal['Mingap'] * (i+1)
                        result[i-1] = float(format(p,'{}f'.format(self.spread)))

            elif signal['Signal'] == SHORT:
                for i in range(GENERAL_DIV+1):
                    if i == 0:
                        result['Signal'] = gpc_signal['Close']
                    else:
                        p = gpc_signal['Close'] + gpc_signal['Mingap'] * (i+1)
                        result[i-1] = float(format(p,'{}f'.format(self.spread)))
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
            self.unit = float(gqc_qty/sum(G_RATE_LIST),'{}f'.format(self.decimal))
            result = {}
            for i in range(G_RATE_LIST):
                result[i] = self.unit*G_RATE_LIST[i]
            rest = gqc_qty - sum(result)
            if rest != 0:
                result[i] += rest
            logging.info(result)
            return result
        except Exception as e:
            logging.error(traceback.format_exc())

    #헷지 내부수량 생성함수
    def hedge_qty_creator(self):
        try:
            logging.info('create hedge qty')
            result = {}
            for i in range(H_RATE_LISE):
                result[i] = H_RATE_LISE[i]*self.unit
            logging.info(result)
            return result
        except Exception as e:
            logging.error(traceback.format_exc())

    #단계별 오더 저장하는 것 틀 생성
    def history_creator(self):
        history = {}
        for i in range(len(G_RATE_LIST)):
            history['{}'.format(i)] = {}
    
    #프리H 주문 넣는 함수
    @decorator.call_binance_api
    async def pre_h_order(self, signal, price, qty):
        
        try:
            if self.pre_h != None:
                qty = float(format(qty/2,'{}f'.format(self.decimal)))
            logging.info('pre_h_order')
            order = self.binance.new_order(
                symbol=SYMBOL,
                type=MARKET,
                side=HEDGE_TO_OPEN_SIDE[signal],
                PositionSide=HEDGE_TO_POSITION_SIDE[signal],
                quantity=qty,
                newClientOrderId='pre_h'
            )
            while True:
                await asyncio.sleep(0.01)
                if self.pre_h != None:
                    break
            slical = self.pre_h['Price'] - self.signal['Close']
            self.h_slippage += slical
            self.hedge_qty[0] = qty
            print(signal,'order_price:',price,'avg_price:',self.pre_h['Price'],'slippage:',slical,'qty:',qty)
        except Exception as e:
            logging.error(traceback.format_exc())

    #프리H 주문 종료하는 함수
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
                    pnl= self.pre_h['Price'] - self.pre_h_exit['Exit_price']
                    self.spare_pnl += pnl
                print('order_price:',self.price,'avg_price:',self.pre_h_exit['Exit_price'],'qty:',qty)
        except Exception as e:
            logging.error(traceback.format_exc())

    #엔트리 주문 넣는 함수
    @decorator.call_binance_api
    async def entry_order(self, signal, g_qty, h_qty):
        
        try:
            logging.info('entry')
            g_ent_qty = g_qty//(ENTRY_ORDER_COUNT*self.min_qty)
            g_rest = f'{g_qty%(ENTRY_ORDER_COUNT*self.min_qty):.{self.decimal}f}'
            h_ent_qty = h_qty//(ENTRY_ORDER_COUNT*self.min_qty)
            h_rest = f'{h_qty%(ENTRY_ORDER_COUNT*self.min_qty):.{self.decimal}f}'
            for i in range(ENTRY_ORDER_COUNT):
                if g_rest != 0:
                    if i == ENTRY_ORDER_COUNT - g_rest*10^self.decimal:
                        g_ent_qty += self.min_qty
                if h_rest != 0:
                    if i == ENTRY_ORDER_COUNT - h_rest*10^self.decimal:
                        h_ent_qty += self.min_qty
                g_order = self.binance.new_order(
                    symbol=SYMBOL,
                    type=MARKET,
                    side=SIGNAL_TO_OPEN_SIDE[signal],
                    PositionSide=[signal],
                    quantity=g_ent_qty,
                    newClientOrderId='entry_g'
                )
                h_order = self.binance.new_order(
                    symbol=SYMBOL,
                    type=MARKET,
                    side=HEDGE_TO_OPEN_SIDE[signal],
                    PositionSide=HEDGE_TO_POSITION_SIDE[signal],
                    quantity=h_ent_qty,
                    newClientOrderId='entry_h'
                )
                while True:
                    await asyncio.sleep(0.01)
                    if len(self.g_order) > i and len(self.h_order) > i:
                        break
            g_cal = 0
            h_cal = 0
            for l in range(len(self.g_order_price)):
                a = self.g_order_price[l] * self.g_order_qty[l]
                g_cal += a
            for l in range(len(self.h_order_price)):
                a = self.g_order_price[l] * self.g_order_qty[l]
                h_cal += a
            g_ap = g_cal / sum(self.g_order_qty)
            h_ap = h_cal / sum(self.h_order_qty)
            slical = h_ap - g_ap
            self.h_slippage += slical
            self.g_history['{}'.format(i)] = {'price':g_ap,'qty':g_qty}
            self.h_history['{}'.format(i)] = {'price':h_ap,'qty':h_qty}
            print(signal,'g_price:',g_ap,'g_qty:',g_qty,'h_price:',h_ap,'h_qty:',h_qty,'slippage:',slical)
        except Exception as e:
            logging.error(traceback.format_exc())

    #진입 매니저
    async def entry_manager(self):
        """
        """
        try: 
            while True:
                await asyncio.sleep(0.05)
                if self.check_time != None:
                    if self.check_time != self.now[-5:-3]:
                        print('진입 매니저 작동중')
                        await asyncio.sleep(0.5)
                #safe2가 발동되었는지 확인후 주문하는 것.
                price = self.price #현재 가격을 확인하고
                safe2 = self.safe_manager(price=price,safe2=SAFE2_PER)
                if safe2 == True:
                    print('safe2 발동')
                    pass
                    """전부다사"""
                else:
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
                                self.hedge_qty = self.hedge_qty_creator()
                                self.g_history = self.history_creator()
                                self.h_history = self.history_creator()
                                print('진입준비완료')
                            else:
                                if self.stg == 0: #None이 아닐경우 0인지 확인해서
                                    if self.pre_h == None: # 0이라면 pre_h 주문이 있는지 확인하고 없다면 주문해줌.
                                        await self.pre_h_order(signal=self.signal['Signal'],price=price,qty=self.hedge_qty[0])
                                        print("pre_h 완료")
                                    else: #pre h가 있다면
                                        if self.g_history[self.stg] == {}: # pre_h 주문이 있다면 g주문이 없는지확인하고 없다면
                                            if price <= ((self.general_price[self.stg+1] - self.h_slippage) if self.signal('Signal') == LONG else (self.general_price[self.stg+1] + self.h_slippage)): #0은 시그널 발생가격이기때문에 +1
                                                await self.entry_order(self, signal=self.signal['Signal'], g_qty=self.general_qty[self.stg], h_qty=self.hedge_qty[self.stg])#G1 H1 주문하는 함수
                                                # G1 이 전부 체결 됐으면 liquidation price 확인해서 self.safe_per 입력해줘야함
                                                self.stg += 1
                                                print('첫 gh 진입 완료 stg1 추가')
                                            else:
                                                if self.g_history[self.stg] == {}:
                                                    cur_time = datetime.now()
                                                    if cur_time > self.signal_time:
                                                        self.entry_reset()
                                                        print('25분체결안됨 취소')
                                                        #초기화 함수 시그널 취소
                                                #5개봉동안 g1함수가 발동되지 않는다면 pre_h가 수익중이면 없애면서 종료 손실중이면 리미트주문넣고종료

                                elif 0 < self.stg < GENERAL_DIV: #stg 가 0 보다 클경우
                                    if price <= ((self.general_price[self.stg+1] - self.h_slippage) if self.signal('Signal') == LONG else (self.general_price[self.stg+1] + self.h_slippage)):
                                        await self.entry_order(self, signal=self.signal['Signal'], g_qty=self.general_qty[self.stg], h_qty=self.hedge_qty[self.stg])
                                        self.stg += 1
                                        print('gh 진입 완료 stg1 추가')
                                
                                elif self.stg == GENERAL_DIV:
                                    if price <= ((self.general_price[self.stg+1] - self.h_slippage) if self.signal('Signal') == LONG else (self.general_price[self.stg+1] + self.h_slippage)):
                                        await self.entry_order(self, signal=self.signal['Signal'], g_qty=self.general_qty[self.stg], h_qty=self.hedge_qty[self.stg])
                                        if self.status == NEUTRAL:
                                            self.status = self.signal['Signal']
                                            self.division += 1
                                            self.entry_reset()
                                            print('마지막gh진입완료 시그널종료')
                    else:
                        pass


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
                    safe1_per = self.liquidation_per*SAFE1_PER
                    price = price
                    if self.status == LONG:
                        if price <= self.g_position['AEP'] * safe1_per:
                            result = True
                    elif self.status == SHORT:
                        if price >= self.g_position['AEP'] * safe2_per:
                            result = True
                    else:
                        result = False
                else:
                    result = False

                if safe2 != None and self.division != 0:
                    safe2_per = self.liquidation_per*SAFE2_PER
                    price = price
                    if self.status == LONG:
                        if price <= self.g_position['AEP'] * safe2_per:
                            result = True
                    elif self.status == SHORT:
                        if price >= self.g_position['AEP'] * safe2_per:
                            result = True
                    else:
                        result = False
                else:
                    result = False
            
            return result
        except Exception as e:
            logging.error(traceback.format_exc())


    async def main(self):
        tasks = [trader.administrator(),trader.order_handler(),trader.entry_manager()]
        result = await asyncio.gather(*tasks)
        print(result)

if __name__ == "__main__":
    try:
        if not API_KEY or not API_SECRET:
            logging.error('Set API_KEY and API_SECRET')
        else:
            trader = Trader()
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.run(trader.main())
    except Exception as e:
        logging.error(traceback.format_exc())