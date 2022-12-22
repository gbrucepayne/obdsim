import asyncio
import atexit
import logging
import os
import subprocess
from typing import Callable
from asyncio import FIRST_COMPLETED

import bluetooth

from obdsim.bluetooth import ADAPTER_NAME, UartPty, UartBtc

_log = logging.getLogger(__name__)


class BtcUartBridge:
    """A Class that bridges a (remote) BLE UART with a (local) PTY UART.
    """
    def __init__(self,
                 device_addr: str,
                 device_name: str = None,
                 channel: int = 1,
                 timeout: float = 10,
                 port: str = '/tmp/ttyBTC',
                 mtu: int = 20,
                 disconnect_handler: Callable = None,
                 ) -> None:
        atexit.register(self._cleanup)
        self.addr = device_addr
        self.name = device_name or device_addr
        self.channel = channel
        self.timeout = timeout
        self.port = port
        self.mtu = mtu
        self.uart: UartPty = None
        self.btc: UartBtc = None
        self._main_tasks: 'dict[asyncio.Task]' = {}
        self._disconnect_handler: Callable = disconnect_handler
    
    def start(self):
        """Starts the UART process."""
        asyncio.run(self._run())
    
    async def _run(self):
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(self._exc_handler)
            self.uart = UartPty(self.port, loop=loop, mtu=self.mtu)
            self.btc = UartBtc(loop=loop)
            self.uart.set_receiver(self.btc.queue_write)
            self.btc.set_receiver(self.uart.queue_write)
            _log.info(f'Linked {self.port} with {self.addr}')
            self.uart.start()
            self.btc.connect(self.addr,
                             port=self.channel,
                             timeout=self.timeout,
                             disconnect_handler=self._disconnect_handler)
            self._main_tasks = {
                asyncio.create_task(self.btc.run_recv_loop()),
                asyncio.create_task(self.btc.run_send_loop()),
                asyncio.create_task(self.uart.run_loop()),
            }
            done, pending = await asyncio.wait(self._main_tasks,
                                               return_when=FIRST_COMPLETED)
            _log.debug('Completed tasks:'
                       f' {[(t._coro, t.result()) for t in done]}')
            _log.debug(f'Pending tasks: {[t._coro for t in pending]}')
        except Exception as err:
            _log.exception(f'Unexpected error: {repr(err)}')
    
    def _cleanup(self):
        for task in self._main_tasks:
            task.cancel()
        if self.uart:
            self.uart.stop_loop()
            self.uart.remove()
        if self.btc:
            self.btc.stop_recv_loop()
            self.btc.stop_send_loop()
            self.btc.disconnect()
            
    def _exc_handler(self, loop: asyncio.AbstractEventLoop, context):
        _log.debug(f'asyncio exception: {context["exception"]}')
        self._cleanup()


def scan_btc(target: 'str|list[str]' = ADAPTER_NAME,
             duration: int = 10) -> dict:
    """Scans for 'Classic' Bluetooth serial devices based on a target name.
    
    Args:
        target: The friendly name of the Bluetooth Adapter e.g. `Android-Vlink`
            or `OBDII`. Can be set as an environment variable `ADAPTER_NAME`.
        duration: The maximum scan time before failing.
    
    Returns:
        A dictionary with connection parameters `device_addr`, `channel`.
        
    """
    if not isinstance(target, (str, list)):
        raise ValueError('Invalid target must be string or list of strings.')
    if isinstance(target, str):
        target = [target]
    btc_parameters = {}
    required = ('device_addr', 'channel')
    sp_service = False
    _log.info('Scanning for bluetooth devices...')
    devices = bluetooth.discover_devices(duration=duration,
                                         lookup_names=True,
                                         lookup_class=True,
                                         flush_cache=True)
    _log.info(f'Found {len(devices)} devices')
    for addr, name, _class in devices:
        if not any(t in name for t in target):
            # _log.debug(f'Skipping {name}')
            continue
        _log.info(f'Assessing device {name} ({addr})')
        btc_parameters['device_name'] = name
        btc_parameters['device_addr'] = addr
        services = bluetooth.find_service(address=addr)
        if not services:
            _log.info(f'Using SDP to find Serial Port service...')
            cmd = f'sdptool search --bdaddr {addr} SP'
            res = subprocess.run(cmd.split(' '), stdout=subprocess.PIPE)
            cmd_response = [r.strip() for r in res.stdout.decode().split('\n')]
            for line in cmd_response:
                if any(s in line for s in ('Serial Port', 'RFCOMM')):
                    sp_service = True
                if line.startswith('Channel:'):
                    btc_parameters['channel'] = int(line.split(':')[1])
                if sp_service and 'channel' in btc_parameters:
                    break   # found; iteration complete
        else:
            _log.warning('UNTESTED bluetooth [services]')
            for service in services:
                if 'port' in service:
                    btc_parameters['channel'] = int(service['port'])
        if not sp_service:
            _log.warning('Unable to verify Serial Port service or UUID')
        if not all(p in btc_parameters for p in required):
            btc_parameters = {}
        return btc_parameters
    

if __name__ == '__main__':
    format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
                '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
    logging.basicConfig(format=format_csv)
    _log.setLevel(logging.INFO)
    try:
        btc_name = ['Vlink', 'OBDII']
        bt_parameters = scan_btc(btc_name)
        if not bt_parameters:
            raise OSError(f'No Bluetooth device {btc_name} found')
        print(f'Found OBD BT Device:({bt_parameters})')
        btc_uart = BtcUartBridge(**bt_parameters)
        btc_uart.start()
    except Exception as err:
        _log.exception(err)
