# Plan Detallado - Etapa 1: Estructuración POO, Sensores en Paralelo y Simulación Wokwi

Este documento detalla a nivel conceptual la arquitectura y las tareas de la **Etapa 1** del firmware ESP32 (`ElectroLinkIoT`). Incluye el diseño modular orientado a objetos, la instrumentación dual de sensores, la lógica de protección preventiva local, la configuración completa del simulador Wokwi, y los ajustes realizados en la Edge API para soportar el payload dual de sensores.

---

## 1. Estructura Final de Archivos del Firmware

```text
ElectroLinkIoT/
│
├── ElectroLinkIoT.ino          # Punto de entrada. Loop polimórfico con lectura dual y corte preventivo. Incluye auto-recovery del relé y protección OLED
├── Config.h                    # Constantes globales, OFFLINE_DEMO_MODE y variables extern de umbrales
├── Pins.h                      # Asignación física de GPIOs (sincronizados con diagram.json)
│
├── Sensor.h                    # [NUEVO] Interfaz abstracta base para todos los sensores
├── Acs712Sensor.h              # [MODIFICADO] Hereda de Sensor. Lectura analógica por efecto Hall
├── Ina219Sensor.h              # [NUEVO] Hereda de Sensor. Lectura digital I2C de alta precisión (o simulada por potenciómetro en Wokwi)
│
├── Actuator.h                  # [NUEVO] Interfaz abstracta base para todos los actuadores
├── RelayActuator.h             # [MODIFICADO] Hereda de Actuator. Control del relé de corte
├── BuzzerActuator.h            # [MODIFICADO] Hereda de Actuator. Control del zumbador acústico
│
├── LedIndicators.h             # Control de terna de LEDs (verde/amarillo/rojo). Sin cambios
├── OledDisplay.h               # Pantalla OLED I2C 128x64. Sin cambios
├── AlertService.h              # [MODIFICADO] Evaluación de alertas con umbrales dinámicos
│
├── WiFiConnectivityDriver.h    # [NUEVO] Gestión de conexión WiFi con auto-reconexión
├── HttpEdgeGatewayClient.h     # [NUEVO] Cliente HTTP con payload dual y parseo de umbrales. Reemplaza a EdgeApiClient.h
│
├── WOKWI_README.md             # [NUEVO] Documentación completa para simulación en Wokwi
├── diagram.json                # [NUEVO] Circuito completo Wokwi con resistencias limitadoras en LEDs
└── libraries.txt               # [NUEVO] Dependencias de librerías para Wokwi

# Archivo legacy eliminado:
# EdgeApiClient.h               # [ELIMINADO] Reemplazado por HttpEdgeGatewayClient.h
```

---

## 2. Arquitectura de Clases (POO C++)

El firmware se diseñó bajo principios de cohesión y abstracción. Cada periférico y servicio tiene su propia clase con responsabilidad única.

### A. Jerarquía de Sensores

* **`Sensor` (Clase Base Abstracta):** Define la interfaz común con métodos virtuales puros `begin()`, `readCurrent()` y `getName()`. Toda clase de sensor debe heredarla.
* **`Acs712Sensor` (Clase Hija):** Lee corriente de forma analógica a través del ADC del ESP32. Incorpora auto-calibración del punto de cero en vacío para eliminar el offset de voltaje. Actúa como sensor de respaldo ante fallas del bus I2C.
* **`Ina219Sensor` (Clase Hija):** Lee corriente, voltaje de bus y potencia a través del protocolo I2C en la dirección `0x40`. Es el sensor **primario de seguridad** por su mayor precisión y capacidad de reportar voltaje real. Si no se detecta al iniciar, el sistema continúa usando solo el ACS712.

### B. Jerarquía de Actuadores

* **`Actuator` (Clase Base Abstracta):** Define la interfaz con métodos virtuales puros `begin()`, `turnOn()`, `turnOff()` e `isOn()`. Permite tratar cualquier actuador de forma polimórfica.
* **`RelayActuator` (Clase Hija):** Controla el relé de corte eléctrico. Soporta lógica activa alta o baja mediante la constante `RELAY_ACTIVE_HIGH`. Mantiene retrocompatibilidad con los métodos `on()`, `off()` y `set()`.
* **`BuzzerActuator` (Clase Hija):** Activa o silencia el zumbador acústico. Se dispara cuando el sistema entra en estado `PELIGRO`.

### C. Controladores de Conectividad e Infraestructura

