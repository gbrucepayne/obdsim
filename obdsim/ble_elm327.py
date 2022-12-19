"""BLE Adapter for OBDII Scanner.

Work in progress...
"""
import asyncio
import logging
import os

import bluetooth
from bleak import BleakClient, BleakScanner, AdvertisementData, BLEDevice

TARGET = os.getenv('ADAPTER_NAME', 'Vlink')


_log = logging.getLogger(__name__)


async def scan_ble(target: str = TARGET) -> str:
    """Attempts to connect to a BLE OBD2 scanner and get its GATT services."""
    _log.debug('Scanning for BLE devices')
    devices: dict = await BleakScanner().discover(timeout=5.0, return_adv=True)
    _log.info(f'Found {len(devices)} devices')
    n = 0
    for d, a in devices.values():
        assert isinstance(d, BLEDevice)
        assert isinstance(a, AdvertisementData)
        n += 1
        try:
            if target not in d.name:
                continue
            _log.info(f'Device {n} of {len(devices)}: {d.name} ({d.address})')
            async with BleakClient(d) as client:
                if client.services is not None:
                    _log.info(f'Services: {[str(s) for s in client.services]}')
                    print(f'Services: {[str(s) for s in client.services]}')
            return d.address
        except Exception as err:
            _log.error(err)


def scan_bt(target: str = TARGET, duration: int = 8) -> str:
    _log.debug('Scanning for bluetooth devices...')
    print('Scanning for bluetooth devices...')
    devices = bluetooth.discover_devices(duration=duration,
                                         lookup_names=True,
                                         lookup_class=False,
                                         flush_cache=True)
    _log.info(f'Found {len(devices)} devices')
    for addr, name in devices:
        if target not in name:
            continue
        services = bluetooth.find_service(address=addr)
        print(f'BT Services: {services}')
        return addr


if __name__ == '__main__':
    addr = scan_bt()
    while addr is None:
        addr = scan_bt()
    if addr:
        print(f'Found Bluetooth {TARGET}: {addr}')
    else:
        addr = asyncio.run(scan_ble())
        if addr:
            print(f'Found BLE {TARGET}: {addr}')
    if addr:
        service_matches = bluetooth.find_service(address=addr)
        # print(f'First match: {service_matches[0]}')
        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        sock.connect((addr, 1))
        sock.send('AT')
        response = sock.recv(1024)
        print(f'AT response: {response}')
    else:
        print(f'{TARGET} not found')
