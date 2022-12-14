"""BLE Adapter for OBDII Scanner.

Usage:

* Run the scanner to detect the OBD2 adapter and get kwarg parameters.
* Create a BleUartBridge using the parameters.
* Set the serial port name (symlink to /dev/pty/N) - default `/tmp/ttyBLE`.
* Start the BleUartBridge.

"""
import asyncio
import atexit
import logging
import threading
from asyncio import FIRST_COMPLETED
from typing import Callable

from bleak import BleakClient, BleakError, BleakScanner, BLEDevice

from obdsim.bluetooth import ADAPTER_NAME, UartBle, UartPty

_log = logging.getLogger(__name__)


class BleUartBridge:
    """A Class that bridges a (remote) BLE UART with a (local) PTY UART.
    """
    def __init__(self,
                 device_addr: str,
                 service_uuid: str,
                 tx_uuid: str,
                 rx_uuid: str,
                 device_name: str = None,
                 timeout: float = 10,
                 port: str = '/tmp/ttyBLE',
                 mtu: int = 20,
                 hci: str = 'hci0',
                 disconnect_handler: Callable = None,
                 ) -> None:
        atexit.register(self._cleanup)
        self.addr = device_addr
        self.name = device_name or device_addr
        self.service_uuid = service_uuid
        self.tx_uuid = tx_uuid
        self.rx_uuid = rx_uuid
        self.timeout = timeout
        self.port = port
        self.mtu = mtu
        self.hci = hci
        self._pty: UartPty = None
        self._ble: UartBle = None
        self._main_tasks: 'dict[asyncio.Task]' = {}
        self._on_disconnect: Callable = disconnect_handler
        self._thread: threading.Thread = None
        self._loop: asyncio.AbstractEventLoop = None
    
    def start(self):
        """Starts the UART process."""
        self._thread = threading.Thread(target=self._daemon_start,
                                        name='BleUartBridgeThread',
                                        daemon=True)
        self._thread.start()
    
    def _daemon_start(self):
        asyncio.run(self._run())
        
    async def _run(self):
        try:
            self._loop = asyncio.get_event_loop()
            self._loop.set_exception_handler(self._exc_handler)
            self._pty = UartPty(self.port, loop=self._loop, mtu=self.mtu)
            self._ble = UartBle()
            self._pty.set_receiver(self._ble.queue_write)
            self._ble.set_receiver(self._pty.queue_write)
            _log.info(f'Linked {self.port} with {self.addr}')
            self._pty.start()
            await self._ble.connect(self.addr,
                                    timeout=self.timeout,
                                    disconnected_callback=self._on_disconnect)
            await self._ble.setup_gatt(self.tx_uuid, self.rx_uuid)
            self._main_tasks = {
                asyncio.create_task(self._ble.run_loop()),
                asyncio.create_task(self._pty.run_loop()),
            }
            done, pending = await asyncio.wait(self._main_tasks,
                                               return_when=FIRST_COMPLETED)
            _log.debug('Completed tasks:'
                       f' {[(t._coro, t.result()) for t in done]}')
            _log.debug(f'Pending tasks: {[t._coro for t in pending]}')
        except (BleakError, ConnectionResetError) as err:
            _log.error(f'BLE connection failed: {err}')
            _log.warning('Some Bleak errors not propagating up...thread hangs?')
            raise err
        except Exception as err:
            _log.exception(f'Unexpected error: {repr(err)}')
            raise err
        finally:
            self._cleanup()
            _log.warning('Attempt to avoid thread hang on Bleak error')
            self._thread.join()
    
    def _cleanup(self):
        for task in self._main_tasks:
            task.cancel()
        if self._ble:
            self._ble.stop_loop()
        if self._pty:
            self._pty.stop_loop()
            self._pty.remove()
            
    def _exc_handler(self, loop: asyncio.AbstractEventLoop, context):
        _log.debug(f'asyncio exception: {context["exception"]}')
        self._cleanup()
    
    
async def scan_ble(target: 'str|list[str]' = ADAPTER_NAME,
                   scan_time: int = 5) -> dict:
    """Attempts to connect to a BLE OBD2 scanner and get its GATT services.
    
    Args:
        target: The name of the adapter when scanning bluetooth
            e.g. `OBDII` or `Vlink`
    
    Returns:
        A dictionary with BLE parameters `device_addr`, `service_uuid`,
            `tx_uuid` and `rx_uuid`.
            
    """
    if not isinstance(target, (str, list)):
        raise ValueError('Invalid target must be string or list of strings')
    if isinstance(target, str):
        target = [target]
    ble_parameters = {}
    required = ('device_addr', 'service_uuid', 'tx_uuid', 'rx_uuid')
    _log.info('Scanning for BLE devices...')
    devices: dict = await BleakScanner().discover(timeout=scan_time,
                                                  return_adv=True)
    _log.debug(f'Found {len(devices)} candidate devices')
    i = 0
    for d, _a in devices.values():
        i += 1
        assert isinstance(d, BLEDevice)
        if not any(t in d.name for t in target):
            # _log.debug(f'Skipping {d.name} ({i} of {len(devices)}')
            continue
        try:
            _log.info(f'Assessing: {d.name} ({d.address})')
            ble_parameters['device_name'] = d.name
            ble_parameters['device_addr'] = d.address
            async with BleakClient(d) as client:
                if client.services is not None:
                    for service in client.services:
                        if 'Vendor specific' not in str(service):
                            continue
                        for c in service.characteristics:
                            if 'notify' in c.properties:
                                _log.debug('READ:', c, c.properties)
                                ble_parameters['rx_uuid'] = c.uuid
                            elif 'write-without-response' in c.properties:
                                _log.debug('WRITE:', c, c.properties)
                                ble_parameters['tx_uuid'] = c.uuid
                            if all(p in ble_parameters for p in
                                   ('rx_uuid', 'tx_uuid')):
                                ble_parameters['service_uuid'] = c.service_uuid
                        if 'service_uuid' in ble_parameters:
                            break   # found UART; services iteration complete
            if all(p in ble_parameters for p in required):
                break   # found target; devices iteration complete
        except BleakError as err:
            _log.error(err)
            _log.info('Try power cycling OBD reader')
        except Exception as err:
            _log.error(err)
        finally:
            if not all(p in ble_parameters for p in required):
                _log.warning(f'Unable to find UART criteria in BLE devices')
                ble_parameters = {}
            return ble_parameters


if __name__ == '__main__':
    import time
    DURATION = 60
    format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
                '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
    logging.basicConfig(format=format_csv, level=logging.INFO)
    try:
        ble_parameters = asyncio.run(scan_ble('Vlink'))
        if not ble_parameters:
            raise OSError('No OBD BLE found or could not connect')
        print(f'Found OBD BLE device: {ble_parameters}')
        ble_uart = BleUartBridge(**ble_parameters)
        ble_uart.start()
        start_time = time.time()
        while int(time.time() - start_time) < DURATION:
            elapsed = int(time.time() - start_time)
            if elapsed % 10 == 0:
                _log.info(f'Remaining: {int(DURATION - elapsed)} seconds...')
            time.sleep(1)
    except Exception as err:
        _log.exception(err)
