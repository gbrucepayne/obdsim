import logging
import os
import subprocess

_log = logging.getLogger(__name__)


def create_vcan(bus_name: str = 'vcan0') -> str:
    _log.debug(f'Attempting to create virtual {bus_name}')
    sys_name = f'/sys/class/net/{bus_name}'
    shell_commands = [
        'sudo modprobe vcan',
        f'sudo ip link add dev {bus_name} type vcan',
        f'sudo ip link set {bus_name} up',
    ]
    for command in shell_commands:
        rc = subprocess.run(command.split(' ')).returncode
        if rc != 0:
            _log.warning(f'{command} failed with return code {rc}')
            raise OSError
    if not os.path.exists(sys_name):
        raise FileNotFoundError(f'Cannot find {sys_name}')
