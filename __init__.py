from mycroft.messagebus.message import Message
from mycroft.skills.core import MycroftSkill
from mycroft.version import CORE_VERSION_STR
import paho.mqtt.client as mqtt
import json
import uuid


APP_NAME = "mycroft_mqtt_adapter"


class MqttAdapterSkillError(Exception):
    """General MqttAdapterSkill exception"""


class Topic:

    def __init__(self, root_topic):
        self.root = root_topic

    def full_topic(self, *args):
        topic_elts = [self.root, *args]
        return "/".join(topic_elts)


class MicMuteTopics(Topic):

    def __init__(self, root_topic):
        super().__init__(root_topic)
        self.set = self.full_topic('mic_mute', 'set')
        self.state = self.full_topic('mic_mute', 'state')


class VolMuteTopics(Topic):

    def __init__(self, root_topic):
        super().__init__(root_topic)
        self.set = self.full_topic('vol_mute', 'set')
        self.state = self.full_topic('vol_mute', 'state')


class SpeakingTopics(Topic):

    def __init__(self, root_topic):
        super().__init__(root_topic)
        self.state = self.full_topic('speaking', 'state')


class ListeningTopics(Topic):

    def __init__(self, root_topic):
        super().__init__(root_topic)
        self.state = self.full_topic('listening', 'state')


class Topics(Topic):

    def __init__(self, device_name=None):
        root_topic = "mycroft"
        if device_name:
            root_topic += "/{}".format(device_name)
        super().__init__(root_topic)
        self.available = self.full_topic('available')
        self.listen_button = self.full_topic('listen_button')
        self.mic_mute = MicMuteTopics(root_topic)
        self.vol_mute = VolMuteTopics(root_topic)
        self.speaking = SpeakingTopics(root_topic)
        self.listening = ListeningTopics(root_topic)


