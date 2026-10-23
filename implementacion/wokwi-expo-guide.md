# Guía de Integración Wokwi / Expo — ElectroLink IoT

## Arquitectura General

```
Wokwi / ESP32 Físico              Edge API (Python)            Backend .NET              App Móvil
┌─────────────────────┐          ┌─────────────────┐         ┌──────────────────┐      ┌──────────────┐
│ deviceId:           │          │                 │         │                  │      │              │
│  "electrolink-      │  POST    │ POST /readings   │  Sync   │ GET /devices/{id}│      │  Onboarding  │
│   esp32-01"         │────────► │ Almacena lectura │◄────────│ /thresholds      │◄─────│  con IA      │
│                     │          │ Busca thresholds │         │                  │      │              │
│ Recibe thresholds   │◄─────────│ en DeviceConfig  │         │                  │      │              │
│ en la respuesta     │          │ (SQLite local)   │         │                  │      │              │
└─────────────────────┘          └─────────────────┘         └──────────────────┘      └──────────────┘
      Cada 5 segundos                  Cada 5 segundos               Cada 5s
```

## Cómo se propaga un threshold desde la App al ESP32

### Paso a paso:

1. **Visitante abre la app móvil** → crea cuenta → hace onboarding de dispositivo
2. **La IA (Groq)** analiza el dispositivo y devuelve 8 campos:
   - `normalLimitAmps`, `alertLimitAmps`, `nominalVoltage`, `maxConsumptionWatts`,
     `maxCurrentAmps`, `minPowerFactor`, `nominalFrequency`, `disconnectionThresholdMin`
3. **El usuario confirma** los thresholds → `PUT /profiles/{profileId}/thresholds`
4. **Backend .NET** guarda en el perfil y dispara `ConsumptionThresholdsUpdatedEvent`
5. **El EventHandler** hace 2 cosas:
   - **A)** Actualiza los streams del owner (para su device personal)
   - **B)** Actualiza el stream del **device demo** `electrolink-esp32-01`
6. **Edge API** (SyncWorker, cada 5s): llama a `GET /api/v1/iot/edge/devices/electrolink-esp32-01/thresholds`
7. **Edge API** guarda la respuesta en su tabla local `DeviceConfig`
8. **ESP32** envía `POST /api/electrolink/readings`
9. **Edge API** busca en `DeviceConfig` por `deviceId` y devuelve los thresholds
10. **ESP32** parsea `normalLimit` y `alertLimit` y los aplica en caliente

### ¿Qué pasa si el stream demo no existe?

Cuando el Edge API llama `GET /devices/electrolink-esp32-01/thresholds` por primera vez,
el endpoint **crea automáticamente** un `DeviceReadingStream` con valores por defecto
si no existe, asegurando que siempre haya un stream donde escribir los thresholds.

## Modelo de Datos

### Backend .NET — GET /api/v1/iot/edge/devices/{deviceId}/thresholds

**Response (200 OK):**
```json
{
  "deviceId": "electrolink-esp32-01",
  "thresholds": {
    "normalLimit": 0.20,
    "alertLimit": 0.60,
    "nominalVoltage": 220,
    "maxConsumptionWatts": 5000,
    "maxCurrentAmps": 20,
    "minPowerFactor": 0.85,
    "nominalFrequency": 60,
    "disconnectionThresholdMin": 30
  }
}
```

El Edge API toma `response["thresholds"]` y lo guarda en `DeviceConfig`.

### Edge API — POST /api/electrolink/readings

**Response (200 OK):**
```json
{
  "status": "success",
  "thresholds": {
    "normalLimit": 0.20,
    "alertLimit": 0.60
  },
  "relayCommand": { }
}
```

### ESP32 — parseo de thresholds

El firmware (`HttpEdgeGatewayClient._parseThresholds()`) espera:
- `response["thresholds"]["normalLimit"]` — float, debe ser > 0
- `response["thresholds"]["alertLimit"]` — float, debe ser > normalLimit
- Los otros 6 campos (`nominalVoltage`, `maxConsumptionWatts`, etc.) se leen si existen, si no mantienen valores por defecto firmados en `Config.h`

El ESP32 loguea los 8 campos recibidos en la consola serial cada vez que se actualizan.

## Cómo probar todo (Expo / Local)

### Requisitos

