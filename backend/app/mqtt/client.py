import paho.mqtt.client as mqtt
import json
import asyncio
import logging
from app.core.config import settings
# FIX: Import from db.session, not api.dependencies
from app.db.session import AsyncSessionLocal
from app.models.domain import Command, CommandStatus
from sqlalchemy import update

logger = logging.getLogger(__name__)

class MQTTManager:
    def __init__(self):
        self.client = mqtt.Client(client_id="gridsphere_backend")
        if settings.MQTT_USER:
            self.client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASS)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def start(self):
        try:
            self.client.connect(settings.MQTT_BROKER, settings.MQTT_PORT, 60)
            self.client.loop_start()
            logger.info(f"MQTT Client started. Broker: {settings.MQTT_BROKER}")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT Broker: {e}")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT Broker successfully.")
            client.subscribe("gridsphere/+/+/acks")
        else:
            logger.error(f"MQTT Connection failed with code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            command_id = payload.get("cmd_id")
            status = payload.get("status")
            
            if command_id and status:
                # Use a background task to handle the async DB update
                asyncio.run(self.update_command_status(command_id, status))
        except Exception as e:
            logger.error(f"MQTT Message Error: {e}")

    async def update_command_status(self, command_id: int, status: str):
        async with AsyncSessionLocal() as db:
            try:
                await db.execute(
                    update(Command)
                    .where(Command.id == command_id)
                    .values(status=CommandStatus.SUCCESS if status == "success" else CommandStatus.FAILED)
                )
                await db.commit()
                logger.info(f"Updated Command {command_id} status to {status}")
            except Exception as e:
                logger.error(f"Database update error from MQTT: {e}")
                await db.rollback()

    def publish_command(self, tenant_id: int, device_id: str, command_id: int, command: str, target_id: int):
        topic = f"gridsphere/{tenant_id}/{device_id}/commands"
        payload = json.dumps({
            "cmd_id": command_id, 
            "command": command, 
            "target_id": target_id
        })
        self.client.publish(topic, payload, qos=1)
        logger.info(f"Published command {command} to {topic}")

mqtt_manager = MQTTManager()