# Mycroft MQTT Adapter
A skill to control your Mycroft instance via MQTT protocol

## About 

To use this skill you need MQTT server and (possibly) some sort of home automation server. All features were tested with HomeAssistant but should also work with other servers (except, maybe, MQTT discovery - it was designed primary for HomeAssistant). Via this skill you can:

- Mute Mycroft's speaker and microphone
- Check if mycroft listening or speaking
- Activate command by button instead of wakeword
- Send commands directly to messagebus

MQTT credentials needed to connect to server should be setted via settings through home.mycroft.ai; after that Mycroft will connect to server. If discovery enabled (should be by default, can be changed via settings), you shold see Mycroft into Settings->Devices section. Also you can set up all switches/sensors manually using information below.

This skill uses topic `mycroft/subtopic` if you set subtopic via settings, or just `mycroft` if not. Below I'll assume you have only one mycroft instance and use it without device name. So there are topics you can use:

Availability topic:

- `mycroft/available` (payload - `ONLINE` or `OFFLINE`)

Mute microphone switch:

- `mycroft/mic_mute/set` (payload - `ON` or `OFF`)
- `mycroft/mic_mute/state` (payload - `ON` or `OFF`)

Mute speaker switch:

- `mycroft/vol_mute/set` (payload - `ON` or `OFF`)
- `mycroft/vol_mute/set` (payload - `ON` or `OFF`)

Speaking sensor:
- `mycroft/speaking` (payload - `ON` or `OFF`)

Listening sensor:
- `mycroft/listening` (payload - `ON` or `OFF`)

Listen button:
- `mycroft/listen_button` (payload - `PRESS`)

Command topic:
- `mycroft/command` (payload - any command)


 
## Credits 
@jumper047

## Category
IoT

## Tags
#IoT
#MQTT
#HomeAutomation
#HomeAssistant