| Componente | Comando |
|---|---|
| Backend .NET | `cd electrolink-backend-api && dotnet run` (puerto 8088) |
| Edge API | `cd electrolink-edge-api && python main.py` (puerto 3000) |
| ngrok | `ngrok http 3000` |
| Mobile App | `cd electrolink-mobile-app && flutter run` |
| Wokwi | Abrir en wokwi.com con `diagram.json` |

### Orden de arranque

```bash
# 1. Backend
cd electrolink-backend-api
dotnet run
# Esperar a que muestre "Now listening on http://localhost:8088"

# 2. Edge API (nueva terminal)
cd electrolink-edge-api
$env:EDGE_API_KEY="el-edge-api-key-secreto-2024"
python main.py
# Esperar a que muestre "[SyncWorker] Started..."

# 3. ngrok (nueva terminal)
ngrok http 3000
# Copiar la URL https://xxxx.ngrok-free.app

# 4. Configurar ESP32
# En Config.h del firmware:
#   #define EDGE_API_URL "https://xxxx.ngrok-free.app/api/electrolink/readings"
# Recompilar y ejecutar en Wokwi

# 5. Mobile App
cd electrolink-mobile-app
flutter run
```

### Secuencia de prueba desde cero

Sigue estos pasos en orden para validar que todo funcione correctamente.

#### Paso 1: Arrancar Backend .NET
```bash
cd electrolink-backend-api
dotnet run
# Esperar: "Now listening on http://localhost:8088"
```

#### Paso 2: Verificar Backend (endpoint de thresholds)
```bash
curl -H "X-Api-Key: el-edge-api-key-secreto-2024" \
  http://localhost:8088/api/v1/iot/edge/devices/electrolink-esp32-01/thresholds
# Debe responder con los 8 campos (valores default):
# { "deviceId": "electrolink-esp32-01", "thresholds": { "normalLimit": 0.20, "alertLimit": 0.60, "nominalVoltage": 220, ... } }
# Si es la primera vez, el backend crea automaticamente el stream demo.
```

#### Paso 3: Arrancar Edge API
```bash
cd electrolink-edge-api
python main.py
# Esperar logs:
# [Lifespan] Initializing SQLite database...
# [Lifespan] Starting background sync worker...
# [SyncWorker] Started background sync worker.
```

#### Paso 4: Verificar SyncWorker
En la consola del Edge API, a los ~5 segundos debe aparecer:
```
[SyncWorker] Config pulled for electrolink-esp32-01: {'normalLimit': 0.2, 'alertLimit': 0.6, 'nominalVoltage': 220.0, ...}
```
Si aparece `No thresholds for device`, esperar otro ciclo o verificar que el backend esté corriendo.

#### Paso 5: Simular una lectura del ESP32
```bash
curl -X POST http://localhost:3000/api/electrolink/readings \
  -H "Content-Type: application/json" \
  -d '{ "deviceId": "electrolink-esp32-01", "currentAcs": 0.15, "currentIna": 0.14, "voltage": 5.0, "power": 0.75, "relay": true, "status": "NORMAL", "timestamp": 1000 }'
```
En la consola del Edge API debe aparecer:
```
[Readings] Returning thresholds for electrolink-esp32-01: {'normalLimit': 0.2, 'alertLimit': 0.6, 'nominalVoltage': 220.0, ...}
```

#### Paso 6: Arrancar ngrok y Wokwi
```bash
# Terminal 3
ngrok http 3000
# Copiar URL https://xxxx.ngrok-free.app

# En Config.h: EDGE_API_URL = "https://xxxx.ngrok-free.app/api/electrolink/readings"
# Compilar y ejecutar Wokwi
```
El monitor serial del ESP32 debe mostrar:
```
[Edge] POST -> HTTP 200
[Edge] Thresholds recibidos (8 campos):
  normalLimit: 0.20
  alertLimit: 0.60
  nominalVoltage: 220
  maxConsumptionWatts: 5000
  maxCurrentAmps: 20.00
  minPowerFactor: 0.85
  nominalFrequency: 60
  disconnectionThresholdMin: 30
```

#### Paso 7: Hacer onboarding desde la app
1. Abrir la app móvil → crear cuenta
2. Ir a onboarding → responder preguntas del dispositivo
3. La IA responde con 8 campos → confirmar
4. En la consola del Backend debe aparecer:
   ```
   [IoT] Demo device electrolink-esp32-01 thresholds updated
   ```
5. En la consola del Edge API (en ~5 segundos):
   ```
   [SyncWorker] Thresholds CHANGED for electrolink-esp32-01: {'normalLimit': 0.35, 'alertLimit': 1.2, ...}
   ```
