import logging
import os
import sys

sys.path.append(f'{os.getcwd()}')

from obdsim.simulator import ObdSimulator
from obdsim.scanners.can import CanScanner

format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
              '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter(format_csv)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def main():
    vehicle = ObdSimulator()
    vehicle.connect()
    vehicle.start()
    app = CanScanner()
    app.connect()
    app.start()


if __name__ == '__main__':
    main()
