"""A Bluetooth Low Energy UART forwarder to interact with a stream.

Intended to interface to a psuedo-terminal or socket.

"""
import asyncio
import logging

from bleak import BleakClient
from typing import Callable

_log = logging.getLogger(__name__)


class UartBle():
    """A BLE data forwarder for devices that support UART read/write."""
    def __init__(self, **kwargs):
        self._send_queue = asyncio.Queue()
        self.scan_args = dict(adapter=kwargs.get('hci', 'hci0'))
        if 'service_uuid' in kwargs:
            self.scan_args['service_uuids'] = [kwargs['service_uuid']]
        self._client: BleakClient = None
        self._receiver: Callable = None
        self._read_enabled: bool = True
        self._write_enabled: bool = True
        self._read_uuid: str = None
        self._write_uuid: str = None
        self._disconnect_handler: Callable = None

    async def connect(self,
                      address: str,
                      disconnected_callback: Callable = None,
                      timeout: float = 10,
                      **kwargs) -> None:
        """Connects to the BLE device.
        
        Args:
            address: The MAC address or (for MacOS) UUID.
            disconnected_callback: Optional callback function when a disconnect
                occurs.
            timeout: The maximum number of seconds to wait for connection.
            **kwargs: Optional kwargs for the `BleakClient`
            
        """
        disconnect_cb = disconnected_callback or self._handle_disconnect
        self._client = BleakClient(address_or_ble_device=address,
                                   timeout=timeout,
                                   disconnected_callback=disconnect_cb,
                                   **kwargs)
        self._disconnect_handler = disconnected_callback
        _log.info(f'Trying to connect with {address}')
        await self._client.connect()
        _log.info(f'Device {self._client.address} connected')

    async def setup_gatt(self, write_uuid: str, read_uuid: str) -> None:
        """Configures GATT Characteristics for read/write of UART."""
        self._write_uuid = write_uuid
        self._read_uuid = read_uuid
        await self._client.start_notify(self._read_uuid, self._handle_notify)

    def _handle_notify(self, handle: int, data: bytes):
        """Passes bytes received via BLE to the receiver function."""
        _log.debug(f'Received notify from {handle}: {data}')
        if not self._read_enabled:
            _log.warning(f'Read unexpected data, dropping: {data}')
            return
        if not self._receiver or not callable(self._receiver):
            raise ConnectionError('Missing receiver callback function')
        self._receiver(data)

    def set_receiver(self, callback: 'Callable[[bytes]]') -> None:
        """Sets the receiver callback that will receive `bytes` from the device.
        
        Args:
            callback: The function that will receive `bytes` sent by the device.
        
        """
        self._receiver = callback
        _log.info('Receiver set up')

    async def run_loop(self):
        """Starts the loop checking for `bytes` submitted via `queue_write`.
        
        Putting `None` in the queue will cause the loop to stop after the next
        iteration.
        
        Raises:
            `OSError` if the receiver function has not been defined via
            `set_receiver`.
            
        """
        if not self._receiver:
            raise OSError('Receiver must be defined')
        while True:
            data = await self._send_queue.get()
            if data == None:
                break   #: Let future end on shutdown
            if not self._write_enabled:
                _log.warning(f'Ignoring unexpected write data: {data}')
                continue
            _log.debug(f'Sending {data}')
            await self._client.write_gatt_char(self._write_uuid, data)

    def queue_write(self, data: bytes) -> None:
        """Submits data `bytes` to be sent to the BLE device asynchronoously.
        
        Args:
            data: The bytes to be written.
            
        """
        self._send_queue.put_nowait(data)

    def stop_loop(self) -> None:
        """Stops the writer loop."""
        _log.info('Stopping Bluetooth event loop')
        self._send_queue.put_nowait(None)

    async def disconnect(self) -> None:
        """Stops the reader loop and disconnects from the BLE device."""
        if self._client.is_connected:
            if self._read_uuid:
                await self._client.stop_notify(self._read_uuid)
            await self._client.disconnect()
            _log.info('Bluetooth disconnected')

    def _handle_disconnect(self, client: BleakClient):
        _log.warning(f'Device {client.address} disconnected')
        self.stop_loop()
        if callable(self._disconnect_handler):
            self._disconnect_handler(client.address)
        else:
            raise ConnectionResetError(f'BLE disconnected')
