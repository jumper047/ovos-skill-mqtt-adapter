# Copyright 2022 jumper047.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import json
import uuid

import paho.mqtt.client as mqtt
from mycroft.messagebus.message import Message
from mycroft.skills.core import MycroftSkill
from mycroft.version import CORE_VERSION_STR


APP_NAME = "mycroft_mqtt_adapter"


# Topics
MIC_MUTE_STATE_TOPIC = '{main_topic}/mic_mute/state'
MIC_MUTE_SET_TOPIC = '{main_topic}/mic_mute/set'
VOL_MUTE_STATE_TOPIC = '{main_topic}/vol_mute/state'
VOL_MUTE_SET_TOPIC = '{main_topic}/vol_mute/set'
SPEAKING_STATE_TOPIC = '{main_topic}/speaking/state'
LISTENING_STATE_TOPIC = '{main_topic}/listening/state'
AVAILABILITY_TOPIC = '{main_topic}/available'
LISTEN_BUTTON_TOPIC = '{main_topic}/listen_button'
COMMAND_TOPIC = '{main_topic}/command'

# Payloads
ON = "ON"
OFF = "OFF"
ONLINE = "ONLINE"
OFFLINE = "OFFLINE"
PRESS = "PRESS"

# Discovery
SWITCH_DISCOVERY_TOPIC = "{discovery_topic}/switch/{id}/config"
BINARY_SENSOR_DISCOVERY_TOPIC = "{discovery_topic}/binary_sensor/{id}/config"
BUTTON_DISCOVERY_TOPIC = "{discovery_topic}/button/{id}/config"


