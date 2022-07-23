from mycroft.messagebus.message import Message
from mycroft.skills.core import MycroftSkill
import paho.mqtt.client as mqtt


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

    def __init__(self, root_topic):
        super().__init__(root_topic)
        self.mic_mute = MicMuteTopics(root_topic)


class MqttAdapterSkill(MycroftSkill):

    def __init__(self):
        super().__init__("MqttAdapterSkill")
        self.mqtt = mqtt.Client(APP_NAME)
        

    def initialize(self):
        # self.topics = Topics('mycroft/{}'.format(self.settings.get('instance_name')))
        self.advertise_topic = 'homeassistant'
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
        config = {
            "name": "Mycroft Muted",
            "command_topic": self.topics.mic_mute.set,
            "state_topic": self.topics.mic_mute.state,
        }
        advertise_topic = "{}/switch/mycroft/mic_mute/config".format(self.advertise_topic)
        self.mqtt.publish(advertise_topic, payload=config, retain=True)
        
        
    
            
def create_skill():
    return MqttAdapterSkill()

