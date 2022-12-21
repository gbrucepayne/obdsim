import logging

import bluetooth

from . import ADAPTER_NAME

_log = logging.getLogger(__name__)


def scan_bt(target: str = ADAPTER_NAME, duration: int = 8) -> str:
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
