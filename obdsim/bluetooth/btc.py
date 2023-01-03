"""Helpers to identify and connect to a Bluetooth *Classic* OBD2 adapter.

Usage:

* Run the scanner to detect the OBD2 adapter and get kwarg parameters.
* Create a BtcUartBridge using the parameters.
* Set the serial port name (symlink to /dev/pty/N) - default `/tmp/ttyBTC`.
* Start the BtcUartBridge.

"""
import asyncio
import atexit
import logging
import sys
import threading
from asyncio import FIRST_COMPLETED
from typing import Callable

import bluetooth
import pexpect

from obdsim.bluetooth import ADAPTER_NAME, UartBtc, UartPty

_log = logging.getLogger(__name__)


class BtcUartBridge:
    """A Class that bridges a (remote) BLE UART with a (local) PTY UART.
    
    Attributes:
        addr (str): The Bluetooth MAC address.
        name (str): The Bluetooth adapter name.
        channel (int): The channel being used for RFCOMM/SPP (default 1).
        timeout (float): The Bluetooth connection timeout in seconds.
        port (str): The virtual serial port name (default `/tmp/ttyBTC`).
        disconnect_handler (Callable): Optional callback when Bluetooth
            disconnects.
        
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
        """Instantiates the UART Bridge.
        
        Args:
            device_addr (str): The Bluetooth MAC address.
            device_name (str): (optional) Device name.
            channel (int): The channel/port used for RFCOMM/SPP.
            timeout (float): The connection timeout in seconds.
            port (str): The virtual serial port name (default `/tmp/ttyBTC`).
        
        """
        atexit.register(self._cleanup)
        self.addr = device_addr
        self.name = device_name or device_addr
        self.channel = channel
        self.timeout = timeout
        self.port = port
        self.mtu = mtu
        self._pty: UartPty = None
        self._btc: UartBtc = None
        self._main_tasks: 'dict[asyncio.Task]' = {}
        self._disconnect_handler: Callable = disconnect_handler
        self._thread: threading.Thread = None
        self._loop: asyncio.AbstractEventLoop = None
    
    def start(self):
        """Starts the UART process."""
        self._thread = threading.Thread(target=self._daemon_start,
                                        name='BtcUartBridgeThread',
                                        daemon=True)
        self._thread.start()
    
    def _daemon_start(self):
        asyncio.run(self._run())
        
    async def _run(self):
        try:
            self._loop = asyncio.get_event_loop()
            self._loop.set_exception_handler(self._exc_handler)
            self._pty = UartPty(self.port, loop=self._loop, mtu=self.mtu)
            self._btc = UartBtc(loop=self._loop)
            self._pty.set_receiver(self._btc.queue_write)
            self._btc.set_receiver(self._pty.queue_write)
            _log.info(f'Linked {self.port} with {self.addr}')
            self._pty.start()
            self._btc.connect(self.addr,
                             port=self.channel,
                             timeout=self.timeout,
                             disconnect_handler=self._disconnect_handler)
            self._main_tasks = {
                asyncio.create_task(self._btc.run_recv_loop()),
                asyncio.create_task(self._btc.run_send_loop()),
                asyncio.create_task(self._pty.run_loop()),
            }
            done, pending = await asyncio.wait(self._main_tasks,
                                               return_when=FIRST_COMPLETED)
            _log.debug('Completed tasks:'
                       f' {[(t._coro, t.result()) for t in done]}')
            _log.debug(f'Pending tasks: {[t._coro for t in pending]}')
        except Exception as err:
            _log.exception(f'Unexpected error: {repr(err)}')
            raise err
    
    @property
    def initialized(self) -> bool:
        if self._btc:
            return self._btc.initialized
        return False
        
    def _cleanup(self):
        for task in self._main_tasks:
            task.cancel()
        if self._pty:
            self._pty.stop_loop()
            self._pty.remove()
        if self._btc:
            self._btc.stop_recv_loop()
            self._btc.stop_send_loop()
            self._btc.disconnect()
            
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
    _log.debug(f'Found {len(devices)} devices')
    for addr, name, _class in devices:
        if not any(t in name for t in target):
            # _log.debug(f'Skipping {name}')
            continue
        _log.info(f'Assessing device {name} ({addr})')
        btc_parameters['device_name'] = name
        btc_parameters['device_addr'] = addr
        services = bluetooth.find_service(address=addr)
        if not services:
            _log.debug(f'Using SDP to check Serial Port service for {addr}')
            cmd = f'sdptool search --bdaddr {addr} SP'
            res: str = pexpect.run(cmd).decode()
            cmd_response = [r.strip() for r in res.split('\n')]
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
        else:
            _log.info(f'Found candidate: {btc_parameters}')
        return btc_parameters
    

def pair_with_pin(addr: str,
                  pin: 'int|str',
                  timeout: int = 30,
                  debug: bool = False) -> bool:
    """Launches a child process to supply the OBD2 PIN for pairing.
    
    Args:
        addr: The Bluetooth MAC address.
        pin: The PIN of the device.
        debug: Enables verbose output to stdout.

    """
    cmd_sequence = {
        'scan on': addr,
        'scan off': '# ',
        f'pair {addr}': 'Enter PIN code:',
        f'{pin}': '# ',
        'paired-devices': addr,
        'exit': pexpect.EOF,
    }
    try:
        paired: str = pexpect.run('bluetoothctl paired-devices').decode()
        if addr in paired:
            _log.info(f'Found {addr} in paired-devices')
            return True
        _log.info('Spawning bluetoothctl for PIN pairing...')
        analyzer = pexpect.spawn(command='bluetoothctl',
                                 encoding='utf-8',
                                 timeout=timeout)
        if debug:
            analyzer.logfile_read = sys.stdout
        analyzer.expect_exact('# ')
        for cmd, exp in cmd_sequence.items():
            _log.info(f'Sending "{cmd}"')
            analyzer.sendline(cmd)
            if isinstance(exp, str):
                _log.info(f'Waiting for {exp}')
            analyzer.expect_exact(exp)
        return True
    except Exception as err:
        _log.error(err)
        return False


def forget_device(device_address: str):
    """Removes the device from the host's list."""
    res = pexpect.run(f'bluetoothctl remove {device_address}').decode()
    if 'removed' not in res:
        _log.warning(f'Device {device_address} may not have been removed')


if __name__ == '__main__':
    import time
    DURATION = 60
    format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
                '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
    logging.basicConfig(format=format_csv, level=logging.INFO)
    try:
        btc_name = ['Vlink', 'OBDII']
        bt_parameters = scan_btc(btc_name)
        if not bt_parameters:
            raise OSError(f'No Bluetooth device {btc_name} found')
        mac = bt_parameters['device_addr']
        paired = pair_with_pin(mac, 1234)
        if not paired:
            raise ConnectionError(f'Unable to pair with {mac}')
        btc_uart = BtcUartBridge(**bt_parameters)
        btc_uart.start()
        while not btc_uart.initialized:
            time.sleep(1)
        start_time = time.time()
        while time.time() - start_time < DURATION:
            elapsed = int(time.time() - start_time)
            if elapsed % 10 == 0:
                _log.info(f'Remaining: {int(DURATION - elapsed)} seconds...')
            time.sleep(1)
    except Exception as err:
        _log.exception(err)
