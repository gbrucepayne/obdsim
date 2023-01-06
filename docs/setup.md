# Setup

## ELM327-based Adapters

The low cost Tonwon Pro BLE 4.0 that I bought had almost no documentation.
Apparently it has a dual Bluetooth chip that supports both traditional
Bluetooth and BLE. I couldn't find any detail on the GATT model, so using
BTC (*Bluetooth Classic*) was my start point. After getting comms to the unit
I determined this device uses ELM327 v2.2.

>Because the Tonwon goes into a low power mode after a period of inactivity,
I found I had to remove/re-insert it on the OBD port to have it connect
sometimes.

Another dongle I bought on the cheap was marked as *Only Work with Android*
which means it does not support BLE 4.0. It was a bit more problematic to get
working, perhaps less tolerant to latency in the serial comms. This device
uses ELM327 v1.5.

These adapters are all based on
[**ELM327**](https://www.elmelectronics.com/wp-content/uploads/2016/07/ELM327DS.pdf),
and most online instructions for using them with a Raspberry Pi or PC focus 
on using Linux **`bluetoothctl`** to pair the device manually, then map to a
`/dev/rfcomm` port as a serial link (see [here](#manual-bluetooth)).

I wanted to find a way to automate all that.

## DBC File

### Resources

* http://mcu.so/Microcontroller/Automotive/DBC_File_Format_Documentation.pdf

## Python CAN BUS tools

The [**`cantools`**](https://cantools.readthedocs.io/en/latest/) library
provides handy facilities for using standardized
[DBC]() files to define the supported OBD2 messages (extensible to other
CAN protocols such as J1939). It also pulls in the
[**`python-can`**](https://python-can.readthedocs.io/en/stable/) library.

>:warning: `cantools.database.can.dbc.grammar` does not support `BS_`:
```
bs = Sequence('BS_', ':')
```

## CSS-Electronics Tools

[CSS Electronics](https://csselectronics.com) has been an invaluable resource.

The samples and tools for developing DBC files were very helpful, in addition
to the basic training on all things OBD/J1939.

Their team also produced a package
[**`can-decoder`**](https://github.com/CSS-Electronics/can_decoder) that
seems highly useful for various types of analysis.

>*Not currently used in this library.*

## Bluetooth with Python on Linux

On Debian/Raspberry Pi you may need to install bluetooth dev tools:
```
sudo apt-get install libbluetooth-dev
```

### Bluetooth Classic

>Several low cost ELM-based devices do not support BLE, these are usually
indicated as not compatible with iOS.

[**`PyBluez`**](https://github.com/pybluez/pybluez) seems to be the most known
base for Bluetooth *Classic* and has experimental support for BLE.

The approach here was to simply open a socket using the `bluetooth` facilities.

>The UART bridge approach similar to BLE was appealing but I could not get it
to work reliably on both OBD2 devices I had, I suspect my implementation was
poor and latency of the bridge was an issue for one of the devices.

However there are some dependency issues installing on Debian-based systems:

* Installing `pyobjc-core` Failed...error: PyObjC requires macOS to build
    * See [issue](https://github.com/python-poetry/poetry/issues/3415) and
    [issue](https://github.com/pybluez/pybluez/issues/431)
    * Workaround: `poetry add git+https://github.com/pybluez/pybluez`
* 

### Bluetooth Low Energy (BLE)

The package I used for this is [**`Bleak`**](https://github.com/hbldh/bleak),
which seems to install fine on its own.

The approach I took was to create a bridge between the
[GATT]https://learn.adafruit.com/introduction-to-bluetooth-low-energy/gatt)
UART service and a pseudoterminal, allowing
[pyserial](https://pyserial.readthedocs.io/en/latest/)
to be used.

#### Resources

* The [BLE Serial](https://github.com/Jakeler/ble-serial) package was helpful
for me to get a better understanding of the undocumented GATT model of the
OBD2 BLE device's serial/UART service.

## Python-OBD

The open-source/GPL
[**`python-obd`**](https://python-obd.readthedocs.io/en/latest/)
library has a nice framework for interacting with ELM327 over USB, or bluetooth
mapped to a `/dev/rfcomm` port (see [here](#manual-bluetooth)).

I started using and trying to align to this package but ended up building my
own simpler model for the **Elm327** interactions and **cantools** DBC use.

The `python-obd` library was particularly helpful with the following concepts:

* Auto-connection to USB or RF port
* Abstraction of Mode/PID commands to human-readable parameters like `SPEED`
* Units (`obd.Unit`) in value calculations allowing easy conversion based on the
[**`Pint`**](https://pint.readthedocs.io/en/latest/) library.
* Timestamp on responses.

However it ended up being limiting in a few key ways:

* Doesn't play well with plain socket-based connection that was reliable with
*Classic* Bluetooth devices, particularly where baud rate is unknown.
* Problematic with serial port names not starting with `/dev/rfcomm` for
Bluetooth or `/dev/pts` for pseudoterminals.
* A bit dated in terms of PEP style and flow making it harder to troubleshoot.
* `OBD.status()` doesn't update after the initial connection.
* Some of the names are counterintuitive e.g. `PIDS_A` rather than `PIDS_01_20`.
* `obd.Async` isn't based on `asyncio`.
* DEBUG logging is verbose and distracting, doesn't follow best practices.
* Only supports Service/Mode 01 current data

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
```
>You may need to enter a passcode, this tends to be `1234` or `0000`.
```
[bluetooth]# trust <MAC>
[bluetooth]# quit
```

Next bind the adapter to a serial port `/dev/rfcomm0`:
```
sudo rfcomm bind rfcomm0 <MAC>
```

When finished it can then be released:
```
sudo rfcomm release rfcomm0
```