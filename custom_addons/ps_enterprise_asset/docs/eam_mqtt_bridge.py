"""Forward MQTT telemetry to Odoo JSON-2. Run with paho-mqtt==2.1.0."""

import json
import logging
import os
import ssl
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import paho.mqtt.client as mqtt

log = logging.getLogger("eam-mqtt")


def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing {name}")
    return value


def credential(name):
    path = os.environ.get(name + "_FILE")
    if path:
        with open(path, encoding="utf-8") as source:
            return source.read().strip()
    return required(name)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api_url = required("ODOO_URL").rstrip("/") + "/json/2/ps.eam.meter/eam_ingest_mqtt"
    api_headers = {
        "Authorization": "Bearer " + credential("ODOO_API_KEY"),
        "X-Odoo-Database": required("ODOO_DATABASE"),
        "Content-Type": "application/json",
    }
    topic_filter = required("MQTT_TOPIC_FILTER")
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=required("MQTT_CLIENT_ID"),
        clean_session=False, protocol=mqtt.MQTTv311, manual_ack=True,
    )
    tls = os.environ.get("MQTT_TLS", "1") != "0"
    if tls:
        client.tls_set_context(ssl.create_default_context(cafile=os.environ.get("MQTT_CA_FILE")))
    username = os.environ.get("MQTT_USERNAME")
    if username:
        client.username_pw_set(username, credential("MQTT_PASSWORD"))

    def on_connect(connection, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            raise RuntimeError("MQTT broker rejected the connection")
        connection.subscribe(topic_filter, qos=1)
        log.info("Connected to MQTT broker")

    def on_message(connection, userdata, message):
        if message.qos == 0:
            log.warning("Ignored telemetry published with QoS 0")
            return
        try:
            payload = json.loads(message.payload)
            body = json.dumps({
                "topic": message.topic, "event_id": payload["event_id"],
                "value": payload["value"], "measured_at": payload["measured_at"],
            }, allow_nan=False).encode()
        except (KeyError, TypeError, ValueError):
            log.warning("Discarded invalid MQTT payload")
            connection.ack(message.mid, message.qos)
            return
        try:
            with urlopen(Request(api_url, data=body, headers=api_headers, method="POST"), timeout=15) as response:
                result = json.load(response)
                if not isinstance(result, dict) or not result.get("id"):
                    raise RuntimeError("Invalid acknowledgment from Odoo")
        except HTTPError as error:
            try:
                response = json.load(error)
                error_name = response.get("name", "")
            except (ValueError, AttributeError):
                error_name = ""
            if error_name != "odoo.exceptions.ValidationError":
                raise RuntimeError(f"Odoo rejected telemetry with HTTP {error.code}") from None
            log.warning("Odoo rejected invalid telemetry")
        connection.ack(message.mid, message.qos)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(required("MQTT_HOST"), int(os.environ.get("MQTT_PORT", 8883 if tls else 1883)))
    client.loop_forever()


if __name__ == "__main__":
    main()
