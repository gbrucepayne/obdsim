import asyncio
import logging
import os
import sys
import json

sys.path.append(f'{os.getcwd()}')

from obdsim.bluetooth.ble import BleUartBridge, scan_ble
from obdsim.bluetooth.btc import scan_btc, pair_with_pin
from obdsim.scanners import ElmScanner
from obdsim.simulator import ObdSimulator
from obdsim.elm import ElmProtocol

DEVICE_UNDER_TEST = os.getenv('DEVICE_UNDER_TEST')
VEHICLE_BUS = os.getenv('VEHICLE_BUS')

format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
              '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter(format_csv)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def main():
    ble_parameters = {}
    btc_parameters = {}
    scanner_parameters = {}
    device_names = ['Vlink', 'OBDII']
    if DEVICE_UNDER_TEST:
        config = json.loads(DEVICE_UNDER_TEST)
        if 'ble' in config:
            ble_parameters = config['ble']
        elif 'btc' in config:
            ble_parameters = None
            btc_parameters = config['btc']
    if VEHICLE_BUS:
        vehicle = ObdSimulator(VEHICLE_BUS)
        vehicle.connect()
        vehicle.start()
        scanner_parameters['protocol'] = ElmProtocol.ISO_15765_4_11_500
    if isinstance(ble_parameters, dict) and not ble_parameters:
        ble_parameters = asyncio.run(scan_ble(device_names))
    if ble_parameters:
        device_address = ble_parameters['device_addr']
        bt_uart = BleUartBridge(**ble_parameters)
        bt_uart.start()
        scanner_parameters['serial_name'] = bt_uart.port
    else:
        if not btc_parameters:
            btc_parameters = scan_btc(device_names)
            if not btc_parameters:
                raise OSError(f'No Bluetooth device {device_names} found')
        device_address = btc_parameters['device_addr']
        device_channel = btc_parameters['channel']
        paired = pair_with_pin(device_address, 1234, timeout=40)
        if not paired:
            raise ConnectionError('Unable to pair Bluetooth using PIN')
        scanner_parameters = {
            'bluetooth': (device_address, device_channel),
        }
    try:
        scanner_parameters['scan_interval'] = 5
        app = ElmScanner(**scanner_parameters)
        app.connect()
        print(f'ELM version: {app.elm._version}')
        print(f'ELM status: {app.elm.status.name}')
        app.start()
    except Exception as err:
        logger.exception(err)
        app.stop()
        # if simulate_vehicle:
        #     vehicle.stop()


if __name__ == '__main__':
    main()
