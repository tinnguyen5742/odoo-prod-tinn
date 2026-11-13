FROM python:3.12-slim
RUN pip install --no-cache-dir paho-mqtt==2.1.0
COPY eam_mqtt_bridge.py /app/eam_mqtt_bridge.py
USER 65534:65534
CMD ["python", "-u", "/app/eam_mqtt_bridge.py"]
