import serial.tools.list_ports
import dearpygui.dearpygui as dpg
import serial
import json
import base64

config = {

    'port': None,
    'baud': None,
    'pin': None,
    'gui': 1,
    'tokens_count': 0,
    'tokens': []
}

def alert(message, button=True):
    global config
    dpg.delete_item("info-st-gui")
    pos = [7.5, 7.5] if config["gui"] == 1 else [7.5, 50] if config["gui"] == 2 else [25.5, 50]
    with dpg.window(label="notification", width=183, height=30, tag="info-st-gui", pos=pos, no_title_bar=False, no_close=True):
        dpg.add_text(f"{message}", tag="alert-txt")
        if button:
            dpg.add_button(label="Ok", pos=[70, 69], width=45, callback=lambda: dpg.delete_item('info-st-gui'))

def serial_talkie(port, baud, message, bytes):
    with serial.Serial(port, baud, timeout=5) as sir:
        sir.write(f"{message}".encode())
        response = sir.read(bytes)
        return response

def list_com_ports():
    return [port.device for port in serial.tools.list_ports.comports()]

def is_esp8266(port):
    try:
        with serial.Serial(port, baudrate=115200, timeout=1) as ser:
            ser.write(b'{"action": "call"}\r\n')
            response = ser.read(100)
            if b'OK' in response:
                return True
    except:
        pass
    return False


def cb_delete_window(tag):
    try:
        dpg.delete_item(tag)
        select_esp_gui()
    except Exception:
        pass

def cb_token_delete(id):
    global config
    dpg.delete_item(f"token-token-{id}")
    config['tokens_count'] -= 1

def cb_detectesp():
    ports = list_com_ports()
    for port in ports:
        label = port if is_esp8266(port) else port
        dpg.set_value("select-esp-port", port)
        return
    dpg.set_value("select-esp-port", "")

def cb_next():
    global config
    port, baud = dpg.get_value("select-esp-port"), dpg.get_value("select-esp-baud")
    if not baud or not port:
        alert("Port or baud empty")
        return
    config["baud"] = int(baud)
    config["port"] = port
    config["gui"] = 2
    dpg.delete_item("select-esp")
    enter_pin_gui()

def cb_enter():
    global config
    pin = dpg.get_value("enter-pin-passcode")
    data = json.dumps({
        'action': 'auth',
        'pin': pin
    })
    alert("Authing...", False)
    response = serial_talkie(config['port'], config['baud'], data, 100)
    if response and b'OK' in response:
        config["gui"] = 3
        config["pin"] = pin
        dpg.delete_item("enter-pin")
        main_gui()
        alert("Authentication \nsuccessful")
    else:
        alert("Authentication failed")

def cb_changepin():
    global config
    oldpin, newpin = dpg.get_value("manage-oldpin"), dpg.get_value("manage-newpin")
    if not oldpin or not newpin:
        alert("Old or new pin-code is\n empty")
        return
    data = json.dumps({
        'action': 'change_pin',
        'old_pin': oldpin,
        'new_pin': newpin
    })
    alert("Changing PIN-Code..", False)
    response = serial_talkie(config['port'], config['baud'], data, 100)
    if response and b'OK' in response:
        alert("PIN changed \nsuccessfully")
        config['pin'] = newpin
    else:
        alert("Incorrect old PIN")

def cb_wifisettings():
    global config
    wifi, passwd = dpg.get_value("manage-wifi"), dpg.get_value("manage-wifipwd")
    if not wifi or not passwd:
        alert("WiFi SSID or WiFi\n Password is empty")
        return
    data = json.dumps({
        'action': 'change_wifi',
        'pin': config['pin'],
        'wifi': wifi,
        'password': passwd
    })
    alert("Updating WiFi settings..", False)
    response = serial_talkie(config['port'], config['baud'], data, 100)
    if response and b'OK' in response:
        alert("WiFi settings updated\n successfully")
    else:
        alert("Failed to update WiFi\n settings")

def cb_savedata():
    global config
    tokens = []

    for i in range(1, config['tokens_count'] + 1):
        name = dpg.get_value(f"token-name-{i}")
        secret = dpg.get_value(f"token-secret-{i}")
        if name and secret:
            secret_bytes = base64.b32decode(secret, casefold=True)
            tokens.append({
                "name": name,
                "secret": list(secret_bytes)
            })

    data = json.dumps({
        'action': 'save_tokens',
        'pin': config['pin'],
        'tokens': tokens
    })
    alert("Saving data...", False)
    response = serial_talkie(config['port'], config['baud'], data, 100)
    if response and b'OK' in response:
        alert("Tokens saved\n successfully")
    else:
        alert("Failed to save tokens")

def cb_refreshdata():
    global config
    data = json.dumps({
        'action': 'get_data',
        'pin': config['pin']
    })
    for i in range(1, config['tokens_count'] + 1):
        cb_token_delete(i)
    config['tokens_count'] = 0
    alert("Refreshing data..", False)
    response = serial_talkie(config['port'], config['baud'], data, 1024)
    if response:
        try:
            response_data = json.loads(response.decode())
            if 'tokens' in response_data:
                config['tokens_count'] = len(response_data['tokens'])
                for idx, token in enumerate(response_data['tokens']):
                    name = token['name']
                    secret = base64.b32encode(bytes(token['secret'])).decode('utf-8')
                    cb_addtoken(name=name, secret=secret)
                    alert("Done!")
        except json.JSONDecodeError:
            alert(f"Failed to parse data\n from ESP8266")
    else:
        alert("Failed to get data from\n ESP8266")
    

