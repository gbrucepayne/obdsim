"""BLE Adapter for OBDII Scanner.

Run the scanner to create a BleUart class.
Set the serial port name (symlink to /dev/pty/N) - default `/tmp/ttyBLE`.
Start the BleUart.
"""
import asyncio
import atexit
import logging
from asyncio import FIRST_COMPLETED
from typing import Callable

from obdsim.bluetooth import UartPty, UartBle
from bleak import BleakClient, BleakScanner, BLEDevice, BleakError

from obdsim.bluetooth import ADAPTER_NAME

_log = logging.getLogger(__name__)


class BleUartBridge:
    """A Class that bridges a (remote) BLE UART with a (local) PTY UART.
    """
    def __init__(self,
                 device_addr: str,
                 service_uuid: str,
                 tx_uuid: str,
                 rx_uuid: str,
                 timeout: float = 10,
                 port: str = '/tmp/ttyBLE',
                 mtu: int = 20,
                 hci: str = 'hci0',
                 disconnect_handler: Callable = None,
                 ) -> None:
        atexit.register(self._cleanup)
        self.addr = device_addr
        self.service_uuid = service_uuid
        self.tx_uuid = tx_uuid
        self.rx_uuid = rx_uuid
        self.timeout = timeout
        self.port = port
        self.mtu = mtu
        self.hci = hci
        self.uart: UartPty = None
        self.ble: UartBle = None
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
            self.ble = UartBle(self.hci, None)
            self.uart.set_receiver(self.ble.queue_write)
            self.ble.set_receiver(self.uart.queue_write)
            _log.info(f'Linked {self.port} with {self.addr}')
            self.uart.start()
            await self.ble.connect(self.addr,
                                   timeout=self.timeout,
                                   disconnect_handler=self._disconnect_handler)
            await self.ble.setup_chars(self.tx_uuid, self.rx_uuid)
            self._main_tasks = {
                asyncio.create_task(self.ble.run_loop()),
                asyncio.create_task(self.uart.run_loop()),
            }
            done, pending = await asyncio.wait(self._main_tasks,
                                               return_when=FIRST_COMPLETED)
            _log.debug('Completed tasks:'
                       f' {[(t._coro, t.result()) for t in done]}')
            _log.debug(f'Pending tasks: {[t._coro for t in pending]}')
        except BleakError as err:
            _log.error(f'BLE connection failed: {err}')
        except Exception as err:
            _log.exception(f'Unexpected error: {repr(err)}')
        finally:
            self._cleanup()
    
    def _cleanup(self):
        for task in self._main_tasks:
            task.cancel()
        if self.uart:
            self.uart.stop_loop()
            self.uart.remove()
        if self.ble:
            self.ble.stop_loop()
            
    def _exc_handler(self, loop: asyncio.AbstractEventLoop, context):
        _log.debug(f'asyncio exception: {context["exception"]}')
        self._cleanup()
    
    
async def scan_ble(target: str = ADAPTER_NAME, scan_time: int = 5) -> dict:
    """Attempts to connect to a BLE OBD2 scanner and get its GATT services.
    
    Args:
        target: The name of the adapter when scanning bluetooth
            e.g. `OBDII` or `Vlink`
    
    Returns:
        A dictionary with BLE parameters `device_addr`, `service_uuid`,
            `tx_uuid` and `rx_uuid`.
            
    """
    obd_addr = ''
    service_uuid = ''
    rx_uuid = ''
    tx_uuid = ''
    _log.info('Scanning for BLE devices...')
    devices: dict = await BleakScanner().discover(timeout=scan_time,
                                                  return_adv=True)
    _log.debug(f'Found {len(devices)} devices')
    n = 0
    for d, _a in devices.values():
        assert isinstance(d, BLEDevice)
        # assert isinstance(_a, AdvertisementData)
        n += 1
        try:
            if target not in d.name:
                continue
            _log.info(f'Assessing: {d.name} ({d.address})')
            obd_addr = d.address
            async with BleakClient(d) as client:
                if client.services is not None:
                    for service in client.services:
                        if 'Vendor specific' not in str(service):
                            continue
                        for c in service.characteristics:
                            if 'notify' in c.properties:
                                _log.debug('READ:', c, c.properties)
                                rx_uuid = c.uuid
                            elif 'write-without-response' in c.properties:
                                _log.debug('WRITE:', c, c.properties)
                                tx_uuid = c.uuid
                            if rx_uuid and tx_uuid:
                                service_uuid = c.service_uuid
                        if service_uuid:
                            break
            if not all([obd_addr, service_uuid, tx_uuid, rx_uuid]):
                raise OSError(f'Could not find OBD BLE device {ADAPTER_NAME}')
            return {
                'device_addr': obd_addr,
                'service_uuid': service_uuid,
                'tx_uuid': tx_uuid,
                'rx_uuid': rx_uuid,
            }
        except BleakError as err:
            _log.error(err)
            _log.info('Try power cycling OBD reader')
        except Exception as err:
            _log.error(err)


if __name__ == '__main__':
    format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
                '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
    logging.basicConfig(format=format_csv)
    _log.setLevel(logging.INFO)
    try:
        ble_parameters = asyncio.run(scan_ble('Vlink'))
        if not ble_parameters:
            raise OSError('No OBD BLE found or could not connect')
        print(f'Found OBD BLE device {ble_parameters["device_addr"]}')
        ble_uart = BleUartBridge(**ble_parameters)
        ble_uart.start()
    except Exception as err:
        _log.exception(err)
