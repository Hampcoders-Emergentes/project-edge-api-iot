# Plan Detallado — Etapa 3: Integración Local y Sincronización Edge API ↔ Backend

## Resumen

Reemplazar los thresholds hardcodeados del Edge API (`normalLimit: 0.20`, `alertLimit: 0.60`) por valores reales sincronizados desde el backend .NET, completando el pipeline:

```
Onboarding IA (8 campos) → Backend .NET → SyncWorker → Edge API → POST /readings → ESP32
```

---

## 1. Arquitectura del Flujo

```
Backend .NET (Processing BC)
┌─────────────────────────────────────────────────┐
│ EdgeIngestionController                         │
│  POST /readings          (existente)            │
│  GET /devices/{id}/thresholds  (NUEVO)          │
│  [RequireEdgeApiKey]     (existente)            │
└──────────────────────┬──────────────────────────┘
                       │ GET /devices/{id}/thresholds
                       │ X-Api-Key: ...
                       ▼
Edge API (FastAPI Python)
┌─────────────────────────────────────────────────┐
│ SyncWorker (cada 5s)                            │
│  _pull_device_configurations()  (NUEVO)          │
│  → almacena en DeviceConfig table  (NUEVO)      │
│                                                  │
│ POST /api/electrolink/readings                   │
│  → busca en DeviceConfig por deviceId            │
│  → retorna thresholds reales (no hardcodeados)   │
└──────────────────────┬──────────────────────────┘
                       │ { thresholds: { normalLimit, alertLimit } }
                       ▼
ESP32 (Wokwi)
┌─────────────────────────────────────────────────┐
│ HttpEdgeGatewayClient._parseThresholds()         │
│  → actualiza currentNormalLimit y                │
│    currentAlertLimit en caliente                 │
└─────────────────────────────────────────────────┘
```

---

## 2. Backend .NET — Cambios

### 2.1 Nuevos Archivos

| Archivo | Propósito |
|---------|-----------|
| `Processing/Domain/Model/Aggregates/DeviceThreshold.cs` | Entidad con deviceId + 8 campos de thresholds |
| `Processing/Domain/Repositories/IDeviceThresholdRepository.cs` | Interfaz del repositorio |
| `Processing/Infrastructure/Persistence/Repositories/DeviceThresholdRepository.cs` | Implementación EF Core |
| `Processing/Interfaces/REST/Resources/DeviceThresholdResource.cs` | DTO de respuesta |

### 2.2 Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `Processing/Interfaces/REST/EdgeIngestionController.cs` | Agregar `GET /devices/{deviceId}/thresholds` |
| `Profiles/Interfaces/REST/Resources/SuggestedThresholdsResource.cs` | Agregar `NormalLimitAmps` y `AlertLimitAmps` |
| `appsettings.json` | Agregar sección `EdgeApi:ApiKey` |
| `Processing/Infrastructure/Interfaces.ASP/Configuration/Extensions/WebApplicationBuilderExtensions.cs` | Registrar `IDeviceThresholdRepository` |

### 2.3 DeviceThreshold Entidad

Almacena 8 campos: `NormalLimitAmps`, `AlertLimitAmps`, `MaxConsumptionWatts`, `MaxCurrentAmps`, `MinPowerFactor`, `NominalVoltage`, `NominalFrequency`, `DisconnectionThresholdMin`.

### 2.4 Endpoint GET

```
GET /api/v1/iot/edge/devices/{deviceId}/thresholds
```
- Auth: `[RequireEdgeApiKey]`
- Retorna `200` con los thresholds o `404` si no existe
- El Edge API usa `404` como señal para mantener defaults

---

## 3. Edge API — Cambios

### 3.1 Nuevo modelo DeviceConfig en database.py

```python
class DeviceConfig(BaseModel):
    device_id = CharField(max_length=100, primary_key=True)
    config_json = TextField()
    updated_at = DateTimeField(default=datetime.utcnow)
```

### 3.2 Nueva variable EDGE_API_KEY

En `config.py` para autenticación contra el backend.

### 3.3 _pull_device_configurations en SyncWorker

Itera los device_ids de las readings locales, llama al backend y hace upsert en DeviceConfig.

### 3.4 POST /readings actualizado

Busca en DeviceConfig por deviceId. Si existe, usa esos thresholds. Si no, usa defaults hardcodeados (0.20/0.60).

---

## 4. Onboarding IA — Agregar normalLimit/alertLimit

| Archivo | Cambio |
|---------|--------|
| `onboarding-system-prompt.txt` | Instruir a Groq que devuelva `normalLimitAmps` y `alertLimitAmps` |
| `SuggestedThresholdsResource.cs` | +2 campos |
| `device_onboarding_data.dart` | +2 campos |

---

## 5. Conectividad ngrok

| Componente | URL |
|---|---|
| Edge API | `localhost:3000` |
| ngrok | `https://xxxx.ngrok-free.app → localhost:3000` |
| ESP32 Config.h | `EDGE_API_URL = https://xxxx.ngrok-free.app/api/electrolink/readings` |
| Backend .NET | `localhost:8088` (Edge lo llama directo) |

---

## 6. Resumen de Archivos

| Capa | Nuevos | Modificados |
|------|--------|-------------|
| Backend .NET | 4 | 4 |
| Edge API Python | 0 | 4 |
| Mobile Flutter | 0 | 1 |
| Prompt | 0 | 1 |
| Documentación | 1 | 0 |
| **Total** | **5** | **10** |

---

## 7. Estado de Implementación

- [x] Documento etapa3.md creado
- [ ] Backend: DeviceThreshold entidad + repo
- [ ] Backend: GET endpoint
- [ ] Backend: SuggestedThresholdsResource + EdgeApi:ApiKey
- [ ] Edge API: DeviceConfig + EDGE_API_KEY
- [ ] Edge API: _pull_device_configurations
- [ ] Edge API: POST /readings actualizado
- [ ] Prompt: normalLimitAmps/alertLimitAmps
- [ ] Mobile: modelo actualizado
- [ ] Verificación: dotnet build + flutter analyze

---

**Fin de Etapa 3**