* **`WiFiConnectivityDriver`:** Encapsula toda la lógica de conexión y reconexión WiFi. El archivo principal `.ino` nunca toca la librería `WiFi.h` directamente. Implementa reintento automático cada 30 segundos si se pierde la conexión.
* **`HttpEdgeGatewayClient`:** Reemplaza al antiguo `EdgeApiClient`. Serializa un payload JSON con las lecturas de **ambos sensores** simultáneamente y parsea la respuesta del Edge para actualizar en caliente las variables globales de umbrales (`currentNormalLimit` y `currentAlertLimit`).
* **`AlertService`:** Clase utilitaria que compara la corriente máxima medida contra los umbrales dinámicos globales. Retorna el estado `NORMAL`, `ALERTA` o `PELIGRO`.
* **`LedIndicators`:** Maneja la terna de LEDs de estado de forma atómica (solo un LED activo a la vez).
* **`OledDisplay`:** Renderiza las métricas de corriente, potencia y estado del relé en la pantalla OLED I2C.

---

## 3. Propósito y Rol de Cada Sensor

| Característica | ACS712 (Analógico) | INA219 (Digital I2C) |
|---|---|---|
| Principio de medición | Efecto Hall en señal analógica | Resistencia shunt + comunicación I2C |
| Precisión | Media (ruidosa a frecuencias bajas) | Alta (resolución 12-bit) |
| Lectura de voltaje | No | Sí (voltaje de bus) |
| Lectura de potencia | Calculada externamente | Integrada en el chip |
| Rol en el sistema | Sensor de **respaldo** analógico | Sensor **primario** de seguridad |
| Falla tolerante | Usado si INA219 no se inicializa | Si falla, retorna 0.0 (sistema continúa) |

**Lógica de fusión:** El firmware toma el **valor máximo** entre ambas lecturas de corriente para evaluar el estado de alerta. Esto garantiza la mayor seguridad: si alguno de los dos detecta sobrecorriente, el sistema reacciona.

---

## 4. Mecanismo de Protección Preventiva Local

> [!IMPORTANT]
> El corte del relé en estado `PELIGRO` es **local e inmediato**. No espera confirmación del servidor Edge ni de ningún servicio externo. Funciona incluso sin conexión a internet.

Flujo de decisión en cada iteración del `loop()`:
1. Se leen `corrienteAcs` y `corrienteIna` en paralelo.
2. Se calcula `corrienteMaxima = max(corrienteAcs, corrienteIna)`.
3. `AlertService::evaluate(corrienteMaxima)` retorna el estado.
4. Si el estado es `PELIGRO` → `relay.turnOff()` + `buzzer.turnOn()` + `leds.danger()` en el mismo ciclo de CPU.
5. El log se imprime por Serial y, si hay red, se reporta al Edge en el siguiente intervalo.

---

## 5. Modo Demostración Offline (`OFFLINE_DEMO_MODE`)

La directiva en `Config.h` permite compilar dos modos distintos:

| `OFFLINE_DEMO_MODE` | Comportamiento |
|---|---|
| `false` (por defecto) | Modo Wokwi. Conecta WiFi, sincroniza umbrales con el Edge Gateway dinámicamente. |
| `true` | Modo expo física. No intenta conectar WiFi. Usa los valores `DEFAULT_NORMAL_LIMIT` y `DEFAULT_ALERT_LIMIT` definidos en `Config.h` como umbrales fijos. |

---

## 6. Configuración del Simulador Wokwi

### A. `diagram.json` — Circuito Completo

Describe todos los componentes físicos y sus conexiones:

| Componente | Tipo en Wokwi | ID | Pines relevantes |
|---|---|---|---|---|
| ESP32 DevKit C V4 | `board-esp32-devkit-c-v4` | `esp` | TX→SerialMonitor, RX→SerialMonitor |
| OLED SSD1306 I2C | `board-ssd1306` | `oled1` | SDA→21, SCL→22, VCC→3V3, GND→GND.3 |
| Potenciómetro ACS712 | `wokwi-potentiometer` | `pot1` | SIG→34, VCC→3V3, GND→GND.1 |
| Potenciómetro INA219 | `wokwi-potentiometer` | `pot2` | SIG→35, VCC→3V3, GND→GND.1 |
| Módulo Relé | `wokwi-relay-module` | `relay1` | IN→13, VCC→5V, GND→GND.1 |
| Zumbador | `wokwi-buzzer` | `bz1` | +→14 (por 1→GND.2) |
| LED Verde (NORMAL) | `wokwi-led` | `led1` | A→GPIO 25 *(vía resistor 220Ω)*, C→GND.1 |
| LED Amarillo (ALERTA) | `wokwi-led` | `led2` | A→GPIO 26 *(vía resistor 220Ω)*, C→GND.1 |
| LED Rojo (PELIGRO) | `wokwi-led` | `led3` | A→GPIO 27 *(vía resistor 220Ω)*, C→GND.1 |

