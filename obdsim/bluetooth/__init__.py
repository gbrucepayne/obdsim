import os
from .uart_pty import UartPty
from .uart_ble import UartBle
from .uart_btc import UartBtc

ADAPTER_NAME = os.getenv('ADAPTER_NAME', 'Vlink')
