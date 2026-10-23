import os

# Server Configuration
HOST = os.getenv("EDGE_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("EDGE_PORT", 3000)))

# Database Configuration
DATABASE_PATH = os.getenv("EDGE_DATABASE_PATH", "electrolink_edge.db")

# Cloud Backend API Configuration
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "https://electrolink-backend.onrender.com")
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", 5))
SYNC_BATCH_SIZE = int(os.getenv("SYNC_BATCH_SIZE", 50))

# Edge API Key for authenticating against the backend
EDGE_API_KEY = os.getenv("EDGE_API_KEY", "el-edge-api-key-secreto-2024")
