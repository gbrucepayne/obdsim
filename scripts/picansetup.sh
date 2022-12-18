#!/bin/bash
# Sets up Raspberry Pi overlay and SPI
function help() {
  echo "Enables or disables CANbus via MCP2515 chip using SPI interface"
  echo " *** Must be run as root/sudo"
  echo "Syntax: sudo bash $0 -e 1"
  echo "  options:"
  echo -e "\t-e\tEnable=1, Disable=0"
}

while getopts ":he:" 'OPTKEY'; do
  case "${OPTKEY}" in
    h)
      help
      exit 0
      ;;
    e)
      ENABLE="${OPTARG}"
      ;;
    \?)
      echo "ERROR: invalid option -${OPTARG}"
      exit 1
      ;;
  esac
done

if [ "$(id -u)" != 0 ]; then
  echo "You must run this script as root or sudo"
  exit 1
fi

if [ "${ENABLE}" == 1 ]; then
  if [ -z "$(grep '^dtoverlay=mcp2515' /boot/config.txt)" ]; then
    sed -i '/^# Additional overlays/a dtoverlay=mcp2515-can0,oscillator=12000000,interrupt=25,spimaxfrequency=2000000' /boot/config.txt
  fi
  if [ -z "$(grep '^dtoverlay=spi-bcm2835' /boot/config.txt)" ]; then
    sed -i '/^dtoverlay=mcp2515/a dtoverlay=spi-bcm2835' /boot/config.txt
  fi
  if [ -n "$(grep '^dtparam=spi=off' /boot/config.txt)" ]; then
    sed -i 's/^dtparam=spi=off/dtparam=spi=on/' /boot/config.txt
  fi
else
  if [ -n "$(grep '^dtoverlay=mcp2515' /boot/config.txt)"]; then
    sed -i '/^dtoverlay=mcp2515/d' /boot/config.txt
  fi
  if [ -n "$(grep '^dtoverlay=spi-bcm2835' /boot/config.txt)" ]; then
    sed -i '/^dtoverlay=sp-bcm2835/d' /boot/config.txt
  fi
  if [ -n "$(grep '^dtparam=spi=on' /boot/config.txt)" ]; then
    sed -i 's/^dtoverlay=spi=on/dtoverlay=spi=off/' /boot/config.txt
  fi
fi
