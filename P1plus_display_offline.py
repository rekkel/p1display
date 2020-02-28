from datetime import datetime, timezone, timedelta
from functools import partial
from guizero import App, Text, TextBox, PushButton, Box, CheckBox
import board
import neopixel
import crcmod.predefined
import re
import serial
import threading
import time
import traceback
crc16 = crcmod.predefined.mkPredefinedCrcFun('crc16')
pixels = neopixel.NeoPixel(board.D18, 32)
checksum = ''

FONT = 'Quicksand'

def parse_dsmr_timestamp(timestamp):
    timestamp = str(timestamp)
    year, month, day, hour, minute, second = [int(timestamp[i:i+2]) for i in range(0, 12, 2)]
    year = 2000 + year
    if timestamp[-1] == "W":
        offset = 1
    else:
        offset = 2
    dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone(timedelta(hours=offset))).astimezone(timezone.utc)
    return dt


def parse_dsmr_text_message(textmessage):
    return bytes.fromhex(textmessage).decode('ascii')

def scale(value, multiplier):
    return int(float(value) * multiplier)

class DisplayApp(App):
    obis_mapping = {"1-3:0.2.8": {"name": "dsmr_version", "type": int},
                    "0-0:1.0.0": {"name": "timestamp", "type": parse_dsmr_timestamp},
                    "0-0:96.1.1": {"name": "identifier", "type": str},
                    "1-0:1.8.1": {"name": "energy_import_t1", "type": partial(scale, multiplier=1000)},
                    "1-0:1.8.2": {"name": "energy_import_t2", "type": partial(scale, multiplier=1000)},
                    "1-0:2.8.1": {"name": "energy_export_t1", "type": partial(scale, multiplier=1000)},
                    "1-0:2.8.2": {"name": "energy_export_t2", "type": partial(scale, multiplier=1000)},
                    "0-0:96.14.0": {"name": "tariff_indicator", "type": int},
                    "1-0:1.7.0": {"name": "power_import", "type": partial(scale, multiplier=1000)},
                    "1-0:2.7.0": {"name": "power_export", "type": partial(scale, multiplier=1000)},
                    "0-0:96.7.21": {"name": "num_power_failures", "type": int},
                    "0-0:96.7.9": {"name": "num_long_power_failures", "type": int},
                    "1-0:32.32.0": {"name": "num_voltage_sags_l1", "type": int},
                    "1-0:52.32.0": {"name": "num_voltage_sags_l2", "type": int},
                    "1-0:72.32.0": {"name": "num_voltage_sags_l3", "type": int},
                    "1-0:32.36.0": {"name": "num_voltage_swells_l1", "type": int},
                    "1-0:52.36.0": {"name": "num_voltage_swells_l2", "type": int},
                    "1-0:72.36.0": {"name": "num_voltage_swells_l3", "type": int},
                    "0-0:96.13.0": {"name": "text_message", "type": parse_dsmr_text_message},
                    "1-0:32.7.0": {"name": "voltage_l1", "type": partial(scale, multiplier=10)},
                    "1-0:52.7.0": {"name": "voltage_l2", "type": partial(scale, multiplier=10)},
                    "1-0:72.7.0": {"name": "voltage_l3", "type": partial(scale, multiplier=10)},
                    "1-0:31.7.0": {"name": "current_l1", "type": int},
                    "1-0:51.7.0": {"name": "current_l2", "type": int},
                    "1-0:71.7.0": {"name": "current_l3", "type": int},
                    "1-0:21.7.0": {"name": "power_import_l1", "type": partial(scale, multiplier=1000)},
                    "1-0:41.7.0": {"name": "power_import_l2", "type": partial(scale, multiplier=1000)},
                    "1-0:61.7.0": {"name": "power_import_l3", "type": partial(scale, multiplier=1000)},
                    "1-0:22.7.0": {"name": "power_export_l1", "type": partial(scale, multiplier=1000)},
                    "1-0:42.7.0": {"name": "power_export_l2", "type": partial(scale, multiplier=1000)},
                    "1-0:62.7.0": {"name": "power_export_l3", "type": partial(scale, multiplier=1000)}}

    def __init__(self):
        super().__init__(title='SMR5 P1 display', bg = 'white')
        self.tk.attributes("-fullscreen",True)
        self._stop = None
        self._read_p1_plus_message_thread = None
        
        header = add_text(self, 'ElaadNL Social Module', 'top', 20)
        self.app_message = add_text(self, 'Start reading P1+ messages\n', align = 'top')
        
        start_stop_box = Box(self, width = 'fill', align = 'bottom')
        space = add_text(start_stop_box, '', 'top')
        readButton = add_pushbutton(start_stop_box, self.read_p1_plus_message, "Read social module now",
                                    'right', '#33cc33')
        stopButton = add_pushbutton(start_stop_box, self.stop, 'Stop', 'right')
        self.demoButton = add_checkbox(start_stop_box, text="Congestion Demo")
        exitButton = add_pushbutton(start_stop_box, exit, 'Exit')
      
        ean_box = EmulatorBox(self, 'EAN', align = 'top')
        self.ean = ean_box.add_controls('EAN        ', '', 0, 0, 20,)
        message_box = EmulatorBox(self, 'Message', align = 'top')
        self.message = message_box.add_controls('Message', '', 0, 0, 60, 3)

        measure_box = EmulatorBox(self, 'Current flow', 'left')
        self.input_l1_i = measure_box.add_controls('L1', '', 1, 1)
        self.input_l2_i = measure_box.add_controls('L2', '', 1, 2)
        self.input_l3_i = measure_box.add_controls('L3', '', 1, 3)
        
        congestion_box = EmulatorBox(self, 'Current Limit', 'right')
        self.input_l1_u_min = congestion_box.add_controls('L1+', '', 1, 1, 5)
        self.input_l2_u_min = congestion_box.add_controls('L2+', '', 1, 2, 5)
        self.input_l3_u_min = congestion_box.add_controls('L3+', '', 1, 3, 5)
        self.input_l1_e_min = congestion_box.add_controls('   L1-', '', 3, 1, 5)
        self.input_l2_e_min = congestion_box.add_controls('   L2-', '', 3, 2, 5)
        self.input_l3_e_min = congestion_box.add_controls('   L3-', '', 3, 3, 5)
        
        self.display()
        
    def read_p1_plus_message(self):
        if not self._read_p1_plus_message_thread:
            self._stop = threading.Event()
            
            def run():
                try:
                    with serial.Serial("/dev/ttyUSB0", baudrate=115200) as s:
                        telegram = bytes()
                        data = {}
                        while 1:
                            if self._stop.isSet():
                                break
                            line = s.readline()
                            if line.startswith(b'/'):
                                telegram = line
                                line = line.decode('ascii').strip()
                                print(line)
                                break
                        received_message = '' 
                        while 1:
                            if self._stop.isSet():
                                break
                            self.app_message.text_color = 'grey'
                            self.app_message.value = received_message + '\nReading P1... '
                            line = s.readline()
                            telegram += line
                            line = line.decode('ascii').strip()
                            if line.startswith("!"):
                                received_message = 'P1 Message received at: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                self.app_message.text_color = 'blue'
                                self.app_message.value = received_message + '\n'
                                if self.validate(telegram):
                                    print('P1 message with valid CRC')
                                    self.input_l1_i.value = data[self.obis_mapping["1-0:31.7.0"]["name"]]
                                    self.input_l2_i.value = data[self.obis_mapping["1-0:51.7.0"]["name"]]
                                    self.input_l3_i.value = data[self.obis_mapping["1-0:71.7.0"]["name"]]
                                    self.ean.value = bytearray.fromhex(data[self.obis_mapping["0-0:96.1.1"]["name"]]).decode()
                                    if self.demoButton.value:
                                        if self.message.value.strip() == "EAN0000000000000;;20;;;;":
                                            self.message.value = "EAN0000000000000;;;;;;"
                                        else:
                                            self.message.value = "EAN0000000000000;;20;;;;"
                                    elif not self.demoButton.value:
                                        self.message.value = data[self.obis_mapping["0-0:96.13.0"]["name"]]
                                    congestion_list = list(map(str.strip, self.message.value.split(";")))
                                    if len(congestion_list) == 7:
                                        self.input_l1_u_min.value = '' if congestion_list[1] == '' else congestion_list[1]
                                        self.input_l2_u_min.value = '' if congestion_list[2] == '' else congestion_list[2]
                                        self.input_l3_u_min.value = '' if congestion_list[3] == '' else congestion_list[3]
                                        self.input_l1_e_min.value = '' if congestion_list[4] == '' else congestion_list[4]
                                        self.input_l2_e_min.value = '' if congestion_list[5] == '' else congestion_list[5]
                                        self.input_l3_e_min.value = '' if congestion_list[6] == '' else congestion_list[6]
                                        if(congestion_list.count('') == 6):
                                            self.led_indicator(0, 0, 255)
                                        else:
                                            self.led_indicator(205, 0, 255)
                                    else:
                                        self.led_indicator(0, 0, 255)
                                        self.input_l1_u_min.value = ''
                                        self.input_l2_u_min.value = ''
                                        self.input_l3_u_min.value = ''
                                        self.input_l1_e_min.value = ''
                                        self.input_l2_e_min.value = ''
                                        self.input_l3_e_min.value = ''
                                data = {}
                                telegram = bytes()
                                continue
                            for key in self.obis_mapping:
                                if line.startswith(key):
                                    match = re.match(r'.*\(([a-fA-F0-9.]*)', line)
                                    if match:
                                        value = self.obis_mapping[key]["type"](match[1])
                                        data[self.obis_mapping[key]["name"]] = value
                                    break
                except:
                    print(traceback.format_exec())

            self._read_p1_plus_message_thread = threading.Thread(target=run)
            self._read_p1_plus_message_thread.start()    
        
        elif not self._read_p1_plus_message_thread.isAlive():
            self.stop()
            self.read_p1_plus_message()


    def stop(self):
        if self._read_p1_plus_message_thread: 
            self._stop.set()
            self.led_indicator(0, 0, 0)
            self._read_p1_plus_message_thread.join(1)
            self._read_p1_plus_message_thread = None

    def validate(self, telegram):
        global checksum
        pattern = re.compile(b'\r\n(?=!)')
        for match in pattern.finditer(telegram):
            packet = telegram[:match.end() + 1]
            checksum = telegram[match.end() + 1:]
        if checksum.strip():
            given_checksum = int('0x' + checksum.decode('ascii').strip(), 16)
            calculated_checksum = crc16(packet)
            if given_checksum != calculated_checksum:
                print('Checksum mismatch: given={}, calculated={}'.format(given_checksum, calculated_checksum))
                return False
        return True

    def led_indicator(self, r, g, b):
        for i in range(0, 16):
            pixels[i] = (r, g, b)
            pixels[16+i] = (r, g, b)
            time.sleep(0.05)