class MqttAdapterSkill(MycroftSkill):

    def __init__(self):
        super().__init__("MqttAdapterSkill")
        self.mqtt = mqtt.Client(APP_NAME)
        self.command_handlers = dict()
        self.advertise_functions = list()

    def initialize(self):
        
        subtopic = self.settings.get("subtopic")
        self.main_topic = "mycroft/{}".format(subtopic) if subtopic else "mycroft"
        self.discovery_topic = self.settings.get('discovery_prefix')

        # Init sensors
        self.init_mic_mute()
        self.init_vol_mute()
        self.init_listening_sensor()
        self.init_speaking_sensor()
        self.init_listen_button()
        self.init_command()

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
        self.mqtt.enable_logger()

        # Set up availability topic
        self.mqtt.will_set(self.expand(AVAILABILITY_TOPIC), payload=OFFLINE, retain=True)

        try:
            self.mqtt.connect(host, port, keepalive)
        except Exception as e:
            self.log.exception(e)
            return None
        self.mqtt.loop_start()
        self.log.info('MQTT initialized')

    def teardown_mqtt(self):
        self.mqtt.publish(self.expand(AVAILABILITY_TOPIC), payload=OFFLINE, retain=True)
        self.mqtt.disconnect()
        self.mqtt.loop_stop()

    def on_connect(self, client, userdata, flags, rc):
        if self.settings.get('advertise_sensors', True):
            for func in self.advertise_functions:
                func()

        self.mqtt.publish(self.expand(AVAILABILITY_TOPIC), payload=ONLINE, retain=True)

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
            self.log.exception(e)

    def shutdown(self):
        self.teardown_mqtt()
 
    def register_mqtt_handler(self, topic_template, handler):
        self.command_handlers[self.expand(topic_template)] = handler

    def register_advertise_function(self, func):
        self.advertise_functions.append(func)

    def expand(self, template, **kwargs):
        return template.format(
            main_topic=self.main_topic,
            discovery_topic=self.discovery_topic,
            **kwargs
        )

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
            "model": self.config_core['enclosure'].get("platform", "unknown"), 
            "manufacturer": "Mycroft AI, Inc",
            "sw_version": CORE_VERSION_STR,
            "identifiers": [
                    self.mqtt_discovery_unique_id(),
                ]
            }

    def mqtt_availability_config(self):
        return {
            "availability_topic": self.expand(AVAILABILITY_TOPIC),
            "pl_avail": ONLINE,
            "pl_not_avail": OFFLINE,
        }

    def set_sensor_state(self, topic, payload):
        self.mqtt.publish(self.expand(topic), payload=payload, retain=True)


    # Mic mute switch
    def init_mic_mute(self):
        self.bus.on('mycroft.mic.get_status.response', self.handle_mic_status)
        self.bus.emit(Message('mycroft.mic.get_status'))
        self.register_mqtt_handler(MIC_MUTE_SET_TOPIC, self.process_mic_mute_command)
        self.register_advertise_function(self.advertise_mic_mute)

    def handle_mic_status(self, event):
        payload = ON if event.data['muted'] else OFF
        self.set_sensor_state(self.expand(MIC_MUTE_STATE_TOPIC), payload)

    def process_mic_mute_command(self, state):
        if state == ON:
            self.log.info('Switch MIC MUTE toggled on via MQTT')
            self.bus.emit(Message('mycroft.mic.mute'))
        elif state == OFF:
            self.log.info('Switch MIC MUTE toggled off via MQTT')
            self.bus.emit(Message('mycroft.mic.unmute'))
        else:
            self.log.warning("Payload {} is unknown".format(state))
        self.bus.emit(Message('mycroft.mic.get_status'))

    def advertise_mic_mute(self):
        id = self.mqtt_discovery_unique_id() + "mic_mute"
        config = {
            "command_topic": self.expand(MIC_MUTE_SET_TOPIC), 
            "state_topic": self.expand(MIC_MUTE_STATE_TOPIC),
            "name": "Mycroft Mic Muted",
            "uniq_id": id,
            "pl_on": ON, 
            "pl_off": OFF,
            "icon": "mdi:microphone-off",
            "device": self.mqtt_device_config(),
            **self.mqtt_availability_config()
        }
        self.mqtt.publish(
            self.expand(SWITCH_DISCOVERY_TOPIC, id=id),
            payload=json.dumps(config),
            retain=True
        )


    # Volume mute switch
    def init_vol_mute(self):
        # For now I don't want to interact with mixer inside this plugin
        # but to rely on ohter Mycroft skills instead. So I'll assume
        # on the moment of the plugin's init volume is unmuted
        self.bus.on('mycroft.volume.duck', self.set_vol_mute_on)
        self.bus.on('mycroft.volume.unduck', self.set_vol_mute_off)
        self.register_mqtt_handler(VOL_MUTE_SET_TOPIC, self.process_vol_mute_command)
        self.register_advertise_function(self.advertise_vol_mute)
        # Set initial state
        self.set_vol_mute_off()

    def set_vol_mute_on(self, event=None):
        self.set_sensor_state(self.expand(VOL_MUTE_STATE_TOPIC), ON)

    def set_vol_mute_off(self, event=None):
        self.set_sensor_state(self.expand(VOL_MUTE_STATE_TOPIC), OFF)

    def process_vol_mute_command(self, state):
        if state == ON:
            self.log.info('Switch VOL MUTE toggled on via MQTT')
            self.bus.emit(Message('mycroft.volume.mute', data={'speak_message': False}))
        elif state == OFF:
            self.log.info('Switch VOL MUTE toggled off via MQTT')
            self.bus.emit(Message('mycroft.volume.unmute', data={'speak_message': False}))
        else:
            self.log.warning("Payload {} is unknown".format(state))

    def advertise_vol_mute(self):
        id = self.mqtt_discovery_unique_id() + "vol_mute"
        config = {
            "command_topic": self.expand(VOL_MUTE_SET_TOPIC),
            "state_topic": self.expand(VOL_MUTE_STATE_TOPIC),
            "name": "Mycroft Speaker Muted",
            "uniq_id": id,
            "pl_on": ON,
            "pl_off": OFF,
            "icon": "mdi:volume-off",
            "device": self.mqtt_device_config(),
            **self.mqtt_availability_config()
        }
        self.mqtt.publish(
            self.expand(SWITCH_DISCOVERY_TOPIC, id=id),
            payload=json.dumps(config),
            retain=True
        )


    # Speaking binary sensors
    def init_speaking_sensor(self):
        self.bus.on(
            'recognizer_loop:audio_output_start',
            self.set_speaking_on
        )
        self.bus.on(
            'recognizer_loop:audio_output_end',
            self.set_speaking_off
        )
        self.register_advertise_function(self.advertise_speaking)
        self.set_speaking_off()

    def set_speaking_on(self, event=None):
        self.set_sensor_state(self.expand(SPEAKING_STATE_TOPIC), ON)

    def set_speaking_off(self, event=None):
        self.set_sensor_state(self.expand(SPEAKING_STATE_TOPIC), OFF)

    def advertise_speaking(self):
        id = self.mqtt_discovery_unique_id() + "speaking"
        config = {
            "state_topic": self.expand(SPEAKING_STATE_TOPIC),
            "name": "Mycroft Is Speaking",
            "uniq_id": id,
            "pl_on": ON,
            "pl_off": OFF,
            "icon": "mdi:account-voice",
            "device": self.mqtt_device_config(),
            **self.mqtt_availability_config()
        }
        self.mqtt.publish(
            self.expand(BINARY_SENSOR_DISCOVERY_TOPIC, id=id),
            payload=json.dumps(config),
            retain=True)


    # Listening binary sensor
    def init_listening_sensor(self):
        self.bus.on(
            'recognizer_loop:record_begin',
            self.set_listening_on
        )
        self.bus.on(
            'recognizer_loop:record_end',
            self.set_listening_off
        )        
        self.register_advertise_function(self.advertise_listening)
        self.set_listening_off()

    def set_listening_on(self, event=None):
        self.set_sensor_state(LISTENING_STATE_TOPIC, ON)

    def set_listening_off(self, event=None):
        self.set_sensor_state(LISTENING_STATE_TOPIC, OFF)

    def advertise_listening(self):
        id = self.mqtt_discovery_unique_id() + "listening"
        config = {
            "state_topic": self.expand(LISTENING_STATE_TOPIC),
            "name": "Mycroft Is Listening",
            "uniq_id": id,
            "pl_on": ON,
            "pl_off": OFF,
            "icon": "mdi:ear-hearing",
            "device": self.mqtt_device_config(),
            **self.mqtt_availability_config()
        }
        self.mqtt.publish(
            self.expand(BINARY_SENSOR_DISCOVERY_TOPIC, id=id),
            payload=json.dumps(config),
            retain=True
        )


    # Listen button
    def init_listen_button(self):
        self.register_mqtt_handler(LISTEN_BUTTON_TOPIC, self.process_listen_button)
        self.register_advertise_function(self.advertise_listen_button)

    def process_listen_button(self, state):
        if state == PRESS:
            self.log.info('Command listening triggered by MQTT')
            self.bus.emit(Message('mycroft.mic.listen'))
        else:
            self.log.warning("Payload {} is unknown".format(state))

    def advertise_listen_button(self):
        id = self.mqtt_discovery_unique_id() + "listen_button"
        config = {
            "command_topic": self.expand(LISTEN_BUTTON_TOPIC),
            "name": "Mycroft Listen Command",
            "uniq_id": id,
            "payload_press": PRESS,
            "icon": "mdi:record-rec",
            "device": self.mqtt_device_config(),
            **self.mqtt_availability_config()
        }
        self.mqtt.publish(
            self.expand(BUTTON_DISCOVERY_TOPIC, id=id),
            payload=json.dumps(config),
            retain=True
        )


    # Command topic
    def init_command(self):
        self.register_mqtt_handler(COMMAND_TOPIC, self.process_command)

    def process_command(self, command):
        self.bus.emit(Message("recognizer_loop:utterance", {
            'utterances': [command],
            'lang': self.lang
        }))


def create_skill():
    return MqttAdapterSkill()

