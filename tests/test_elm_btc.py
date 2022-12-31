from obdsim.bluetooth.btc import BtcUartBridge, scan_btc


def test_scan_btc():
    btc_name = ['Vlink', 'OBDII']
    bt_parameters = scan_btc(btc_name)
    if not bt_parameters:
        raise OSError(f'No Bluetooth device {btc_name} found')
    print(f'Found OBD BT Device:({bt_parameters})')
    btc_uart = BtcUartBridge(**bt_parameters)
    btc_uart.start()
    