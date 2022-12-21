import logging
import os
import sys

sys.path.append(f'{os.getcwd()}')

from obdsim.simulator import ObdSimulator
from obdsim.scanners import CanScanner
from obdsim.vcan import create_vcan

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
    vehicle = ObdSimulator()
    vehicle.connect('vcan0')
    vehicle.start()
    app = CanScanner()
    app.connect('vcan0')
    app.start()


if __name__ == '__main__':
    main()
