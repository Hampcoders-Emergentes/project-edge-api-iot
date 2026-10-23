from datetime import datetime
from peewee import SqliteDatabase, Model, AutoField, CharField, FloatField, BooleanField, DateTimeField, TextField
import config

db = SqliteDatabase(config.DATABASE_PATH)

class BaseModel(Model):
    class Meta:
        database = db

class Reading(BaseModel):
    id = AutoField()
    device_id = CharField(max_length=100)
    reading_id = CharField(max_length=50, unique=True)
    voltage = FloatField()
    current_acs = FloatField(default=0.0)
    current_ina = FloatField(default=0.0)
    power = FloatField()
    relay = BooleanField()
    status = CharField(max_length=50)
    timestamp = DateTimeField()  # Absolute UTC timestamp
    synced = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.utcnow)

    class Meta:
        table_name = "readings"

class RelayCommand(BaseModel):
    id = AutoField()
    command_id = CharField(max_length=100, unique=True)
    device_id = CharField(max_length=100)
    target_state = CharField(max_length=20)  # "ON" or "OFF"
    executed = BooleanField(default=False)
    synced = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.utcnow)

    class Meta:
        table_name = "relay_commands"

class DeviceConfig(BaseModel):
    device_id = CharField(max_length=100, primary_key=True)
    config_json = TextField()
    updated_at = DateTimeField(default=datetime.utcnow)

    class Meta:
        table_name = "device_config"

def _migrate_db():
    """Migra esquema SQLite de forma segura: agrega columnas si no existen."""
    import sqlite3
    conn = sqlite3.connect(config.DATABASE_PATH)
    cursor = conn.cursor()

    # Check if table exists first
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='readings'")
    if not cursor.fetchone():
        conn.close()
        return

    cursor.execute("PRAGMA table_info(readings)")
    existing = {row[1] for row in cursor.fetchall()}

    if 'current' in existing and 'current_acs' not in existing:
        cursor.execute("ALTER TABLE readings ADD COLUMN current_acs REAL DEFAULT 0.0")
        cursor.execute("UPDATE readings SET current_acs = current")
    if 'current' in existing:
        cursor.execute("ALTER TABLE readings DROP COLUMN current")
    if 'current_acs' not in existing:
        cursor.execute("ALTER TABLE readings ADD COLUMN current_acs REAL DEFAULT 0.0")
    if 'current_ina' not in existing:
        cursor.execute("ALTER TABLE readings ADD COLUMN current_ina REAL DEFAULT 0.0")

    conn.commit()
    conn.close()

def init_db():
    db.connect()
    db.create_tables([Reading, RelayCommand, DeviceConfig], safe=True)
    _migrate_db()
    db.close()
