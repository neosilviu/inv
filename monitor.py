#! /usr/bin/python

# Axpert Inverter control script

# Read values from inverter, sends values to emonCMS,
# read electric low or high tarif from emonCMS and setting charger and mode to hold batteries fully charged
# controls grid charging current to meet circuit braker maximum alloweble grid current(power)
# calculation of CRC is done by XMODEM mode, but in firmware is wierd mistake in POP02 command, so exception of calculation is done in serial_command(command) function

import time, sys, string
import sqlite3
import json
import datetime
import calendar
import os
import fcntl
import re
import crcmod
from binascii import unhexlify
import paho.mqtt.client as mqtt
from random import randint

def connect():
    global client
    client = mqtt.Client(client_id=os.environ['MQTT_CLIENT_ID'])
    client.username_pw_set(os.environ['MQTT_USER'], os.environ['MQTT_PASS'])
    client.connect(os.environ['MQTT_SERVER'])
    try:
        global file
        global fd
        file = open('/dev/hidraw0', 'r+')
        fd = file.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    except Exception as e:
        print('error open file descriptor:' + str(e))
        exit()

def disconnect():
    file.close()

def serial_command(command):
    print(command)
    try:
        xmodem_crc_func = crcmod.predefined.mkCrcFun('xmodem')
        command_crc = command + unhexlify(hex(xmodem_crc_func(command)).replace('0x','',1)) + '\x0d'

        os.write(fd, command_crc)

        response = ''
        timeout_counter = 0
        while '\r' not in response:
            if timeout_counter > 500:
                raise Exception('Read operation timed out')
            timeout_counter += 1
            try:
                response += os.read(fd, 100)
            except Exception as e:
                # print("error reading response...: " + str(e))
                time.sleep(0.01)
            if len(response) > 0 and response[0] != '(' or 'NAKss' in response:
                raise Exception('NAKss')

        print(response)
        response = response.rstrip()
        lastI = response.find('\r')
        response = response[1:lastI-2]
        return response
    except Exception as e:
        print('error reading inverter...:' + str(e))
        disconnect()
        time.sleep(0.1)
        connect()
        return serial_command(command)

def get_parallel_data():
    #collect data from axpert inverter
    try:
        response = serial_command('QPIRI')
        nums = response.split(' ')
        if len(nums) < 17:
            return ''
        data = '{'

        data += '"OutputSourcePriority":' + str(int(nums[16]))
        data += ',"ChargerSourcePriority":' + str(int(nums[17]))   
  

        data += '}'
        return data
    except Exception as e:
        print('error parsing inverter data...:' + str(e))
        return ''

def get_mode_data():
    #collect data from axpert inverter
    try:
        response = serial_command('QMOD')
        nums = response.split(' ')
        if len(nums) < 1:
            return ''
        data = '{'
        if nums[0] == 'P':
            data += '"InverterMode":1'
        elif nums[0] == 'S':
            data += '"InverterMode":2'
        elif nums[0] == 'L':
            data += '"InverterMode":3'
        elif nums[0] == 'B':
            data += '"InverterMode":4'
        elif nums[0] == 'F':
            data += '"InverterMode":5'
        elif nums[0] == 'H':
            data += '"InverterMode":6'
        else:
            data += '"InverterMode":0'
 #       data += '"InverterMode":' + str(nums[0])

        data += '}'
        return data
    except Exception as e:
        print('error parsing inverter data...:' + str(e))
        return ''


def get_data():
    #collect data from axpert inverter
    try:
        response = serial_command('QPIGS')
        nums = response.split(' ')
        if len(nums) < 21:
            return ''

        data = '{'

        data += '"GridVoltage":' + str(float(nums[0]))
        data += ',"GridFrequency":' + str(float(nums[1]))
        data += ',"OutputVoltage":' + str(float(nums[2]))
        data += ',"OutputFrequency":' + str(float(nums[3]))
        data += ',"OutputAparentPower":' + str(int(nums[4]))
        data += ',"OutputActivePower":' + str(int(nums[5]))
        data += ',"LoadPercentage":' + str(int(nums[6]))
        data += ',"BusVoltage":' + str(float(nums[7]))
        data += ',"BatteryVoltage":' + str(float(nums[8]))
        data += ',"BatteryChargingCurrent":' + str(int(nums[9]))
        data += ',"BatteryCapacity":' + str(float(nums[10]))
        data += ',"InverterHeatsinkTemperature":' + str(float(nums[11]))
        data += ',"PvInputPower":' + str(int(nums[19]))   
        data += ',"PvInputCurrent":' + str(int(nums[12]))
        data += ',"PvInputVoltage":' + str(float(nums[13]))
        data += ',"BatteryVoltageFromScc":' + str(float(nums[14]))
        data += ',"BatteryDischargeCurrent":' + str(int(nums[15]))
        data += ',"DeviceStatus":"' + nums[16] + '"'
     
      
               
        data += '}'
        return data
    except Exception as e:
        print('error parsing inverter data...:' + str(e))
        return ''

def send_data(data, topic):
    try:
        client.publish(topic, data)
    except Exception as e:
        print("error sending to emoncms...: " + str(e))
        return 0
    return 1

def main():
    time.sleep(randint(0, 2)) # so parallel streams might start at different times
    connect();
    serial_number = serial_command('QID')
    print('Reading from inverter ' + serial_number)
    while True:
        data = get_parallel_data()
        # data = '{"TotalAcOutputActivePower": 1000}'
        if not data == '':
            send = send_data(data, os.environ['MQTT_QPIRI'])

        data = get_mode_data()
        if not data == '':
            send = send_data(data, os.environ['MQTT_MODE'])

        data = get_data()
        if not data == '':
            send = send_data(data, os.environ['MQTT_QPIGS'].replace('{sn}', serial_number))

        time.sleep(20)

if __name__ == '__main__':
    main()
