# Plan Detallado — Etapa 2.5: Onboarding Conversacional con IA

## Resumen

Transformar el wizard de onboarding actual (3 pasos secos: formulario → spinner → sliders) en una experiencia conversacional donde la IA **guía al usuario con preguntas y respuestas**, pero los datos estructurados se capturan con **controles UI táctiles** (chips, sliders) para mantener precisión.

La IA solo interviene donde agrega valor: **analizar contexto, explicar recomendaciones y ajustar thresholds en lenguaje natural**.

---

## 1. Flujo Nuevo

```
HOY:                                     PROPUESTO:
──────────────────────────────────────   ──────────────────────────────────────
Step 1: Formulario frío                  Paso 1: Conversación guiada
  "Tipo: HVAC [v]"                         🤖 "¿Qué dispositivo?"
  "Voltaje: 220"                           [HVAC] [Calentador] [✏️ Otro...]
  "Horas: 8"                               🤖 "¿Voltaje?" → [220V] [380V]
  "Ocupantes: 4"                           🤖 "¿Horas de uso?" → [═══│══] 8h
  "Ubicación: Residencial"                 etc.
  "Uso: Climatización"
                                         Paso 2: Análisis con typing effect
Step 2: Spinner                            🤖 "Analizando..."
  [CircularProgressIndicator]               ✓ Voltaje nominal: 220V
  "Analizando..."                           ✓ Consumo máximo: 5000W
                                            ✓ Corriente máxima: 22.5A
Step 3: Sliders fríos                      ─── Recomendación ───
  "220V [=====]"                           "Para tu HVAC en una casa con
  "5000W [=====]"                           4 personas, recomiendo..."
  etc.
                                         Paso 3: Revisión conversacional
                                          Umbrales: 220V [editar] 5000W [editar]
                                          [💬 Preguntar a la IA: "sube consumo a 6000"]
                                          [✓ Confirmar y Guardar]
```

---

## 2. Arquitectura

```
Mobile (Flutter)                                  Backend (.NET 9)
┌────────────────────────────┐                    ┌──────────────────────────────┐
│                            │                    │  Profiles Bounded Context     │
│ Paso 1: Conversación UI    │                    │                              │
│  - Preguntas + controles   │  POST /analyze     │  DeviceOnboardingController   │
│  - Sin llamadas a API      │ ──────────────────►│    ↓                          │
│                            │                    │  DeviceOnboardingService      │
│ Paso 2: Análisis + typing  │◄────────────────────│  (Groq)                      │
│  - Muestra narrative       │  response con       │    ↓                          │
│  - Línea por línea         │  narrative +        │  - reasoning                 │
│                            │  suggestedThresholds│  - narrative (NUEVO)         │
│ Paso 3: Ajuste conv.       │                    │  - suggestedThresholds        │
│  - Editar thresholds       │  POST /analyze/adjust (NUEVO)                     │
│  - 💬 Preguntar a IA       │ ──────────────────►│                              │
│  - Confirmar               │◄────────────────────│  Groq re-consulta           │
│                            │  thresholds         │  con ajuste del usuario     │
│                            │  ajustados          │                              │
└────────────────────────────┘                    └──────────────────────────────┘
```

---

## 3. Detalle del Flujo por Paso

### Paso 1: Configuración del dispositivo (conversacional)

Cada "mensaje" de la IA se muestra como una **burbuja de chat** con avatar. Debajo de cada burbuja, un **control UI táctil** permite responder sin escribir.

