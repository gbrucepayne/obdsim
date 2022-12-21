import asyncio
import logging

from bleak import BleakClient
from typing import Callable

_log = logging.getLogger(__name__)


class UartBle():
    def __init__(self, hci: str = 'hci0', service_uuid: str = None):
        self._send_queue = asyncio.Queue()
        self.scan_args = dict(adapter=hci)
        if service_uuid:
            self.scan_args['service_uuids'] = [service_uuid]
        self._client: BleakClient = None
        self._receiver: Callable = None
        self._read_enabled: bool = True
        self._write_enabled: bool = True
        self._read_uuid: str = None
        self._write_uuid: str = None
        self._disconnect_handler: Callable = None

    async def connect(self,
                      addr: str,
                      disconnect_handler: Callable = None,
                      addr_type: str = 'public',
                      timeout: float = 10):
        # address_type used only in Windows .NET currently
        self._client = BleakClient(addr,
                                   address_type=addr_type,
                                   timeout=timeout,
                                   disconnected_callback=self._handle_disconnect)
        self._disconnect_handler = disconnect_handler
        _log.info(f'Trying to connect with {addr}')
        await self._client.connect()
        _log.info(f'Device {self._client.address} connected')

    async def setup_chars(self,
                          write_uuid: str,
                          read_uuid: str,
                          mode: str = 'rw'):
        self._write_uuid = write_uuid
        self._read_uuid = read_uuid
        self._read_enabled = 'r' in mode
        self._write_enabled = 'w' in mode
        # if self._write_enabled:
        #     write_props = ['write', 'write-without-response']
        #     self._write_char = self.find_char(write_uuid, write_props)
        if self._read_enabled:
            # read_props = ['notify', 'indicate']
            # self._read_char = self.find_char(read_uuid, read_props)
            await self._client.start_notify(self._read_uuid, self._handle_notify)
        else:
            _log.info('Reading disabled, skipping read UUID detection')

    def set_receiver(self, callback):
        self._receiver = callback
        _log.info('Receiver set up')

    async def run_loop(self):
        if not self._receiver:
            raise OSError('Receiver must be defined')
        while True:
            data = await self._send_queue.get()
            if data == None:
                break # Let future end on shutdown
            if not self._write_enabled:
                _log.warning(f'Ignoring unexpected write data: {data}')
                continue
            _log.debug(f'Sending {data}')
            await self._client.write_gatt_char(self._write_uuid, data)

    def stop_loop(self):
        _log.info('Stopping Bluetooth event loop')
        self._send_queue.put_nowait(None)

    async def disconnect(self):
        if self._client.is_connected:
            if self._read_uuid:
                await self._client.stop_notify(self._read_uuid)
            await self._client.disconnect()
            _log.info('Bluetooth disconnected')

    def queue_write(self, data: bytes):
        self._send_queue.put_nowait(data)

    def _handle_notify(self, handle: int, data: bytes):
        _log.debug(f'Received notify from {handle}: {data}')
        if not self._read_enabled:
            _log.warning(f'Read unexpected data, dropping: {data}')
            return
        self._receiver(data)

    def _handle_disconnect(self, client: BleakClient):
        _log.warning(f'Device {client.address} disconnected')
        self.stop_loop()
        if callable(self._disconnect_handler):
            self._disconnect_handler(client.address)
