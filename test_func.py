import logging
import traceback
import time
from consts import *
from datetime import datetime
from datetime import timedelta

class test():
    def __init__(self):
         self.price = 24000
         self.balance = 0.0833
         self.min_qty = 0.001

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
        tt = 3
        if 1<tt<5:
            print('ok')
tes = test()
s= tes.tsts()