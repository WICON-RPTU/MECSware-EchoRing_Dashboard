from flask import Flask, render_template, request, jsonify
import subprocess
import json
import threading
import paho.mqtt.client as mqtt

app = Flask(__name__)

# MQTT broker config
MQTT_BROKER = "10.0.3.5"  # Broker for sending MQTT
MQTT_PORT = 1337

# MQTT subscriber config
MQTT_SUB_BROKER = "10.0.5.3"
MQTT_SUB_PORT = 1335
MQTT_SUB_TOPIC = "#"  # subscribe to all topics

# Store latest received MQTT messages
latest_echoring_message = "--"
latest_messages = {}


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
    from paho.mqtt.publish import single as mqtt_publish
    data = request.json

    topic = data.get('topic')
    payload = data.get('payload')

    if not topic or not payload:
        return jsonify({"error": "Missing 'topic' or 'payload' in request."}), 400

    try:
        mqtt_publish(
            topic,
            payload,
            hostname=MQTT_BROKER,
            port=MQTT_PORT
        )
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


# MQTT Subscriber Thread
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
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_SUB_BROKER, MQTT_SUB_PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"[MQTT] Connection error: {e}")


if __name__ == '__main__':
    threading.Thread(target=mqtt_subscriber, daemon=True).start()
    app.run(host='0.0.0.0', port=1100, debug=True)
