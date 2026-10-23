# Plan Detallado — Etapa 2: Onboarding Conversacional de Dispositivos IoT con IA (Groq)

Este documento detalla la implementación de la **Etapa 2** del ecosistema ElectroLink: un wizard de onboarding conversacional que permite a homeowners y empresas configurar umbrales de monitoreo para nuevos dispositivos IoT mediante análisis inteligente con Groq (modelo `llama-3.3-70b-versatile`).

---

## 1. Resumen de Cambios

| Capa | Archivos nuevos | Archivos modificados |
|------|----------------|---------------------|
| Backend (.NET 9) | 7 | 4 |
| Mobile (Flutter) | 14 | 5 |
| Documentación | 1 | — |
| **Total** | **22** | **9** |

---

## 2. Arquitectura del Flujo

```
Mobile (Flutter)                           Backend (.NET 9)
┌─────────────────────┐                    ┌──────────────────────────────┐
│ Step 1: Device Info │                    │  Profiles Bounded Context     │
│  - Tipo dispositivo │  POST analyze      │                              │
│  - Voltaje nominal  │───────────────────►│  DeviceOnboardingController   │
│  - Horas uso        │                    │    ↓                          │
│  - Ocupantes        │                    │  DeviceOnboardingService      │
│  - Ubicación        │                    │    ↓ (HTTP)                   │
│  - Uso principal    │                    │  Groq API (mixtral)           │
└─────────┬───────────┘                    │    ↓                          │
          │                                │  ← análisis estructurado     │
          ▼                                │                              │
┌─────────────────────┐                    │  ← DeviceOnboardingAnalysis   │
│ Step 2: AI Analysis │◄───────────────────│                              │
│  - Loading spinner  │   200 OK           └──────────────────────────────┘
│  - Reasoning card   │
└─────────┬───────────┘                    ┌──────────────────────────────┐
          │                                │  Profiles Bounded Context     │
          ▼                                │                              │
┌─────────────────────┐                    │  PUT /thresholds              │
│ Step 3: Confirmation│───────────────────►│  ProfilesContextFacade        │
│  - Sliders editables│                    │    ↓ (MediatR event)          │
│  - Confirmar button │                    │  Processing Bounded Context   │
└─────────────────────┘                    │    ↓                          │
                                           │  DeviceReadingStream          │
                                           │  .UpdateCustomThresholds()    │
                                           └──────────────────────────────┘
```

---

## 3. Backend — Perfiles de Contexto (Profiles BC)

### 3.1 Nuevos Archivos

#### `Profiles/Domain/Services/IDeviceOnboardingService.cs`
Interfaz del dominio con los records:
- `AnalyzeDeviceOnboardingRequest`: datos de entrada del wizard
- `SuggestedThresholds`: los 6 campos que mapean a `ThresholdConfig`
- `DeviceOnboardingAnalysis`: razonamiento + umbrales sugeridos
- `IDeviceOnboardingService.AnalyzeAsync()`: método principal

#### `Profiles/Application/Internal/CommandServices/DeviceOnboardingService.cs`
Implementación del servicio:
- Lee el prompt del sistema desde `ProfilesAISettings.SystemPromptPath`
- Serializa el request a JSON
- Llama a **Groq API** vía HTTP (formato OpenAI-compatible) con retry 3 intentos y timeout
- Parsea la respuesta JSON estructurada
- Fallback a valores predeterminados si Groq no responde

#### `Profiles/Infrastructure/ExternalProviders/ProfilesAISettings.cs`
Configuración para la integración con IA en Profiles:
- `SectionName = "ProfilesAI"`
- `ApiKey`, `ModelId`, `SystemPromptPath`, `MaxTokens`, `TimeoutSeconds`

#### `Profiles/Infrastructure/ExternalProviders/Prompts/onboarding-system-prompt.txt`
Prompt del sistema en español que instruye a la IA:
- Recibir datos del dispositivo
- Calcular umbrales óptimos según tipo, voltaje, uso, ocupantes, ubicación
- Restricciones: minPowerFactor 0-1, disconnectionThresholdMin ≥ 5
- Responder EXCLUSIVAMENTE JSON con `reasoning` + `suggestedThresholds`

#### `Profiles/Interfaces/REST/DeviceOnboardingController.cs`
Endpoint único:
- `POST /api/v1/profiles/me/device-onboarding/analyze`
- Body: `AnalyzeDeviceOnboardingResource`
- Response: `DeviceOnboardingAnalysisResource`
- Auth: requiere JWT Bearer token

#### `Profiles/Interfaces/REST/Resources/` (3 archivos)
- `AnalyzeDeviceOnboardingResource.cs`: DTO de entrada con validación
- `SuggestedThresholdsResource.cs`: DTO con 6 campos anidados
- `DeviceOnboardingAnalysisResource.cs`: DTO de respuesta compuesto

### 3.2 Archivos Modificados

