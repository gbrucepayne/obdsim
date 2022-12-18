import asyncio
import logging
import os

from bleak import BleakClient, BleakScanner, AdvertisementData, BLEDevice

TARGET = os.getenv('ADAPTER_NAME', 'Vlink')

_log = logging.getLogger(__name__)


class ElmBle:
    def __init__(self) -> None:
        self.ble_client = None


async def find_scanner(target: str = TARGET):
    """Attempts to connect to a BLE OBD2 scanner and get its GATT services."""
    devices: dict = await BleakScanner().discover(timeout=5.0, return_adv=True)
    _log.debug(f'Found {len(devices)} devices')
    n = 0
    found = False
    for d, a in devices.values():
        assert isinstance(d, BLEDevice)
        assert isinstance(a, AdvertisementData)
        n += 1
        try:
            if target not in d.name:
                continue
            found = True
            _log.debug(f'Device {n} of {len(devices)}: {d.name} ({d.address})')
            async with BleakClient(d) as client:
                if client.services is not None:
                    for service in client.services:
                        _log.debug(f'\t{service}')
        except Exception as err:
            _log.error(err)
    if not found:
        _log.warning(f'Device {TARGET} not found')


if __name__ == '__main__':
    asyncio.run(find_scanner())