```
┌──────────────────────────────┐
│ 🤖 "¿Qué dispositivo         │
│    vas a configurar?"        │
│                              │
│ [HVAC] [Calentador]          │
│ [Refrigerador] [Inversor]    │
│ [✏️ Otro...]                 │
│                              │
│ 🤖 "¿Qué voltaje nominal     │
│    tiene?"                   │
│ [110V] [220V] [380V]         │
│ [✏️ Otro: ____]              │
│                              │
│ 🤖 "¿Cuántas horas al día    │
│    se usa?"                  │
│                              │
│  Poco (2h)  ═══│════  Continuo │
│        8h                     │
│                              │
│ 🤖 "¿Cuántas personas hay    │
│    en el hogar?"             │
│  [1-2] [3-4] [5+]            │
│                              │
│ 🤖 "¿Tipo de ubicación?"     │
│ [Residencial] [Comercial]    │
│ [Industrial]                 │
│                              │
│ 🤖 "¿Uso principal?"         │
│ [Climatización] [Iluminación]│
│ [Equipos] [Producción]       │
│ [✏️ Otro...]                 │
│                              │
│ [▶ Iniciar Análisis]         │
└──────────────────────────────┘
```

**Comportamiento:**
- Cada pregunta aparece con un leve delay (300ms) simulando que la IA "piensa"
- No hay llamadas a API durante este paso
- Cuando todos los campos están completos, se habilita "▶ Iniciar Análisis"
- Si el usuario toca "✏️ Otro", se expande un TextField

### Paso 2: Análisis con IA (typing effect)

```
┌──────────────────────────────┐
│ 🤖 Analizando configuración  │
│    para HVAC...              │
│                              │
│  ✓ Voltaje nominal: 220V     │ ← aparece línea por línea
│  ✓ Consumo máximo: 5000W     │    con delay progresivo
│  ✓ Corriente: 22.5A          │
│  ✓ Factor de potencia: 0.90  │
│  ✓ Frecuencia: 60Hz          │
│  ✓ Desconexión: 15 min       │
│                              │
│ ─────────────────────────── │
│ "Para tu HVAC en una casa    │
│  con 4 personas, recomiendo  │ ← narrative con typing
│  estos umbrales. El consumo  │    character-by-character
│  principal será en horario   │
│  diurno durante verano."     │
│ ─────────────────────────── │
│                              │
│ [▶ Ver y Ajustar Thresholds] │
└──────────────────────────────┘
```

### Paso 3: Revisión y Ajuste Conversacional

```
┌──────────────────────────────┐
│ 🤖 "¿Quieres ajustar algo    │
│    o confirmo los valores?"  │
│                              │
│ ┌────────────────────────┐   │
│ │ 220V     [editar]  ✔️  │   │ ← chips con tap
│ │ 5000W    [editar]  ✔️  │   │
│ │ 22.5A    [editar]  ✔️  │   │
│ │ 0.90     [editar]  ✔️  │   │
│ │ 60Hz     [editar]  ✔️  │   │
│ │ 15min    [editar]  ✔️  │   │
│ └────────────────────────┘   │
│                              │
│ ┌──────────────────────────┐ │
│ │ 💬 Preguntar a la IA...  │ │ ← input para lenguaje natural
│ └──────────────────────────┘ │
│                              │
│ [✓ Confirmar y Guardar]      │
└──────────────────────────────┘
```

**"💬 Preguntar a la IA":**
- Usuario escribe: "Sube el consumo máximo a 6000W"
- Se llama `POST /analyze/adjust` con `{analysisId, userMessage}`
- Backend re-consulta a Groq con contexto completo + ajuste solicitado
- Se devuelven thresholds actualizados + nueva narrative
- La burbuja de la IA se actualiza: "Listo, ajusté el consumo a 6000W"

---

## 4. Backend — Cambios

### Archivos a modificar

| Archivo | Cambio | Estado |
|---------|--------|--------|
| `Profiles/Domain/Services/IDeviceOnboardingService.cs` | Agregar `Narrative` a `DeviceOnboardingAnalysis`. Agregar método `AdjustAnalysisAsync(analysisId, userMessage)` | ✅ |
| `Profiles/Application/Internal/CommandServices/DeviceOnboardingService.cs` | Modificar prompt + implementar `AdjustAnalysisAsync` + `ConcurrentDictionary` para almacenar sesiones | ✅ |
| `Profiles/Infrastructure/ExternalProviders/Prompts/onboarding-system-prompt.txt` | Instruir que devuelva `narrative` además de `reasoning` y `suggestedThresholds` | ✅ |
| `Profiles/Interfaces/REST/DeviceOnboardingController.cs` | Agregar endpoint `POST /analyze/adjust` | ✅ |

