from flask import Flask, render_template, request, jsonify
import subprocess
import json
import paho.mqtt.publish as publish

app = Flask(__name__)

# MQTT Broker Configuration
MQTT_BROKER = "localhost"  # change to your broker IP
MQTT_PORT = 1883

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/put-config', methods=['POST'])
def put_config():
    data = request.json
    ip = data.get('ip')
    port = data.get('port')
    freq = data.get('freq')
    bw = data.get('bw')
    ratio = data.get('ratio')
    power = data.get('power')

    command = (
        f"curl -X PUT https://{ip}:{port}/5g/bs/conf -k -u admin:admin -d "
        f"'{{\"Name\": \"BS-114\", \"ID\": \"14\", \"Band\": \"78\", \"Bandwidth\": \"{bw}\", "
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
    data = request.json
    topic = data.get('topic')
    payload = data.get('payload')
    try:
        publish.single(topic, payload=payload, hostname=MQTT_BROKER, port=MQTT_PORT)
        return jsonify({"status": f"MQTT message sent to '{topic}' with payload '{payload}'."})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    threading.Thread(target=mqtt_subscriber, daemon=True).start()
    app.run(host='0.0.0.0', port=1100, debug=True)
