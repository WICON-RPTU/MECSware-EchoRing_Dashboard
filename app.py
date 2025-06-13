from flask import Flask, render_template, request, jsonify
import subprocess
import json
import threading
import paho.mqtt.client as mqtt
from paho.mqtt.publish import single as mqtt_publish

app = Flask(__name__)

# Initial MQTT broker and sub-broker config
mqtt_config = {
    "broker_ip": "10.0.3.5",        # for publishing
    "broker_port": 1337,
    "sub_broker_ip": "10.0.5.3",    # for subscribing
    "sub_broker_port": 1335
}

MQTT_SUB_TOPIC = "#"  # subscribe to all topics

# MQTT runtime state
latest_echoring_message = "--"
latest_messages = {}
mqtt_client = None
mqtt_pub_client = None      # MQTT publisher client


@app.route('/')
def dashboard():
    return render_template('index.html')


@app.route('/api/put-config', methods=['POST'])
def put_config():
    data = request.json
    ip = data.get('ip')
    port = data.get('port')
    name = data.get('name')
    freq = data.get('freq')
    bw = data.get('bw')
    ratio = data.get('ratio')
    power = data.get('power')

    command = (
        f"curl -X PUT https://{ip}:{port}/5g/bs/conf -k -u admin:admin -d "
        f"'{{\"Name\": \"{name}\", \"ID\": \"14\", \"Band\": \"78\", \"Bandwidth\": \"{bw}\", "
        f"\"Frequency\": \"{freq}\", \"Ratio\": \"{ratio}\", \"Power\": \"{power}\", \"Sync\": \"free\"}}' "
        f"-H \"Content-Type: application/json\" -v"
    )

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return jsonify({"output": result.stdout})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Operation timed out."})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/get-status', methods=['POST'])
def get_status():
    data = request.json
    ip = data.get('ip')
    port = data.get('port')
    name = data.get('name')

    command = (
        f"curl -X GET https://{ip}:{port}/5g/bs/status/{name} -k -u admin:admin "
        f"-H \"Content-Type: application/json\" -v"
    )

    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        try:
            json_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            json_data = {"raw": result.stdout}
        return jsonify(json_data)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Operation timed out."})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/ping', methods=['POST'])
def ping():
    data = request.json
    ip = data.get('ip')
    try:
        result = subprocess.run(['ping', '-c', '1', ip], capture_output=True, text=True)
        return jsonify({"output": result.stdout, "success": result.returncode == 0})
    except Exception as e:
        return jsonify({"error": str(e), "success": False})


@app.route('/api/send-mqtt', methods=['POST'])
def send_mqtt():
    global mqtt_pub_client
    data = request.json
    topic = data.get('topic')
    payload = data.get('payload')

    if not topic or not payload:
        return jsonify({"error": "Missing 'topic' or 'payload' in request."}), 400

    try:
        if mqtt_pub_client is None:
            mqtt_pub_client = mqtt.Client()
            mqtt_pub_client.connect(mqtt_config["broker_ip"], mqtt_config["broker_port"], 60)
            mqtt_pub_client.loop_start()

        mqtt_pub_client.publish(topic, payload)
        print(f"[MQTT PUB] Sent to {mqtt_config['broker_ip']}:{mqtt_config['broker_port']} -> {topic}: {payload}")
        return jsonify({"status": "MQTT message sent."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route('/api/echoring-status')
def echoring_status():
    return jsonify({"status": latest_echoring_message})


@app.route('/api/mqtt-message')
def mqtt_message():
    topic = request.args.get('topic')
    message = latest_messages.get(topic, "--")
    return jsonify({"message": message})


@app.route('/api/update-mqtt-settings', methods=['POST'])
def update_mqtt_settings():
    data = request.json
    try:
        mqtt_config["broker_ip"] = data.get("main_broker_ip", mqtt_config["broker_ip"])
        mqtt_config["broker_port"] = int(data.get("main_broker_port", mqtt_config["broker_port"]))
        mqtt_config["sub_broker_ip"] = data.get("sub_broker_ip", mqtt_config["sub_broker_ip"])
        mqtt_config["sub_broker_port"] = int(data.get("sub_broker_port", mqtt_config["sub_broker_port"]))
        return jsonify({"status": "MQTT settings updated."})
    except Exception as e:
        return jsonify({"error": str(e)}), 400



@app.route('/api/get-mqtt-settings')
def get_mqtt_settings():
    return jsonify({
        "main_broker_ip": mqtt_config['broker_ip'],
        "main_broker_port": mqtt_config['broker_port'],
        "sub_broker_ip": mqtt_config['sub_broker_ip'],
        "sub_broker_port": mqtt_config['sub_broker_port']
    })


@app.route('/api/reconnect-mqtt', methods=['POST'])
def reconnect_mqtt():
    global mqtt_client, mqtt_pub_client

    try:
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
            print("[MQTT SUB] Disconnected.")

        if mqtt_pub_client:
            mqtt_pub_client.loop_stop()
            mqtt_pub_client.disconnect()
            print("[MQTT PUB] Disconnected.")

        # Reconnect subscriber
        mqtt_client = mqtt.Client()
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        mqtt_client.connect(mqtt_config["sub_broker_ip"], mqtt_config["sub_broker_port"], 60)
        mqtt_client.loop_start()
        print(f"[MQTT SUB] Reconnected to {mqtt_config['sub_broker_ip']}:{mqtt_config['sub_broker_port']}")

        # Reconnect publisher
        mqtt_pub_client = mqtt.Client()
        mqtt_pub_client.connect(mqtt_config["broker_ip"], mqtt_config["broker_port"], 60)
        mqtt_pub_client.loop_start()
        print(f"[MQTT PUB] Reconnected to {mqtt_config['broker_ip']}:{mqtt_config['broker_port']}")

        return jsonify({"status": "MQTT clients reconnected."})
    except Exception as e:
        return jsonify({"error": f"Reconnect failed: {e}"}), 500




# MQTT Subscriber Setup
def on_connect(client, userdata, flags, rc):
    print("[MQTT] Connected with result code", rc)
    client.subscribe(MQTT_SUB_TOPIC)


def on_message(client, userdata, msg):
    global latest_echoring_message
    message = msg.payload.decode()
    print(f"[MQTT] Topic: {msg.topic}, Message: {message}")
    latest_messages[msg.topic] = message
    if msg.topic == "/echoringfeedback":
        latest_echoring_message = message


def mqtt_subscriber():
    global mqtt_client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    try:
        mqtt_client.connect(mqtt_config["sub_broker_ip"], mqtt_config["sub_broker_port"], 60)
        mqtt_client.loop_start()
        print(f"[MQTT] Subscriber connected to {mqtt_config['sub_broker_ip']}:{mqtt_config['sub_broker_port']}")
    except Exception as e:
        print(f"[MQTT] Initial subscriber connection failed: {e}")




if __name__ == '__main__':
    threading.Thread(target=mqtt_subscriber, daemon=True).start()
    app.run(host='0.0.0.0', port=1100, debug=True)