### Archivos nuevos

| Archivo | Propósito | Estado |
|---------|-----------|--------|
| `Profiles/Interfaces/REST/Resources/AdjustThresholdsResource.cs` | Request DTO: `{analysisId, userMessage}` | ✅ |

### IDeviceOnboardingService.cs (modificado)

```csharp
public record DeviceOnboardingAnalysis(
    string Reasoning,
    string Narrative,  // NUEVO
    SuggestedThresholds SuggestedThresholds
);

public interface IDeviceOnboardingService
{
    Task<DeviceOnboardingAnalysis> AnalyzeAsync(
        AnalyzeDeviceOnboardingRequest request,
        CancellationToken cancellationToken = default);

    Task<DeviceOnboardingAnalysis> AdjustAnalysisAsync(  // NUEVO
        string analysisId,
        string userMessage,
        CancellationToken cancellationToken = default);
}
```

### DeviceOnboardingService.cs — Lógica de AdjustAnalysisAsync

```csharp
private static readonly ConcurrentDictionary<string, AnalyzeDeviceOnboardingRequest> _sessions = new();

// En AnalyzeAsync, guardar sesión antes de retornar:
var analysisId = Guid.NewGuid().ToString();
_sessions[analysisId] = request;
// Incluir analysisId en el response

// AdjustAnalysisAsync:
public async Task<DeviceOnboardingAnalysis> AdjustAnalysisAsync(
    string analysisId, string userMessage, CancellationToken ct = default)
{
    if (!_sessions.TryGetValue(analysisId, out var request))
        throw new KeyNotFoundException("Sesión de análisis no encontrada");

    var prompt = await File.ReadAllTextAsync(settings.Value.SystemPromptPath, ct);
    var fullContext = prompt + $@"

DATOS ORIGINALES: {JsonSerializer.Serialize(request, JsonOptions)}

EL USUARIO PIDE: {userMessage}

Ajusta los thresholds según lo solicitado. Responde EXCLUSIVAMENTE con JSON.";
    
    // Llamar a Groq (misma lógica que AnalyzeAsync)
    var analysis = await CallGroqAsync(fullContext, ct);
    return analysis;
}
```

### Prompt modificado

```
Eres un experto electricista que ayuda a configurar dispositivos IoT de monitoreo eléctrico.

DATOS DEL DISPOSITIVO:
{tipo, voltaje, horas, ocupantes, ubicación, uso principal}

Responde EXCLUSIVAMENTE con este JSON sin markdown ni texto adicional:
{
  "reasoning": "Explicación técnica breve (1-2 líneas) para el sistema",
  "narrative": "Explicación en lenguaje natural para el USUARIO, como si fueras un técnico explicando cara a cara. Menciona el tipo de dispositivo y el contexto del hogar. Justifica los valores de forma amigable. Máximo 5 líneas.",
  "suggestedThresholds": {
    "nominalVoltage": float,
    "maxConsumptionWatts": float,
    "maxCurrentAmps": float,
    "minPowerFactor": float,
    "nominalFrequency": float,
    "disconnectionThresholdMin": int
  }
}

REGLAS:
- narrative: en español, tono amigable y profesional, dirigido al dueño de casa
- minPowerFactor: 0.0 a 1.0
- disconnectionThresholdMin: mínimo 5
- No incluyas nada antes ni después del JSON
```

---

## 5. Mobile — Cambios

### Archivos a modificar

