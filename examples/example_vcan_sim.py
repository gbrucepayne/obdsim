import logging
import os
import sys

sys.path.append(f'{os.getcwd()}')

from obdsim import ObdSimulator
from obdsim.scanner import CanScanner
from obdsim.utils.vcan import create_vcan

format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
              '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter(format_csv)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def main():
    if not os.path.exists('/sys/class/net/vcan0'):
        create_vcan('vcan0')
    vehicle = ObdSimulator('vcan0')
    vehicle.connect()
    vehicle.start()
    app = CanScanner('vcan0')
    app.connect()
    vin_msg_count = app.query(pid=1, mode=9)
    vin = app.query(pid=2, mode=9)
    print(f'VIN = {vin.value}')
    app.start()


if __name__ == '__main__':
    main()