> [!NOTE]
> El INA219 **no existe como componente nativo en Wokwi**. Se simula con un potenciómetro en el pin 35.
> Al pasar al hardware físico, cambiar `WOKWI_SIMULATION false` en `Config.h` — el sensor I2C real se usará automáticamente.

> [!NOTE]
> El INA219 y el OLED comparten el bus I2C (pines 21 y 22) sin conflicto porque usan direcciones distintas (`0x3C` vs `0x40`).

### C. Fixes Aplicados Durante la Revisión del Código

Durante el análisis del código se detectaron y corrigieron los siguientes problemas:

| # | Problema | Fix | Archivos afectados |
|---|---|---|---|
| 1 | **OLED failure era FATAL** — Si la pantalla no se detectaba, el ESP32 entraba en `while(true)` eterno | Cambiado a warning no bloqueante con flag `oledAvailable`. El sistema opera sin pantalla | `ElectroLinkIoT.ino` |
| 2 | **Payload mismatch Edge API** — El firmware enviaba `currentAcs`/`currentIna` pero el Edge esperaba `current` (singular) | Actualizado `ESP32ReadingPayload` a dual + migración de DB de `current` a `current_acs`/`current_ina` | `routers/readings.py`, `database.py`, `simulate_device.py`, `services/sync_worker.py` |
| 3 | **Edge API no retornaba thresholds** — El `HttpEdgeGatewayClient` parseaba `thresholds` pero el Edge nunca los enviaba | Agregados thresholds por defecto (`normalLimit: 0.20`, `alertLimit: 0.60`) en la respuesta del Edge | `routers/readings.py` |
| 4 | **Sin auto-recovery del relé** — Tras un DANGER el relé quedaba apagado para siempre | Auto-recuperación: al volver a estado NORMAL, el relé se re-activa automáticamente | `ElectroLinkIoT.ino` |
| 5 | **Sin `analogReadResolution` explícito** — El ADC usaba resolución por defecto | Agregado `analogReadResolution(12)` en setup() | `ElectroLinkIoT.ino` |
| 6 | `PIN_INA_SIM` en `Config.h` en vez de `Pins.h` | Movido a `Pins.h` para consistencia | `Config.h`, `Pins.h` |
| 7 | `EdgeApiClient.h` legacy aún presente | Eliminado (reemplazado por `HttpEdgeGatewayClient.h`) | `EdgeApiClient.h` |
| 8 | `diagram.json` sin resistencias limitadoras en LEDs | Agregadas 3 resistencias de 220Ω en serie con cada LED | `diagram.json` |
| 9 | Pines del `diagram.json` no coincidían con `Pins.h` | Sincronizados: relé→13, buzzer→14, LEDs→25/26/27. El `Pins.h` ahora refleja el cableado real del diagrama | `Pins.h`, `diagram.json` |

### D. Cambios en la Edge API para Soportar Etapa 1

La Edge API (`electrolink-edge-api`) recibió los siguientes cambios para alinearse con el firmware dual:

| Archivo | Cambio |
|---|---|
| `routers/readings.py` | Modelo `ESP32ReadingPayload` acepta `currentAcs` y `currentIna`. Respuesta incluye `thresholds` con límites por defecto |
| `database.py` | Columna `current` reemplazada por `current_acs` + `current_ina`. Migración automática con `_migrate_db()` |
| `services/sync_worker.py` | Sincronización con cloud backend usa `current_acs` + `current_ina` |
| `simulate_device.py` | Simulador Python actualizado a payload dual |

### E. Documentación Generada

| Archivo | Contenido |
|---|---|
| `WOKWI_README.md` | Guía completa de simulación: requisitos, conexiones, modos de operación, tests, integración con Edge API y troubleshooting |

### B. `libraries.txt` — Dependencias de Wokwi

Wokwi descarga automáticamente las librerías listadas en este archivo al compilar el proyecto:

```
Adafruit INA219       ← Comunicación I2C con el sensor de corriente/voltaje
Adafruit BusIO        ← Dependencia interna requerida por Adafruit INA219
ArduinoJson           ← Serialización y parseo de JSON para la Edge API
Adafruit SSD1306      ← Driver de la pantalla OLED
Adafruit GFX Library  ← Dependencia gráfica de SSD1306
```

---

## 7. Plan de Pruebas y Validación

### A. Pruebas del Dispositivo en Wokwi (Firmware Aislado)