#### `Profiles/Infrastructure/Interfaces.ASP.Configuration.Extensions/WebApplicationBuilderExtensions.cs`
Se agregó al final de `AddProfilesContextServices`:
```csharp
builder.Services.Configure<ProfilesAISettings>(...);
builder.Services.AddHttpClient();
builder.Services.AddScoped<IDeviceOnboardingService, DeviceOnboardingService>();
```

#### `appsettings.json`
Se agregó sección `ProfilesAI`:
```json
"ProfilesAI": {
    "ApiKey": "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",
    "ModelId": "llama-3.3-70b-versatile",
    "SystemPromptPath": "Profiles/Infrastructure/ExternalProviders/Prompts/onboarding-system-prompt.txt",
    "MaxTokens": 4096,
    "TimeoutSeconds": 30
}
```

---

## 4. Backend — Procesamiento de Thresholds (Processing BC)

### 4.1 Fix Crítico

#### `Processing/Application/Internal/EventHandlers/ConsumptionThresholdsUpdatedEventHandler.cs`
**Antes:** Solo extraía la clave `"High"` del diccionario y hardcodeaba el resto.
**Después:** Mapea correctamente las 6 claves del diccionario:
```csharp
t.TryGetValue("nominalVoltage", out var nv) ? (float)nv : 220f,
t.TryGetValue("maxConsumptionWatts", out var mcw) ? (float)mcw : 5000f,
t.TryGetValue("maxCurrentAmps", out var mca) ? (float)mca : 20f,
t.TryGetValue("minPowerFactor", out var mpf) ? (float)mpf : 0.85f,
t.TryGetValue("nominalFrequency", out var nf) ? (float)nf : 60f,
t.TryGetValue("disconnectionThresholdMin", out var dtm) ? (int)dtm : 10
```

Esto permite que el flujo `PUT /thresholds` → evento → `UpdateCustomThresholdsCommand` funcione correctamente con todos los campos.

---

## 5. Mobile — Infraestructura de Red

### `lib/core/network/api_client.dart`
- Cliente HTTP basado en Dio
- Interceptor para Authorization header
- Métodos: get, post, put, delete
- Timeouts configurables

### `lib/core/network/api_endpoints.dart`
- Constantes de URLs de la API REST
- `analyzeOnboarding`, `thresholds(profileId)`

---

## 6. Mobile — Feature de Onboarding

### 6.1 Modelos de Dominio (`lib/features/device_onboarding/domain/models/`)

| Clase | Propósito |
|-------|-----------|
| `DeviceOnboardingRequest` | Datos del formulario (deviceType, nominalVoltage, etc.) |
| `SuggestedThresholds` | 6 umbrales + `toThresholdsMap()` para PUT /thresholds |
| `DeviceOnboardingAnalysis` | reasoning + suggestedThresholds |

### 6.2 Repositorio

#### `lib/features/device_onboarding/domain/repositories/onboarding_repository.dart`
Interfaz con dos métodos:
- `analyze(DeviceOnboardingRequest)` → llama POST analyze
- `confirmThresholds(profileId, SuggestedThresholds)` → llama PUT thresholds

#### `lib/features/device_onboarding/data/repositories/onboarding_repository_impl.dart`
Implementación con ApiClient + manejo de errores DioException.

### 6.3 BLoC

| Archivo | Clase | Eventos | Estados |
|---------|-------|---------|---------|
| `onboarding_event.dart` | `OnboardingEvent` | `SubmitDeviceInfo`, `AdjustThreshold`, `ConfirmThresholds`, `ResetOnboarding` | — |
| `onboarding_state.dart` | `OnboardingState` | — | `Initial`, `Step1DeviceInfo`, `Step2Analyzing`, `Step3Confirmation`, `Completed`, `Error`, `Confirming`, `ConfirmError` |
| `onboarding_bloc.dart` | `OnboardingBloc` | Maneja todos los eventos | Gestiona transiciones de estado |

### 6.4 Pantallas (Pages)

| Archivo | Descripción |
|---------|-------------|
| `onboarding_wizard_page.dart` | Shell del wizard con step indicator + manejo de estados completado/error |
| `step1_device_info_page.dart` | Formulario: selector tipo dispositivo, voltaje, slider horas, slider ocupantes, ubicación, texto uso |
| `step2_analysis_page.dart` | Pantalla de carga mientras la IA analiza (shimmer + spinner) |
| `step3_confirmation_page.dart` | Sliders editables para cada threshold + botón confirmar |

### 6.5 Widgets

| Archivo | Descripción |
|---------|-------------|
| `device_type_selector.dart` | Grid de chips para seleccionar tipo de dispositivo (HVAC, Calentador, etc.) |
| `analysis_loading_card.dart` | Card con spinner + texto "Analizando con IA..." |
| `threshold_slider_card.dart` | Card reusable con slider + label + valor + unidad |

---

## 7. Mobile — Puntos de Entrada (Entry Points)