6. En el monitor serial del ESP32 (en ~5 segundos):
   ```
   [Edge] Thresholds recibidos (8 campos):
     normalLimit: 0.35
     alertLimit: 1.20
     ...
   ```
7. En el OLED se actualiza `Vnom: 220V` (6ta línea abajo del estado).

#### Paso 8: Verificar la DB local del Edge API
```bash
sqlite3 electrolink_edge.db "SELECT device_id, config_json FROM device_config;"
```

### Flujo de prueba completo

```
1. Abrir Wokwi → ESP32 inicia, envía lecturas
2. Edge API logs: muestra lecturas recibidas
3. SyncWorker: pullea config para electrolink-esp32-01
   → Backend auto-crea stream demo → devuelve thresholds default (0.20/0.60)
4. ESP32 logs: "Umbrales actualizados -> Normal: 0.20 A | Peligro: 0.60 A"
5. Abrir app móvil → crear cuenta → onboarding
6. App logs: IA responde con 8 campos
7. Confirmar thresholds → PUT /thresholds
8. Backend logs: "Demo device electrolink-esp32-01 thresholds updated"
9. SyncWorker logs: "Config pulled for device electrolink-esp32-01"
10. ESP32 recibe nuevos thresholds → "Umbrales actualizados -> Normal: X A | Peligro: Y A"
```

### Verificar cada componente

#### Backend .NET
```bash
# Probar el endpoint directamente
curl -H "X-Api-Key: el-edge-api-key-secreto-2024" \
  http://localhost:8088/api/v1/iot/edge/devices/electrolink-esp32-01/thresholds
# Response: { "deviceId": "electrolink-esp32-01", "thresholds": { "normalLimit": 0.20, "alertLimit": 0.60 } }
```

#### Edge API
```bash
# Simular una lectura del ESP32
curl -X POST http://localhost:3000/api/electrolink/readings \
  -H "Content-Type: application/json" \
  -d '{ "deviceId": "electrolink-esp32-01", "currentAcs": 0.15, "currentIna": 0.14, "voltage": 220, "power": 33, "relay": true, "status": "NORMAL", "timestamp": 1000 }'
# Response debe incluir thresholds dinámicos, no hardcodeados
```

#### Edge API — Ver tabla DeviceConfig
```bash
# Conectarse a la DB
sqlite3 electrolink_edge.db "SELECT * FROM device_config;"
```

### Troubleshooting

| Síntoma | Causa | Solución |
|---|---|---|
| ESP32 no actualiza thresholds | `alertLimit` no es > `normalLimit` | Verificar valores en onboarding |
| Edge API no pull config | Backend no corre | Iniciar backend primero |
| SyncWorker no conecta al backend | `BACKEND_BASE_URL` incorrecto | Verificar config.py |
| `POST /readings` devuelve 500 | `EdgeApi:ApiKey` mismatch | Confirmar mismo key en appsettings.json y config.py |
| ESP32 no recibe thresholds | URL de ngrok desactualizada | Regenerar ngrok y actualizar Config.h |
| No hay stream para demo device | Primera vez que se consulta | Se crea automáticamente — hacer GET una vez |
| Thresholds del demo no se actualizan tras onboarding | Demo stream no existe aún | Hacer GET /thresholds primero para crearlo |

## Notas para Expo Física

- El ESP32 físico se conecta a WiFi local (configurar `WIFI_SSID` en `Config.h`)
- El Edge API corre en una laptop con ngrok apuntando a ella
- ngrok da una URL pública que el ESP32 puede alcanzar aunque esté en otra red
- Cada visitante que hace onboarding sobreescribe los thresholds del device demo
- El ESP32 refleja los cambios en ~5-10 segundos (SyncWorker cada 5s + ESP32 cada 5s)

## Resumen de Endpoints

| Componente | Endpoint | Método | Auth | Propósito |
|---|---|---|---|---|
| Backend .NET | `/api/v1/iot/edge/devices/{deviceId}/thresholds` | GET | X-Api-Key | Edge sync de thresholds |
| Backend .NET | `/api/v1/iot/edge/readings` | POST | X-Api-Key | Ingestion de lecturas |
| Edge API | `/api/electrolink/readings` | POST | — | Recibir lecturas del ESP32 |
| Backend .NET | `/api/v1/profiles/{profileId}/thresholds` | PUT | JWT | Guardar thresholds desde app |
| Backend .NET | `/api/v1/profiles/me/device-onboarding/analyze` | POST | JWT | Analizar dispositivo con IA |
