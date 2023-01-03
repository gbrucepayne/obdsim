"""UART model for 'Classic' Bluetooth interfaces.

This is a work in progress and currently broken. Use at your own risk.

"""
import asyncio
import logging
import socket
from asyncio import AbstractEventLoop, StreamReader, StreamWriter
from typing import Callable

from bluetooth import BluetoothError

_log = logging.getLogger(__name__)


class UartBtc():
    def __init__(self, loop: AbstractEventLoop = None):
        self.loop: AbstractEventLoop = loop or asyncio.get_running_loop()
        self._stall_loop = asyncio.Event()
        self._send_queue = asyncio.Queue()
        self._addr: str = None
        self._client = socket.socket(socket.AF_BLUETOOTH,
                                     socket.SOCK_STREAM,
                                     socket.BTPROTO_RFCOMM)
        self._receiver: Callable = None
        self._recv_buffer: int = 100
        self._read_enabled: bool = True
        self._write_enabled: bool = True
        self._reader: StreamReader = None
        self._reading: bool = False
        self._writer: StreamWriter = None
        self._disconnect_handler: Callable = None
        self._version: str = ''

    def connect(self,
                addr: str,
                port: int = 1,
                timeout: float = 6,
                disconnect_handler: Callable = None,
                ):
        """Connects to the specified Bluetooth Classic device."""
        try:
            self._client.setblocking(False)
            res = self._client.connect_ex((addr, port))
            if res != 115:
                raise BluetoothError(f'Result code {res}')
            # self._client.settimeout(timeout)
            # self._client.connect((addr, port))
            self._addr = addr
            _log.info(f'Connected to {addr}')
            self._disconnect_handler = disconnect_handler
            self._stall_loop.set()
        except (BluetoothError, OSError) as err:
            if err.errno == 115:
                return
            elif '52' in str(err):
                _log.warning('Suspected PIN problem')
            _log.exception(err)
            raise err

    async def run_recv_loop(self):
        """Starts the loop listening for data from the Bluetooth device."""
        assert callable(self._receiver), f'Receiver must be configured first'
        self._reading = True
        while self._reading:
            try:
                data = await self.loop.sock_recv(self._client,
                                                 self._recv_buffer)
                self._receiver(data)
                # await asyncio.sleep(0)
            except (ConnectionError, OSError) as err:
                if err.errno == 111:
                    _log.warning('Connection refused')
                elif err.errno == 52:
                    _log.error('Suspected PIN problem')
                else:
                    _log.exception(err)
                    self._handle_disconnect()
                    raise err

    def stop_recv_loop(self):
        """Gracefully stops the reader loop."""
        self._reading = False
        
    def set_receiver(self, callback):
        """Configures the receiver for data arriving from the BLE device."""
        self._receiver = callback
        _log.info('Receiver set up')

    async def run_send_loop(self):
        """Starts the loop forwarding data to the BLE device."""
        if not self._receiver:
            raise OSError('Receiver must be defined')
        while True:
            data = await self._send_queue.get()
            if data == None:
                break # Let future end on shutdown
            if not self._write_enabled:
                _log.warning(f'Ignoring unexpected write data: {data}')
                continue
            await self._stall_loop.wait()
            self._stall_loop.clear()
            _log.debug(f'Sending {data}')
            await self.loop.sock_sendall(self._client, data)
            self._stall_loop.set()

    def stop_send_loop(self):
        """Gracefully stops the data forwarding loop."""
        _log.info('Stopping Bluetooth event loop')
        self._send_queue.put_nowait(None)

    def disconnect(self):
        """Stops the reader and disconnects from the BLE device."""
        self._client.close()

    def queue_write(self, data: bytes):
        """Queues data to write to the BLE device."""
        self._send_queue.put_nowait(data)

    def _handle_disconnect(self):
        _log.warning(f'Device {self._addr} disconnected')
        self.stop_send_loop()
        self.stop_recv_loop()
        if callable(self._disconnect_handler):
            self._disconnect_handler(self._addr)
