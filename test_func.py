import logging
import traceback
import time
import ccxt
from consts import *
from datetime import datetime
from datetime import timedelta

class test():
    def __init__(self):
         self.price = 24000
         self.balance = 0.0833
         self.min_qty = 0.001
         self.decimal = 3
         self.signal = {'Signal':LONG}

    def create_entry_list(self):
            
            try:
                logging.info('create_entry_list')
                entry_list = []
                able_balance = float(self.balance)*0.95
                price = self.price
                able_coin = able_balance / float(price) * LEVERAGE
                decimal = len(str(self.min_qty%1))-2

                for div in range(DIVISION):
                    if div == 0:
                        add = float(format(LEVERAGE*self.balance/CONST,'.{}f'.format(decimal)))
                        entry_list.append(add)
                    else:
                        add = float(format(sum(entry_list)*RATE_LIST[div],'.{}f'.format(decimal)))
                        entry_list.append(add)
                
                logging.info(entry_list)
                return entry_list
            
            except Exception as e:
                logging.error(traceback.format_exc())

    def history_creator(self):
        history = {}
        for i in range(len(G_RATE_LIST)):
            history['{}'.format(i)] = {}
        return history
        
    
    def tttt(self):
        cur_time = datetime.now()
        end_time = cur_time + timedelta(minutes=int(TIME_FRAME[:-1]))
        while True:
            cur_time = datetime.now()
            print (cur_time, end_time)
            if cur_time > end_time:
                print('done')
                break
            else:
                time.sleep(1)
    def tsts(self):
        if self.check_signal(price=self.price,fomula=(4-2)*3):
            print('true')
        else:
            print('false')

    def check_signal(self,price,fomula):
        s_price = price
        s_fomula= fomula

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

        return result
    
    def check_liq(self):
        exchange = ccxt.binance(config={
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future'
        }
        })
        positions = exchange.fetch_positions(symbols=[SYMBOL])
        print(positions)
    
tes = test()
s= tes.check_liq()