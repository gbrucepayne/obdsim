"""BLE Adapter for OBDII Scanner.

Work in progress...
"""
import asyncio
import atexit
import logging

from ble_serial.bluetooth.ble_interface import BLE_interface
from ble_serial.ports.linux_pty import UART
from bleak import AdvertisementData, BleakClient, BleakScanner, BLEDevice, BleakError

from obdsim.bluetooth import ADAPTER_NAME

_log = logging.getLogger(__name__)


class BleUart:
    """A BLE UART class.
    
    TODO: simplify/improve underlying ble-serial?  e.g. 9600 baud only etc
    
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
        self.uart: UART = None
        self.ble: BLE_interface = None
    
    def start(self):
        """"""
        asyncio.run(self._run())
    
    async def _run(self):
        try:
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(self._exc_handler)
            self.uart = UART(self.port, loop, self.mtu)
            self.ble = BLE_interface(self.hci, None)
            self.uart.set_receiver(self.ble.queue_send)
            self.ble.set_receiver(self.uart.queue_write)
            self.uart.start()
            await self.ble.connect(self.addr, 'public', self.timeout)
            await self.ble.setup_chars(self.tx_uuid, self.rx_uuid, 'rw')
            main_tasks = {
                asyncio.create_task(self.ble.send_loop()),
                asyncio.create_task(self.uart.run_loop()),
            }
            done, pending = await asyncio.wait(main_tasks,
                                               return_when=asyncio.FIRST_COMPLETED)
            _log.debug(f'Completed tasks: {[(t._coro, t.result()) for t in done]}')
            _log.debug(f'Pending tasks: {[t._coro for t in pending]}')
        except BleakError as err:
            _log.error(f'BLE connection failed: {err}')
        except Exception as err:
            _log.error(f'Unexpected error: {repr(err)}')
        finally:
            self._cleanup()
    
    def _cleanup(self):
        if self.uart:
            self.uart.stop_loop()
            self.uart.remove()
        if self.ble:
            self.ble.stop_loop()
            self.ble.disconnect()
            
    def _exc_handler(self, loop: asyncio.AbstractEventLoop, context):
        _log.debug(f'asyncio exception handler calle {context["exception"]}')
        self._cleanup()
    
    
async def scan_ble(target: str = ADAPTER_NAME, scan_time: int = 5) -> BleUart:
    """Attempts to connect to a BLE OBD2 scanner and get its GATT services.
    
    Args:
        target: The name of the adapter when scanning bluetooth e.g. `OBDII`
            or `Vlink`
    
    Returns:
        A tuple with the adapter's MAC address, service UUID, write UUID,
            read UUID
    """
    obd_addr = ''
    uart_uuid = ''
    rx_uuid = ''
    tx_uuid = ''
    _log.debug('Scanning for BLE devices')
    devices: dict = await BleakScanner().discover(timeout=scan_time,
                                                  return_adv=True)
    _log.info(f'Found {len(devices)} devices')
    n = 0
    for d, _a in devices.values():
        assert isinstance(d, BLEDevice)
        # assert isinstance(_a, AdvertisementData)
        n += 1
        try:
            if target not in d.name:
                continue
            _log.info(f'Device {n} of {len(devices)}: {d.name} ({d.address})')
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
                                uart_uuid = c.service_uuid
                        if uart_uuid:
                            break
            if not all([obd_addr, uart_uuid, tx_uuid, rx_uuid]):
                raise OSError(f'Could not find OBD BLE device {ADAPTER_NAME}')
            return BleUart(obd_addr, uart_uuid, tx_uuid, rx_uuid)
        except Exception as err:
            _log.error(err)


if __name__ == '__main__':
    try:
        ble_uart = asyncio.run(scan_ble('Vlink'))
        if ble_uart is None:
            print('No OBD BLE found')
        else:
            ble_uart.start()
    except Exception as err:
        _log.error(err)