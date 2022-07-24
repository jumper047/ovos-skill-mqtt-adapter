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


class Topics(Topic):

    def __init__(self, id):
        root_topic = "mycroft/{}".format(id)
        super().__init__(root_topic)
        self.mic_mute = MicMuteTopics(root_topic)


class MqttAdapterSkill(MycroftSkill):

    def __init__(self):
        super().__init__("MqttAdapterSkill")
        self.mqtt = mqtt.Client(APP_NAME)
        

    def initialize(self):
        self.advertise_topic = self.settings.get('advertise_topic', 'homeassistant')
        self.topics = Topics('mycroft')
        self.handlers = dict()

        # Mic mute button
        self.bus.on('mycroft.mic.get_status.response', self.handle_mic_status)
        self.bus.emit(Message('mycroft.mic.get_status'))
        self.handlers[self.topics.mic_mute.set] = self.process_mic_mute_command

        self.setup_mqtt()
        self.advertise_mic_mute()

    def setup_mqtt(self):
        username = self.settings.get('username')
        password = self.settings.get('password')
        if not username:
            return None
        if password:
            self.mqtt.username_pw_set(username, password=password)
        else:
            self.mqtt.username_pw_set(username)
        host = self.settings.get('host')
        port = self.settings.get('port', 1883)
        keepalive = self.settings.get('keepalive', 60)
        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message
        self.mqtt.connect(host, port, keepalive)
        self.mqtt.loop_start()
        self.log.info('MQTT initialized')

    def on_connect(self, client, userdata, flags, rc):
        # Mute switch
        client.subscribe(self.topics.mic_mute.set)
        self.log.info('Subscribed!')

    def on_message(self, client, userdata, msg):
        if msg.topic not in self.handlers:
            return None

        try:
            self.handlers[msg.topic](bytes.decode(msg.payload))
        except Exception as e:
            raise MqttAdapterSkillError from e

    def shutdown(self):
        self.mqtt.loop_stop()


    def mycroft_id(self):
        """Get uuid for current hardware.

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
                    self.mycroft_id(),
                ]
            }
    

    # Mic mute switch

    def handle_mic_status(self, event):
        muted = event.data['muted']
        self.mqtt.publish(self.topics.mic_mute.state, payload=('ON' if muted else 'OFF'), retain=True)

    def process_mic_mute_command(self, state):
        if state == 'ON':
            self.log.info('Switch MUTE toggled on via MQTT')
            self.bus.emit(Message('mycroft.mic.mute'))
        elif state == 'OFF':
            self.log.info('Switch MUTE toggled off via MQTT')
            self.bus.emit(Message('mycroft.mic.unmute'))
        else:
            raise MqttAdapterSkillError("Payload {} is unknown".format(state))
        self.bus.emit(Message('mycroft.mic.get_status'))

    def advertise_mic_mute(self):
        id = self.mycroft_id() + "mic_mute"
        config = {
            "command_topic": self.topics.mic_mute.set,
            "state_topic": self.topics.mic_mute.state,
            "name": "Mycroft Muted",
            "uniq_id": id, 
            "pl_on": "ON",
            "pl_off": "OFF",
            "icon": "mdi:microphone-off",
            "device": self.mqtt_device_config()
        }
        advertise_topic = "{}/switch/{}/config".format(self.advertise_topic, id)
        self.mqtt.publish(advertise_topic, payload=json.dumps(config), retain=True)
        self.log.info('Mic mute advertised')
    
            
def create_skill():
    return MqttAdapterSkill()

