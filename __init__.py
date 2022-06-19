from mycroft.messagebus.message import Message
from mycroft.skills.core import MycroftSkill
import paho.mqtt.client as mqtt


TOPIC = "mycroft/cmd"
APP_NAME = "mycroft_mqtt_adapter"


class MqttAdapterSkill(MycroftSkill):

    def __init__(self):
        super().__init__("MqttAdapterSkill")
        self.mqtt = mqtt.Client(APP_NAME)
        

    def initialize(self):
        self.setup_mqtt()

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
        client.subscribe(TOPIC)
        self.log.info('Subscribed!')

    def on_message(self, client, userdata, msg):
        if msg.topic == TOPIC:
            payload = bytes.decode(msg.payload)
            if payload == 'WAKE':
                self.log.info('Received command "WAKE"')
                self.bus.emit(Message("mycroft.mic.listen"))
                if self.config_core.get("enclosure").get("platform", "unknown") != "unknown":
                    self.bus.emit(Message('mycroft.volume.unmute',
                                          data={"speak_message": False}))
            elif payload == 'SLEEP':
                self.log.info('Received command "SLEEP"')
                self.bus.emit(Message('recognizer_loop:sleep'))
                if self.config_core.get("enclosure").get("platform", "unknown") != "unknown":
                    self.bus.emit(Message('mycroft.volume.mute',
                                              data={"speak_message": False}))
            else:
                self.log.info('Received unknown payload: {}'.format(payload))    

    def shutdown(self):
        self.mqtt.loop_stop()
    
            
def create_skill():
    return MqttAdapterSkill()