class MqttAdapterSkill(MycroftSkill):

    def __init__(self):
        super().__init__("MqttAdapterSkill")
        self.mqtt = mqtt.Client(APP_NAME)
        self.command_handlers = dict()
        self.advertise_functions = list()

    def initialize(self):
        self.topics = Topics(self.settings.get("subtopic"))

        # Init sensors
        self.init_mic_mute()
        self.init_vol_mute()
        self.init_listening_sensor()
        self.init_speaking_sensor()
        self.init_listen_button()

        self.setup_mqtt()

    def on_settings_changed(self):
        self.teardown_mqtt()
        self.setup_mqtt()

    def setup_mqtt(self):
        username = self.settings.get('username')
        password = self.settings.get('password')
        if password:
            self.mqtt.username_pw_set(username, password=password)
        else:
            self.mqtt.username_pw_set(username)
        host = self.settings.get('host')
        port = self.settings.get('port')
        # This setting not exposed to GUI
        keepalive = self.settings.get('keepalive', 60)

        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message

        # Set up availability topic
        self.mqtt.will_set(self.topics.available, payload="OFFLINE", retain=True)

        try:
            self.mqtt.connect(host, port, keepalive)
        except Exception as e:
            self.log.exception(e)
            return None
        self.mqtt.loop_start()
        self.log.info('MQTT initialized')

    def teardown_mqtt(self):
        self.mqtt.publish(self.topics.available, payload="OFFLINE", retain=True)
        self.mqtt.disconnect()
        self.mqtt.loop_stop()

    def on_connect(self, client, userdata, flags, rc):
        if self.settings.get('advertise_sensors', True):
            discovery_prefix = self.settings.get('discovery_prefix')
            for func in self.advertise_functions:
                func(discovery_prefix)

        self.mqtt.publish(self.topics.available, payload="ONLINE", retain=True)

        for topic in self.command_handlers:
            client.subscribe(topic)

        self.log.info('Connected to MQTT server')

    def on_disconnect(self, client, userdata, flags, rc):
        self.log.info('Disconnected from MQTT server')

    def on_message(self, client, userdata, msg):
        if msg.topic not in self.command_handlers:
            return None

        try:
            self.command_handlers[msg.topic](bytes.decode(msg.payload))
        except Exception as e:
            raise MqttAdapterSkillError from e

    def shutdown(self):
        self.teardown_mqtt()
 
    def register_mqtt_handler(self, topic, handler):
        self.command_handlers[topic] = handler

    def register_advertise_function(self, func):
        self.advertise_functions.append(func)

    def mqtt_discovery_unique_id(self):
        """Get unique_id for current hardware.

        In case this Mycroft instance was moved from one HW to another 
        this ID can be setted via settings to certain value."""
        id = self.settings.get('uuid')
        if not id:
            id = str(uuid.getnode())
            self.settings['uuid'] = id
        return id

    def mqtt_device_config(self):
        return {
            "name": "Mycroft",
            "manufacturer": "Mycroft AI, Inc",
            "sw_version": CORE_VERSION_STR,
            "identifiers": [
                    self.mqtt_discovery_unique_id(),
                ]
            }

    def mqtt_availability_config(self):
        return {
            "availability_topic": self.topics.available,
            "pl_avail": "ONLINE",
            "pl_not_avail": "OFFLINE",
        }

    def set_sensor_state(self, topic, payload):
        self.mqtt.publish(topic, payload=payload, retain=True)

    # Mic mute switch
    def init_mic_mute(self):
        self.bus.on('mycroft.mic.get_status.response', self.handle_mic_status)
        self.bus.emit(Message('mycroft.mic.get_status'))
        self.register_mqtt_handler(self.topics.mic_mute.set, self.process_mic_mute_command)
        self.register_advertise_function(self.advertise_mic_mute)

    def handle_mic_status(self, event):
        payload = 'ON' if event.data['muted'] else 'OFF'
        self.set_sensor_state(self.topics.mic_mute.state, payload)

    def process_mic_mute_command(self, state):
        if state == 'ON':
            self.log.info('Switch MIC MUTE toggled on via MQTT')
            self.bus.emit(Message('mycroft.mic.mute'))
        elif state == 'OFF':
            self.log.info('Switch MIC MUTE toggled off via MQTT')
            self.bus.emit(Message('mycroft.mic.unmute'))
        else:
            raise MqttAdapterSkillError("Payload {} is unknown".format(state))
        self.bus.emit(Message('mycroft.mic.get_status'))

    def advertise_mic_mute(self, discovery_prefix):
        id = self.mqtt_discovery_unique_id() + "mic_mute"
        config = {
            "command_topic": self.topics.mic_mute.set,
            "state_topic": self.topics.mic_mute.state,
            "name": "Mycroft Mic Muted",
            "uniq_id": id, 
            "pl_on": "ON",
            "pl_off": "OFF",
            "icon": "mdi:microphone-off",
            "device": self.mqtt_device_config()
        }
        config.update(self.mqtt_availability_config())
        discovery_topic = "{}/switch/{}/config".format(discovery_prefix, id)
        self.mqtt.publish(discovery_topic, payload=json.dumps(config), retain=True)
        self.log.info('Mic mute advertised')


    # Volume mute switch
    def init_vol_mute(self):
        # For now I don't want to interact with mixer inside this plugin
        # but to rely on ohter Mycroft skills instead. So I'll assume
        # on the moment of the plugin's init volume is unmuted
        self.bus.on('mycroft.volume.duck', lambda _: self.set_vol_mute_state('ON'))
        self.bus.on('mycroft.volume.unduck', lambda _: self.set_vol_mute_state('OFF'))
        self.register_mqtt_handler(self.topics.vol_mute.set, self.process_vol_mute_command)
        self.register_advertise_function(self.advertise_vol_mute)
        # Set initial state
        self.set_vol_mute_state('OFF')


    def set_vol_mute_state(self, state):
        self.set_sensor_state(self.topics.vol_mute.state, state)


    def process_vol_mute_command(self, state):
        if state == 'ON':
            self.log.info('Switch VOL MUTE toggled on via MQTT')
            self.bus.emit(Message('mycroft.volume.mute'))
        elif state == 'OFF':
            self.log.info('Switch VOL MUTE toggled off via MQTT')
            self.bus.emit(Message('mycroft.volume.unmute'))
        else:
            raise MqttAdapterSkillError("Payload {} is unknown".format(state))

    def advertise_vol_mute(self, discovery_prefix):
        id = self.mqtt_discovery_unique_id() + "vol_mute"
        config = {
            "command_topic": self.topics.vol_mute.set,
            "state_topic": self.topics.vol_mute.state,
            "name": "Mycroft Speaker Muted",
            "uniq_id": id,
            "pl_on": "ON",
            "pl_off": "OFF",
            "icon": "mdi:volume-off",
            "device": self.mqtt_device_config()
        }
        config.update(self.mqtt_availability_config())
        discovery_topic = "{}/switch/{}/config".format(discovery_prefix, id)
        self.mqtt.publish(discovery_topic, payload=json.dumps(config), retain=True)
        self.log.info('Volume mute advertised')

    # Speaking binary sensors
    def init_speaking_sensor(self):
        self.bus.on(
            'recognizer_loop:audio_output_start',
            lambda _: self.set_speaking('ON')
        )
        self.bus.on(
            'recognizer_loop:audio_output_end',
            lambda _: self.set_speaking('OFF')
        )
        self.register_advertise_function(self.advertise_speaking)
        self.set_speaking('OFF')

    def set_speaking(self, state):
        self.set_sensor_state(self.topics.speaking.state, state)

    def advertise_speaking(self, discovery_prefix):
        id = self.mqtt_discovery_unique_id() + "speaking"
        config = {
            "state_topic": self.topics.speaking.state,
            "name": "Mycroft Is Speaking",
            "uniq_id": id,
            "pl_on": "ON",
            "pl_off": "OFF",
            "icon": "mdi:account-voice",
            "device": self.mqtt_device_config()
        }
        config.update(self.mqtt_availability_config())
        discovery_topic = "{}/binary_sensor/{}/config".format(discovery_prefix, id)
        self.mqtt.publish(discovery_topic, payload=json.dumps(config), retain=True)
        self.log.info('Speaking sensor advertised')

    # Listening binary sensor
    def init_listening_sensor(self):
        self.bus.on(
            'recognizer_loop:record_begin',
            lambda _: self.set_listening('ON')
        )
        self.bus.on(
            'recognizer_loop:record_end',
            lambda _: self.set_listening('OFF')
        )        
        self.register_advertise_function(self.advertise_listening)
        self.set_listening('OFF')

    def set_listening(self, state):
        self.set_sensor_state(self.topics.listening.state, state)

    def advertise_listening(self, discovery_prefix):
        id = self.mqtt_discovery_unique_id() + "listening"
        config = {
            "state_topic": self.topics.listening.state,
            "name": "Mycroft Is Listening",
            "uniq_id": id,
            "pl_on": "ON",
            "pl_off": "OFF",
            "icon": "mdi:ear-hearing",
            "device": self.mqtt_device_config()
        }
        config.update(self.mqtt_availability_config())
        discovery_topic = "{}/binary_sensor/{}/config".format(discovery_prefix, id)
        self.mqtt.publish(discovery_topic, payload=json.dumps(config), retain=True)
        self.log.info('Listening sensor advertised')

    # Listen button
    def init_listen_button(self):
        self.register_mqtt_handler(self.topics.listen_button, self.process_listen_button)
        self.register_advertise_function(self.advertise_listen_button)

    def process_listen_button(self, state):
        if state == 'PRESS':
            self.log.info('Command listening triggered by MQTT')
            self.bus.emit(Message('mycroft.mic.listen'))
        else:
            raise MqttAdapterSkillError("Payload {} is unknown".format(state))

    def advertise_listen_button(self, discovery_prefix):
        id = self.mqtt_discovery_unique_id() + "listen_button"
        config = {
            "command_topic": self.topics.listen_button,
            "name": "Mycroft Listen Command",
            "uniq_id": id, 
            # "payload_press": "PRESS",
            # "icon": "mdi:microphone-off",
            "device": self.mqtt_device_config()
        }
        # config.update(self.mqtt_availability_config())
        discovery_topic = "{}/button/{}/config".format(discovery_prefix, id)
        self.mqtt.publish(discovery_topic, payload=json.dumps(config), retain=True)
        self.log.info('Listen button advertised')


            # self.bus.emit(Message('mycroft.mic.listen'))


def create_skill():
    return MqttAdapterSkill()