### Homeowner
- **`lib/core/widgets/homeowner_shell.dart`**: FAB doble en Dashboard (azul para servicio, celeste para onboarding)
- **`lib/features/dashboard/presentation/pages/dashboard_page.dart`**: QuickActions con "Añadir Dispositivo" navega al wizard
- **`lib/features/dashboard/data/repositories/dashboard_repository_impl.dart`**: QuickAction "Añadir Dispositivo" agregado a datos mockeados
- **`lib/features/dashboard/presentation/widgets/quick_actions.dart`**: `QuickActionsSection` ahora acepta `onActionTap` callback

### Company
- **`lib/features/company/presentation/screens/company_iot_page.dart`**: Botón "Añadir dispositivo" en header + FAB
- **`lib/features/company/presentation/screens/company_shell.dart`**: FAB en tab IoT (índice 2) abre wizard de onboarding

---

## 8. Dependencias Nuevas (pubspec.yaml)

```yaml
dio: ^5.4.0
```

---

## 9. Resumen de Archivos por Carpeta

### Backend (7 nuevos + 4 modificados)

```
Profiles/
├── Domain/Services/
│   └── IDeviceOnboardingService.cs                          [NUEVO]
├── Application/Internal/CommandServices/
│   └── DeviceOnboardingService.cs                           [NUEVO]
├── Infrastructure/
│   ├── ExternalProviders/
│   │   ├── ProfilesAISettings.cs                               [NUEVO]
│   │   └── Prompts/
│   │       └── onboarding-system-prompt.txt                 [NUEVO]
│   └── Interfaces.ASP.Configuration.Extensions/
│       └── WebApplicationBuilderExtensions.cs               [MODIFICADO]
├── Interfaces/REST/
│   ├── DeviceOnboardingController.cs                         [NUEVO]
│   └── Resources/
│       ├── AnalyzeDeviceOnboardingResource.cs                [NUEVO]
│       ├── DeviceOnboardingAnalysisResource.cs               [NUEVO]
│       └── SuggestedThresholdsResource.cs                    [NUEVO]

Processing/
└── Application/Internal/EventHandlers/
    └── ConsumptionThresholdsUpdatedEventHandler.cs           [MODIFICADO]

Config/
└── appsettings.json                                          [MODIFICADO]
```

### Mobile (14 nuevos + 4 modificados)

```
lib/
├── core/network/
│   ├── api_client.dart                                       [NUEVO]
│   └── api_endpoints.dart                                    [NUEVO]
├── core/widgets/
│   └── homeowner_shell.dart                                  [MODIFICADO]
├── features/
│   ├── device_onboarding/
│   │   ├── domain/models/
│   │   │   └── device_onboarding_data.dart                   [NUEVO]
│   │   ├── domain/repositories/
│   │   │   └── onboarding_repository.dart                    [NUEVO]
│   │   ├── data/repositories/
│   │   │   └── onboarding_repository_impl.dart               [NUEVO]
│   │   └── presentation/
│   │       ├── bloc/
│   │       │   ├── onboarding_bloc.dart                      [NUEVO]
│   │       │   ├── onboarding_event.dart                     [NUEVO]
│   │       │   └── onboarding_state.dart                     [NUEVO]
│   │       ├── pages/
│   │       │   ├── onboarding_wizard_page.dart               [NUEVO]
│   │       │   ├── step1_device_info_page.dart               [NUEVO]
│   │       │   ├── step2_analysis_page.dart                  [NUEVO]
│   │       │   └── step3_confirmation_page.dart              [NUEVO]
│   │       └── widgets/
│   │           ├── device_type_selector.dart                 [NUEVO]
│   │           ├── analysis_loading_card.dart                [NUEVO]
│   │           └── threshold_slider_card.dart                [NUEVO]
│   ├── company/presentation/screens/
│   │   ├── company_iot_page.dart                             [MODIFICADO]
│   │   └── company_shell.dart                                [MODIFICADO]
│   └── dashboard/
│       ├── data/repositories/
│       │   └── dashboard_repository_impl.dart                [MODIFICADO]
│       └── presentation/
│           ├── pages/dashboard_page.dart                     [MODIFICADO]
│           └── widgets/quick_actions.dart                    [MODIFICADO]

pubspec.yaml                                                   [MODIFICADO]
```

---

## 10. Pruebas Manuales

Ver documento de pruebas al final del `README.md` principal o ejectuar:

```bash
# Backend
cd electrolink-backend-api
dotnet build
dotnet run

# Probar endpoint (requiere Groq API Key en appsettings.json)
curl -X POST http://localhost:8088/api/v1/profiles/me/device-onboarding/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "deviceType": "HVAC",
    "nominalVoltage": 220,
    "dailyUsageHours": 8,
    "occupants": 4,
    "locationType": "Residential",
    "primaryUse": "Climatización de sala principal"
  }'

# Mobile
cd electrolink-mobile-app
flutter pub get
flutter run
```

---

**Fin de Etapa 2**
