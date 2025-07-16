import RPi.GPIO as GPIO
from time import time, sleep
import csv
import os
import spidev
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen

# Pin and file constants
PIN = {
    'RELAY': 16
}

CSV_FILE = {
    'TEMP_DATA': 'Temperature_Data.CSV'
}

INPUT_VOLTAGE = 3.3
ADC_RES = 4096

# GPIO Setup
def GPIO_Setup(pinName, setupPin):
    GPIO.setmode(GPIO.BCM)
    if setupPin.upper() == 'INPUT':
        GPIO.setup(PIN[pinName], GPIO.IN)
        print(f"GPIO {PIN[pinName]} successfully initialized as input")
    elif setupPin.upper() == 'OUTPUT':
        GPIO.setup(PIN[pinName], GPIO.OUT)
        GPIO.output(PIN[pinName], GPIO.HIGH)
        print(f"GPIO {PIN[pinName]} successfully initialized as output")

# CSV handler
class CSVObj:
    def __init__(self):
        self.initialize('TEMP_DATA')
        print("CSV Initialized")

    def initialize(self, file_key):
        if file_key not in CSV_FILE:
            print(f"Error: File key '{file_key}' does not exist in CSV_FILE.")
            return

        file_name = CSV_FILE[file_key]

        if os.path.exists(file_name):
            print(f"File {file_name} exists")
            return
        else:
            with open(file_name, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['Controlled Temp', 'Time (Minutes)', 'Measured Temperature (C)', 'Heater (ON/OFF)'])

    def append(self, file_key, controlled_temp, time, measured_temp, heater):
        if file_key not in CSV_FILE:
            print(f"Error: File key '{file_key}' does not exist in CSV_FILE.")
            return

        file_name = CSV_FILE[file_key]
        with open(file_name, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([controlled_temp, time, measured_temp, heater])

# Heater logic
def heaterControl(currTemp, setTemp):
    heaterStatus = currTemp <= setTemp

    if abs(currTemp - setTemp) <= 0.1:
        print('Temperature Achieved')
        heaterStatus = False

    return {
        "currentTemp": currTemp,
        "controlledTemp": setTemp,
        "heaterStatus": heaterStatus
    }

# SPI Initialization
def init_spi(bus, device):
    spi = spidev.SpiDev()
    spi.open(bus, device)
    spi.max_speed_hz = 900000
    spi.mode = 0
    return spi

# Read from MCP3202 channel 1
def read_channel_1(spi):
    start_byte = 0b00000001
    command_byte = 0b11100000
    dummy_byte = 0x00
    response = spi.xfer2([start_byte, command_byte, dummy_byte, dummy_byte])
    adc = ((response[1] & 0x0F) << 8) + response[2]
    return adc

# ADC to Voltage
def calcVoltage(INPUT_VOLTAGE, adc_value):
    voltage = (adc_value / ADC_RES) * INPUT_VOLTAGE
    return round(voltage, 2)

# Write to DAC (MCP4921)
def write_dac(value, spi):
    assert 0 <= value < 4096, "Value must be 0-4095 (12-bit)"
    command = (0b0011 << 12) | value
    response = spi.xfer2([command >> 8, command & 0xFF])
    print("Command (DAC):", bin(command))

# Voltage to Temperature Conversion
def voltageToTemperature(voltage):
    temp = (81 / 3.1) * voltage
    return round(temp, 2)

# Relay Control Logic
def relayControl(heaterStatus):
    if heaterStatus:
        GPIO.output(PIN['RELAY'], GPIO.LOW)  # Turn relay ON
    else:
        GPIO.output(PIN['RELAY'], GPIO.HIGH)  # Turn relay OFF

# Main logic
if __name__ == '__main__':
    csv1 = CSVObj()
    spi1 = init_spi(0, 0)  # MCP3202
    spi2 = init_spi(0, 1)  # MCP4921 (DAC)
    startTime = time()
    controlledTemp = 50
    GPIO_Setup('RELAY', 'OUTPUT')

    count = 0

    try:
        while True:
            currTime = time()
            diff = currTime - startTime
            print("Diff:", diff)

            if diff >= 5:  # Run logic every 5 seconds
                adc_value = read_channel_1(spi1)
                voltage = calcVoltage(INPUT_VOLTAGE, adc_value)
                print(f"ADC Value (Channel 1): {adc_value}")
                print(f"ADC Value (Bin): {bin(adc_value)}")
                print(f"Voltage: {voltage} V")

                write_dac(adc_value, spi2)
                measureTemp = voltageToTemperature(voltage)
                print("Temp:", measureTemp)

                startTime = currTime
                count += 1

                data = heaterControl(measureTemp, controlledTemp)
                relayControl(data['heaterStatus'])
                print("Data:", data)

                csv1.append('TEMP_DATA', data['controlledTemp'], count, data['currentTemp'], data['heaterStatus'])

                if count == 35:
                    print("35 minutes have passed. Exiting program...")
                    break

            print("Count:", count)
            sleep(1)

    finally:
        spi1.close()
        spi2.close()
        GPIO.cleanup()
