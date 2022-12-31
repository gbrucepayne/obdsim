import asyncio
import logging
import os
import sys
import time

sys.path.append(f'{os.getcwd()}')

from obdsim.bluetooth.ble import BleUartBridge, scan_ble
from obdsim.bluetooth.btc import BtcUartBridge, scan_btc, pair_with_pin
from obdsim.scanners import ElmScanner
from obdsim.simulator import ObdSimulator

format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
              '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter(format_csv)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def main():
    btc_names = ['Vlink', 'OBDII']
    simulate_vehicle = False
    ble_parameters = asyncio.run(scan_ble(btc_names))
    ble_parameters = {}
    if ble_parameters:
        bt_uart = BleUartBridge(**ble_parameters)
    else:
        btc_parameters = scan_btc(btc_names)
        if not btc_parameters:
            raise OSError(f'No Bluetooth device {btc_names} found')
        paired = pair_with_pin(btc_parameters['device_addr'], 1234)
        if not paired:
            raise ConnectionAbortedError
        bt_uart = BtcUartBridge(**btc_parameters)
    logger.info(f'Found OBD BT Device:({bt_uart.name})')
    bt_uart.start()
    while not bt_uart.initialized:
        logger.info('Initializing UART...')
        time.sleep(1)
    if simulate_vehicle:
        vehicle = ObdSimulator()
        vehicle.connect('vcan0')
        vehicle.start()
    app = ElmScanner()
    if not os.path.exists(bt_uart.port):
        raise ConnectionAbortedError
    app.connect(port=bt_uart.port)
    app.start()


if __name__ == '__main__':
    main()
