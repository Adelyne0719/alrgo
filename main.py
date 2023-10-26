import sys
import asyncio
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGroupBox
from PyQt5.QtCore import QTimer, QThread, pyqtSignal
from trade import Trader

class UpdateThread(QThread):
    data_updated = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.trader = Trader()
        self.trader.start()

    def update_data(self):
        trader_keys = [
            'binance', 'status', 'division', 'position', 'entry_list', 'g_position', 'h_position', 'g_entry_history', 'h_entry_history',
            'liquidation_per', 'lastest_g_order', 'signal', 'signal_history', 'price', 'top_ask', 'top_bid', 'cycle', 'now', 'check_time',
            'redundancy', 'min_qty', 'decimal', 'spread', 'spare_pnl', 'is_init_success',
            
            'stg', 'pre_h', 'pre_h_exit', 'unit', 'g_detail_count', 'h_detail_count', 'signal_time', 'g_avg_price',
            'h_avg_price', 'g_total_qty', 'h_total_qty', 'general_price', 'general_qty', 'hedge_price',
            'hedge_qty', 'g_entry_order_count', 'h_entry_order_count', 'g_prep', 'h_prep', 'g_order_price', 'g_order_qty',
            'h_order_price', 'h_order_qty', 'g_history', 'h_history', 'hedge_list', 'g_slippage', 'h_slippage', 't_slippage',
            'g_entry_order_check', 'h_entry_order_check', 'next_price'
        ]

        data = {}
        for key in trader_keys:
            value = getattr(self.trader, key, None)
            if value is not None:
                data[key] = value

        if data:
            self.data_updated.emit(data)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('시간 및 가격 업데이트')
        self.setGeometry(300, 300, 600, 400)

        layout = QVBoxLayout()

        global_label_keys = [
            'binance', 'check_time', 'now', 'price', 'top_ask', 'top_bid', 'status', 'division', 'position', 
            'g_entry_history', 'h_entry_history','entry_list', 'g_position', 'h_position', 'liquidation_per', 
            'lastest_g_order', 'signal', 'signal_history',  'cycle', 'redundancy', 'min_qty', 'decimal', 'spread', 
            'spare_pnl', 'is_init_success'
        ]

        entry_label_keys = [
            'stg', 'pre_h', 'pre_h_exit', 'unit', 'next_price', 'signal_time', 'g_avg_price',
            'h_avg_price', 'g_total_qty', 'h_total_qty', 'general_price', 'general_qty', 'hedge_price',
            'hedge_qty','g_detail_count', 'h_detail_count', 'g_entry_order_count', 'h_entry_order_count', 
            'g_prep', 'h_prep', 'g_order_price', 'g_order_qty', 'h_order_price', 'h_order_qty', 'g_history', 'h_history',
            'hedge_list', 'g_slippage', 'h_slippage', 't_slippage', 'g_entry_order_check', 'h_entry_order_check'
        ]

        self.labels = {}

        global_group = QGroupBox('Global')
        global_layout = QVBoxLayout()

        for key in global_label_keys:
            label = QLabel(key + ': ')
            global_layout.addWidget(label)
            self.labels[key] = label

        global_group.setLayout(global_layout)

        entry_group = QGroupBox('Entry')
        entry_layout = QVBoxLayout()

        for key in entry_label_keys:
            label = QLabel(key + ': ')
            entry_layout.addWidget(label)
            self.labels[key] = label

        entry_group.setLayout(entry_layout)

        horizontal_layout = QHBoxLayout()
        horizontal_layout.addWidget(global_group)
        horizontal_layout.addWidget(entry_group)

        layout.addLayout(horizontal_layout)

        self.setLayout(layout)

        self.update_thread = UpdateThread()
        self.update_thread.data_updated.connect(self.update_data)
        self.update_thread.start()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_thread.update_data)
        self.timer.start(100)

    def update_data(self, data):
        for key, label in self.labels.items():
            value = data.get(key)
            if value is None:
                value = "None"
            label.setText(f'{key}: {value}')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())
