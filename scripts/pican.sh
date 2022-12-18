#!/bin/bash
# Sets up can0 on Raspberry Pi with Waveshare CAN/RS485 HAT
NAME="can0"
BITRATE="500000"

function help() {
  echo "Usage: sudo bash $0 -e 1 [-n <name>][-b <bitrate>]"
}

while getopts ":he:n:b:" 'OPTKEY'; do
  case "${OPTKEY}" in
    h)
      help
      exit 0
      ;;
    e)
      ENABLE="${OPTARG}"
      ;;
    n)
      NAME="${OPTARG}"
      ;;
    b)
      if [ "${OPTARG}" == "250000" ] || [ "${OPTARG}" == "500000" ]; then
        BITRATE="${OPTARG}"
      else
        echo "ERROR: invalid bitrate ${OPTARG}"
        exit 1
      fi
      ;;
    \?)
      echo "Invalid option ${OPTKEY}"
      exit 1
      ;;
  esac
done

if [ "$(id -u)" != 0 ]; then
  echo "This script must be run as root/sudo"
  exit 1
fi

if [ "${ENABLE}" == 1 ]; then
  modprobe can
  modprobe can_raw
  ip link set up "${NAME}" type can bitrate 500000 restart-ms 100
else
  ip link set "${NAME}" down
  ip link delete "${NAME}"
fi
