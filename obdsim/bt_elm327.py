import bluetooth


def scan(name: str = 'Vlink') -> str:
    print('Scanning for bluetooth devices...')
    devices = bluetooth.discover_devices(duration=8,
                                         lookup_names=True,
                                         lookup_class=False,
                                         flush_cache=True)
    print(f'Found {len(devices)} devices')
    for addr, name in devices:
        if 'Vlink' not in name:
            continue
        return addr


if __name__ == '__main__':
    scan()
