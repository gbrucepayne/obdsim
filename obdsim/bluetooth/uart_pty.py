import asyncio
import os
import pty
import tty
import termios
import logging
from typing import Callable

_log = logging.getLogger(__name__)


class UartPty:
    """A virtual UART based on a pseudo-terminal with a symbolic link."""
    def __init__(self,
                 port: str,
                 receiver: Callable = None,
                 loop: asyncio.AbstractEventLoop = None,
                 mtu: int = 20,
                 ):
        self.loop = loop or asyncio.get_event_loop()
        self.mtu = mtu
        self._send_queue = asyncio.Queue()
        self._receiver = receiver
        self._controller_fd, endpoint_fd = pty.openpty()
        self.endpoint_path = os.ttyname(endpoint_fd)
        tty.setraw(self._controller_fd, termios.TCSANOW)
        self._symlink = port
        self._create_pty_symlink()
    
    def _create_pty_symlink(self) -> None:
        if os.path.exists(self._symlink):
            try:
                os.stat(self._symlink)
                _log.warning('Removing valid symlink'
                             f' {os.readlink(self._symlink)}')
            except OSError:
                _log.info(f'Removing broken symlink {self._symlink}')
            os.remove(self._symlink)
        try:
            os.symlink(self.endpoint_path, self._symlink)
        except FileExistsError as err:
            if not os.path.exists(os.readlink(self._symlink)):
                raise OSError(f'Broken symlink {self._symlink}')
            _log.warning(f'Symlink already exists: {err}')
        _log.info('Port endpoint created on'
                  f' {self._symlink} -> {self.endpoint_path}')
        
    def set_receiver(self, callback: Callable):
        """Configures the receiver function for data received on the pty."""
        self._receiver = callback

    def start(self):
        """Starts monitoring the pty for incoming data."""
        if not self._receiver:
            raise ConnectionError('No receiver defined')
        # Register the file descriptor for read event
        self.loop.add_reader(self._controller_fd, self._read_handler)

    def stop_loop(self):
        """Gracefully exits the sender loop."""
        _log.info('Stopping serial event loop')
        self._send_queue.put_nowait(None)

    def remove(self):
        """Stops monitoring the pty and removes the symlink."""
        # Unregister the fd
        self.loop.remove_reader(self._controller_fd)
        if os.path.exists(self._symlink):
            os.remove(self._symlink)
        _log.info(f'Serial reader and symlink removed')

    def _read_handler(self):
        data = os.read(self._controller_fd, self.mtu)
        _log.debug(f'Read: {data}')
        self._receiver(data)

    def queue_write(self, value: bytes):
        """Writes data to the pty queue."""
        self._send_queue.put_nowait(value)

    async def run_loop(self):
        """Starts the loop sending queued data."""
        while True:
            data = await self._send_queue.get()
            if data == None:
                break # Let future end on shutdown
            _log.debug(f'Write: {data}')
            os.write(self._controller_fd, data)