class EmulatorBox(Box):
    def __init__(self, parent, box_title, align):
        super().__init__(parent, width = 'fill', height = 'fill', layout='grid', align = align)
        self.bg = '#e6e6e6'

        self.header = add_text(self, box_title, grid = [0, 0])

    def add_controls(self, description, value, row, column, width = 10, height = 1, size = 14, font = FONT):
        Text(self, description, size = size, font = font, grid=[row, column]) 
        text_box = TextBox(self, width = width, height = height, multiline = True, text = value, grid = [row + 1, column])
        text_box.bg = 'white'
        text_box.font = font
        text_box.text_size = size
        return text_box
        
def add_checkbox(app, text, align = 'right', size = 14, font = FONT, grid = []):
    if grid:
        checkbox = CheckBox(app, text = text, align = align, grid = grid)
    else:
        checkbox = CheckBox(app, text = text, align = align)
    checkbox.font = font
    checkbox.text_size = size
    checkbox.bg = 'white'
    return checkbox

def add_text(app, text, align = 'left', size = 13, font = FONT, grid = [], color = 'black'):
    if grid:
        return Text(app, text, size = size, font = font, grid = grid, align = align, color = color)
    else:  # niet per se nodig, maar dan vermijd je de warnings
        return Text(app, text, size = size, font = font, align = align, color = color)
        
def add_pushbutton(app, command, text, align = 'left', bg = 'white', size = 15, font = FONT):
    pushbutton = PushButton(app, command = command, text = text, align = align)
    pushbutton.bg = bg
    pushbutton.font = font
    pushbutton.text_size = size
    return pushbutton


if __name__ == '__main__':
    app = DisplayApp()
    exit()