def cb_addtoken(name="", secret=""):
    global config
    id = config["tokens_count"] + 1
    dpg.delete_item("manage-addtoken-button")
    with dpg.child_window(height=30, no_scrollbar=True, parent="manage-board", no_scroll_with_mouse=True, tag=f"token-token-{id}"):
        dpg.add_input_text(hint="Name", pos=[10, 5.625], width=100, tag=f"token-name-{id}", default_value=name)
        dpg.add_input_text(hint="Secret", pos=[115, 5.625], width=145, tag=f"token-secret-{id}", default_value=secret)
        dpg.add_button(label="Delete Token", pos=[265, 5.625], width=112.5, callback=lambda: cb_token_delete(id))
    dpg.add_button(label="Add new token", callback=lambda: cb_addtoken(), tag="manage-addtoken-button", parent="manage-board")
    config["tokens_count"] = config["tokens_count"] + 1

def select_esp_gui():
    dpg.set_viewport_height(159)
    dpg.set_viewport_width(216)
    with dpg.window(label="Select COM Port",min_size=[200, 120], max_size=[200, 120], tag="select-esp", no_move=True, no_close=True):
        dpg.add_text("Select a COM Port", pos=[35, 20])
        dpg.add_input_text(label="Port", hint="COM0", pos=[15, 40], tag="select-esp-port")
        dpg.add_input_text(label="Baud", hint="115200", pos=[15, 60], tag="select-esp-baud", default_value=115200)
        dpg.add_button(label="Detect esp8266", callback=cb_detectesp, pos=[15, 80])
        dpg.add_button(label="Next", pos=[120, 80], callback=cb_next)

def enter_pin_gui():
    dpg.set_viewport_height(309)
    dpg.set_viewport_width(213)
    with dpg.window(label="Enter master PIN", min_size=[197, 270], max_size=[197, 270], tag="enter-pin", no_move=True, on_close=lambda: cb_delete_window("enter-pin")):
        dpg.add_text("Enter PIN-Code:", pos=[47.5, 20])
        dpg.add_input_text(tag="enter-pin-passcode", pos=[35, 40])
        with dpg.child_window(no_scrollbar=True, pos=[8, 70]): # do not touch
            dpg.add_button(label="1", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}1"), width=40, height=40, pos=[25, 5])
            dpg.add_button(label="2", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}2"), width=40, height=40, pos=[70, 5])
            dpg.add_button(label="3", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}3"), width=40, height=40, pos=[115, 5])
            dpg.add_button(label="4", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}4"), width=40, height=40, pos=[25, 50])
            dpg.add_button(label="5", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}5"), width=40, height=40, pos=[70, 50])
            dpg.add_button(label="6", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}6"), width=40, height=40, pos=[115, 50])
            dpg.add_button(label="7", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}7"), width=40, height=40, pos=[25, 95])
            dpg.add_button(label="8", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}8"), width=40, height=40, pos=[70, 95])
            dpg.add_button(label="9", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}9"), width=40, height=40, pos=[115, 95])
            dpg.add_button(label="enter", width=40, height=40, pos=[25, 140], callback=cb_enter)
            dpg.add_button(label="0", callback=lambda: dpg.set_value("enter-pin-passcode", f"{dpg.get_value("enter-pin-passcode")}0"), width=40, height=40, pos=[70, 140])
            dpg.add_button(label="<-", callback=lambda: dpg.set_value("enter-pin-passcode", ""), width=40, height=40, pos=[115, 140])

def main_gui():
    dpg.set_viewport_height(289)
    dpg.set_viewport_width(416)
    with dpg.window(label="Manage board", min_size=[400, 250], max_size=[400, 1000], tag="manage-board", no_scrollbar=True, no_move=True, on_close=lambda: cb_delete_window("manage-board")):
        with dpg.menu_bar():
            with dpg.menu(label="PIN-Code"):
                dpg.add_input_text(hint="Old PIN", width=100, tag="manage-oldpin")
                dpg.add_input_text(hint="New PIN", width=100, tag="manage-newpin")
                dpg.add_button(label="Change PIN", width=100, callback=cb_changepin)
            with dpg.menu(label="WiFi Settings"):
                dpg.add_input_text(hint="WiFi SSID", width=120, tag="manage-wifi")
                dpg.add_input_text(hint="WiFi Password", width=120, tag="manage-wifipwd")
                dpg.add_button(label="Save wifi", width=120, callback=cb_wifisettings)
            dpg.add_button(label="Save data", callback=cb_savedata)
            dpg.add_button(label="Reflesh data", callback=cb_refreshdata)
        dpg.add_button(label="Add new token", callback=lambda: cb_addtoken(), tag="manage-addtoken-button") # in callback lambda required, or the first fields will be manage-.... and None
        
def main():
    dpg.create_context()
    dpg.create_viewport(title='ESP8266 OTP Token Manager', width=400, height=320, min_height=1, min_width=1, max_width=416)
    select_esp_gui()
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()