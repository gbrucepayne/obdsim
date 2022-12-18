# Setup

The low cost Tonwon Pro BLE 4.0 that I bought has almost no documentation.
Apparently it has a dual Bluetooth chip that supports both traditional
Bluetooth and BLE. I couldn't find any detail on the GATT model so using
traditional BT is the start point.

>Because the Tonwon goes into a low power mode after a period of inactivity,
I found I had to remove/re-insert it on the OBD port to have it connect
sometimes.

These adapters are all based on ELM327, and the open-source/GPL
[`python-obd`](https://github.com/brendan-w/python-OBD)
library has a nice framework for interacting with them over bluetooth or USB.

## Manual Bluetooth

This setup is the quick and dirty approach to mapping the scanner to an RF
serial link.

```
$ bluetoothctl
[bluetooth]# power on
[bluetooth]# pairable on
[bluetooth]# agent on
[bluetooth]# default-agent
[bluetooth]# scan on
```
Find the scanner name e.g. containing **Vlink** and copy its MAC address.
```
[bluetooth]# pair <MAC>
[bluetooth]# trust <MAC>
[bluetooth]# quit
```

Next bind the adapter to a serial port `/dev/rfcomm0`:
```
sudo rfcomm bind rfcomm0 <MAC>
```

## BLE with Python

>:warning: I didn't really get this working since the GATT model for the Tonwon
scanner is unclear.

The package I used for this is [`bleak`](https://github.com/hbldh/bleak)

When using Poetry I needed to manually force setuptools==58 due to a
known issue with PyBluez `use_2to3 is invalid`:
```
poetry run pip install 'setuptools==58'
poetry install
```

On Debian/Raspberry Pi you may need to install bluetooth dev tools:
```
sudo apt-get install libbluetooth-dev
```