| Archivo | Cambio | Estado |
|---------|--------|--------|
| `domain/models/device_onboarding_data.dart` | Agregar `narrative` + `analysisId` a `DeviceOnboardingAnalysis` | ✅ |
| `domain/repositories/onboarding_repository.dart` | Agregar `adjustAnalysis(String analysisId, String userMessage)` | ✅ |
| `data/repositories/onboarding_repository_impl.dart` | Implementar `adjustAnalysis` → `POST /analyze/adjust` | ✅ |
| `core/network/api_endpoints.dart` | Agregar `adjustAnalysis` endpoint | ✅ |
| `presentation/bloc/onboarding_event.dart` | Agregar eventos `AdjustWithAI`, `NarrativeDisplayed` | ✅ |
| `presentation/bloc/onboarding_state.dart` | Agregar `step1Conversational` flag, `narrative` | ✅ |
| `presentation/bloc/onboarding_bloc.dart` | Handler para `AdjustWithAI` | ✅ |
| `presentation/pages/onboarding_wizard_page.dart` | Mapear nuevos estados | ✅ |
| `presentation/pages/step1_device_info_page.dart` | Rediseño conversacional completo | ✅ |
| `presentation/pages/step2_analysis_page.dart` | Rediseño con typing effect + narrative | ✅ |
| `presentation/pages/step3_confirmation_page.dart` | Agregar input IA + chips editables | ✅ |
| `presentation/widgets/device_type_selector.dart` | Agregar opción "✏️ Otro" | ✅ |

### Archivos nuevos

| Archivo | Propósito | Estado |
|---------|-----------|--------|
| `presentation/widgets/chat_bubble.dart` | Burbuja de chat con avatar IA + texto | ✅ |
| `presentation/widgets/ia_input_bar.dart` | Input bar "💬 Preguntar a la IA" | ✅ |

### Modelo (device_onboarding_data.dart)

```dart
class DeviceOnboardingAnalysis extends Equatable {
  final String reasoning;
  final String narrative;  // NUEVO
  final SuggestedThresholds suggestedThresholds;
  final String? analysisId;  // NUEVO

  const DeviceOnboardingAnalysis({
    required this.reasoning,
    this.narrative = '',
    required this.suggestedThresholds,
    this.analysisId,
  });

  factory DeviceOnboardingAnalysis.fromJson(Map<String, dynamic> json) {
    return DeviceOnboardingAnalysis(
      reasoning: json['reasoning'] as String? ?? '',
      narrative: json['narrative'] as String? ?? '',
      suggestedThresholds: SuggestedThresholds.fromJson(
        json['suggestedThresholds'] as Map<String, dynamic>,
      ),
      analysisId: json['analysisId'] as String?,
    );
  }
}
```

### Eventos (onboarding_event.dart)

```dart
class AdjustWithAI extends OnboardingEvent {
  final String analysisId;
  final String userMessage;
  const AdjustWithAI({required this.analysisId, required this.userMessage});
  @override
  List<Object?> get props => [analysisId, userMessage];
}
```

Estados (`onboarding_state.dart`):

```dart
class OnboardingStep3Confirmation extends OnboardingState {
  final DeviceOnboardingAnalysis analysis;
  final bool isAdjusting;  // NUEVO
  const OnboardingStep3Confirmation(this.analysis, {this.isAdjusting = false});
}
```

---

## 6. Resumen de Archivos

| Capa | Nuevos | Modificados | Total |
|------|--------|-------------|-------|
| Backend (.NET) | 1 | 4 | 5 |
| Mobile (Flutter) | 2 | 11 | 13 |
| Documentación | 1 | — | 1 |
| **Total** | **4** | **15** | **19** |

---

## 7. Orden de Implementación

1. Backend: prompt + narrative + endpoint /adjust
2. Mobile: modelos + API + bloc
3. Mobile: widgets conversacionales (ChatBubble, IaInputBar)
4. Mobile: rediseño Step 1
5. Mobile: rediseño Step 2 + 3
6. Verificación: flutter analyze + build