1. **Verificar inicialización:** En la consola Serial, confirmar que ambos sensores impriman sus mensajes de inicio (`[ACS712] Zero voltage calibrado` e `[INA219] Sensor inicializado`).
2. **Simular corriente normal:** Potenciómetro al mínimo → verificar LED verde encendido, buzzer apagado, relé ON.
3. **Simular alerta media:** Mover el potenciómetro hasta superar `DEFAULT_NORMAL_LIMIT` → verificar que LED amarillo se encienda y buzzer permanezca apagado.
4. **Simular peligro:** Llevar el potenciómetro al máximo, superando `DEFAULT_ALERT_LIMIT` → verificar corte **inmediato** del relé, encendido de buzzer y LED rojo, todo en el mismo ciclo sin esperar red.
5. **Probar Modo Demo:** Cambiar `OFFLINE_DEMO_MODE` a `true` en `Config.h`, recompilar → verificar que el dispositivo **no** intente conectar WiFi y opere con los umbrales estáticos.

### B. Prueba de Integración del Sistema Completo (con Edge API)

1. Configurar `OFFLINE_DEMO_MODE false` y actualizar `EDGE_API_URL` en `Config.h` con la URL de ngrok.
2. Lanzar la Edge API localmente y ejecutar `ngrok http 3000`.
3. Correr la simulación → verificar en los logs del Edge que los payloads contienen tanto `currentAcs` como `currentIna`.
4. Si el Edge tiene umbrales configurados desde el backend, verificar que en la respuesta llegue el objeto `"thresholds"` y que el Serial del ESP32 imprima `[Edge] Umbrales actualizados`.
5. Modificar umbrales desde la app móvil → esperar la sincronización del Edge → verificar que el ESP32 recibe y aplica los nuevos límites en la siguiente lectura periódica.

---

## 8. Checklist de Tareas — Etapa 1

### Implementación del Firmware ESP32
- [x] Crear `Sensor.h` (interfaz abstracta base de sensores)
- [x] Crear `Actuator.h` (interfaz abstracta base de actuadores)
- [x] Refactorizar `Acs712Sensor.h` para heredar de `Sensor`
- [x] Crear `Ina219Sensor.h` (sensor digital I2C nuevo, con modo simulación por potenciómetro)
- [x] Refactorizar `RelayActuator.h` para heredar de `Actuator`
- [x] Refactorizar `BuzzerActuator.h` para heredar de `Actuator`
- [x] Crear `WiFiConnectivityDriver.h` (gestión WiFi desacoplada)
- [x] Crear `HttpEdgeGatewayClient.h` (payload dual + parseo de umbrales)
- [x] Actualizar `Config.h` con `OFFLINE_DEMO_MODE`, `WOKWI_SIMULATION` y variables `extern`
- [x] Actualizar `AlertService.h` para usar umbrales dinámicos globales
- [x] Reescribir `ElectroLinkIoT.ino` con arquitectura polimórfica, corte preventivo y auto-recovery

### Configuración Wokwi
- [x] Crear `libraries.txt` con todas las dependencias de Wokwi
- [x] Crear `diagram.json` con el circuito completo (ESP32 + OLED + INA219 + ACS + Relé + Buzzer + LEDs + resistencias)
- [x] Sincronizar `Pins.h` con el cableado real del `diagram.json`
- [x] Documentación de simulación: `WOKWI_README.md`

### Edge API
- [x] Actualizar modelo `ESP32ReadingPayload` a dual (`currentAcs` + `currentIna`)
- [x] Responder con `thresholds` en el POST de lecturas
- [x] Migrar DB: columna `current` → `current_acs` + `current_ina`
- [x] Actualizar `SyncWorker` con los nuevos campos
- [x] Actualizar `simulate_device.py` con payload dual

### Fixes de código
- [x] OLED failure ya no es FATAL (continúa sin pantalla)
- [x] Auto-recovery del relé al volver a NORMAL
- [x] `analogReadResolution(12)` explícito en setup
- [x] `PIN_INA_SIM` movido a `Pins.h`
- [x] `EdgeApiClient.h` legacy eliminado

### Validación
- [x] **Compilación exitosa con `arduino-cli`** (ESP32 Dev Module, 83% flash, 15% RAM, 0 errores)
- [x] **POST /api/electrolink/readings** acepta payload dual y retorna thresholds (Status 200)
- [x] **Migración DB** verifica columnas correctas en SQLite
- [ ] **Ejecutar pruebas de simulación de alertas en Wokwi** (pasos 1–5 de sección 7A)
- [ ] **Ejecutar prueba de integración con Edge API + ngrok** (sección 7B)
- [ ] **Probar demo offline** (`OFFLINE_DEMO_MODE=true`)
