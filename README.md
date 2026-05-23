# 🐾 FutureVet — IoT & Visão Computacional

Backend Python do projeto FutureVet, responsável pela camada de IoT e Visão Computacional.
Integra sensores físicos simulados no Wokwi, comunicação MQTT em nuvem, servidor HTTP REST e detecção de pets em tempo real com YOLOv8.

Desenvolvido para a disciplina **Disruptive Architectures: IoT, IoB & Generative IA** — FIAP · 1º Sprint 2025.

---

## 📋 Índice

- [Sobre o Projeto](#-sobre-o-projeto)
- [Arquitetura](#-arquitetura)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Componentes](#-componentes)
- [Circuito ESP32](#-circuito-esp32-wokwi)
- [Como Executar](#-como-executar)
- [Endpoints da API](#-endpoints-da-api)
- [Visão Computacional](#-visão-computacional)
- [Formato dos Dados](#-formato-dos-dados)
- [Integrantes](#-integrantes)

---

## 📱 Sobre o Projeto

O FutureVet resolve um problema real: tutores não conseguem monitorar a saúde do pet entre consultas veterinárias. Febre, alterações cardíacas e inatividade passam despercebidas até a próxima visita ao veterinário.

Este repositório contém a camada de backend e IoT:

- **Coleira inteligente** simulada no Wokwi com ESP32-S3 e sensores reais
- **Servidor Python** que recebe dados via MQTT e serve uma API REST para o app mobile
- **Visão computacional** com YOLOv8 para detecção e classificação de pets em câmera ou vídeo
- **Simulador de sensores** para desenvolvimento sem hardware físico

---

## 🏗️ Arquitetura

```
┌──────────────────────┐    MQTT      ┌──────────────────────┐
│   ESP32-S3 (Wokwi)   │ ──────────►  │   HiveMQ (Cloud)     │
│                      │              │   broker.hivemq.com  │
│  DS18B20  → temp     │              └──────────────────────┘
│  MAX30102 → FC       │                         │
│  MPU-6050 → ativid.  │                         │ subscribe
│  OLED     → display  │                         ▼
│  LEDs     → status   │              ┌──────────────────────┐
└──────────────────────┘              │  FutureVet_server.py │
                                      │  Python + paho-mqtt  │
┌──────────────────────┐              │  HTTP REST :8080     │
│  FutureVet_          │              └──────────────────────┘
│  visao_computacion.. │                         │
│                      │                         │ GET /api/latest
│  YOLOv8 + OpenCV     │               ┌─────────▼──────────┐
│  Detecção em tempo   │               │   App Mobile        │
│  real: cão/gato      │               │   React Native      │
│  Snapshots → JSON    │               └────────────────────┘
└──────────────────────┘
```

**Fluxo IoT:**
1. ESP32-S3 coleta leituras dos sensores a cada 5 segundos
2. Publica JSON no tópico `FutureVet/sensors/rex` via MQTT no HiveMQ
3. `FutureVet_server.py` assina o tópico e armazena em buffer
4. App mobile faz `GET /api/latest/rex` a cada 5 segundos

**Fluxo Visão Computacional:**
1. `FutureVet_visao_computacional.py` lê câmera, vídeo ou imagem
2. YOLOv8n detecta pets (cão/gato) com bounding boxes
3. Rastreador entre frames identifica comportamento (ativo, deitado, comendo)
4. Snapshots automáticos salvos em `snapshots_FutureVet/` com JSON de metadados

---

## 📂 Estrutura do Projeto

```
IOT - CHALLENGE/
│
├── FutureVet_server.py               # Servidor HTTP + Bridge MQTT → API REST
├── FutureVet_iot_sensor_simulator.py # Simulador de sensores da coleira (sem hardware)
├── FutureVet_visao_computacional.py  # Visão computacional principal (YOLOv8 + rastreador)
├── FutureVet_pet_vision.py           # Script alternativo de visão computacional
│
├── FutureVet_iot_dashboard (2).html  # Dashboard web standalone (sem servidor)
│
├── snapshots_petlink/                # Snapshots gerados pela visão computacional
│   ├── petlink_YYYYMMDD_HHMMSS_fNNN.png   # Frame com bounding boxes desenhados
│   └── petlink_YYYYMMDD_HHMMSS_fNNN.json  # Metadados da detecção
│
└── yolov8n.pt                        # Modelo YOLOv8 nano (baixado automaticamente)
```

---

## 🧩 Componentes

### `FutureVet_server.py` — Servidor principal

Bridge entre o Wokwi (MQTT) e o app mobile (HTTP REST).

- Assina `FutureVet/sensors/#` no HiveMQ em tempo real
- Fallback automático com simulador local quando o Wokwi está offline
- Buffer de até 200 leituras por pet em memória
- Pré-popula 48 leituras históricas ao iniciar (gráfico do app aparece cheio)
- Serve 4 endpoints REST com CORS habilitado

### `FutureVet_iot_sensor_simulator.py` — Simulador de sensores

Simula a coleira IoT sem precisar do Wokwi nem do hardware físico.

- Ciclo diário realista de atividade (baixa de madrugada, picos manhã/tarde)
- 3 perfis de pet: Rex (Labrador), Luna (Siamese), Bolinha (Poodle)
- Publica via MQTT **e** HTTP simultaneamente
- Gera alertas automáticos quando temperatura ou FC ultrapassam limites

### `FutureVet_visao_computacional.py` — Visão Computacional (principal)

Detecção e classificação de pets com rastreamento entre frames.

- **YOLOv8n** para detecção (baixa automaticamente se não encontrar)
- **Fallback** com detector por cor/blob quando YOLO não está disponível
- **Rastreador IoU** — mantém ID único por pet entre frames
- Inferência de comportamento: 🏃 Ativo, 💤 Deitado, 🍖 Comendo/Bebendo, 🐾 Parado
- Snapshot automático a cada 150 frames + snapshot manual com tecla `S`
- Cada snapshot gera `.png` (frame anotado) + `.json` (metadados)

### `FutureVet_pet_vision.py` — Visão Computacional (alternativo)

Versão simplificada focada em logging de eventos para integração com backend.

- Mesma base YOLOv8 + fallback
- Registra eventos no `vision_events.json`
- Mais leve, adequado para rodar em paralelo com o servidor

### `FutureVet_iot_dashboard (2).html` — Dashboard Web

Dashboard standalone que funciona sem servidor — abre direto no navegador.

- Consome a API REST do `FutureVet_server.py` via `fetch()`
- Fallback automático com dados simulados em JS quando servidor offline
- Gráfico de frequência cardíaca em tempo real
- Cards de temperatura, FC, atividade e peso com status fisiológico
- Log MQTT/HTTP dos últimos payloads recebidos
- Seletor de pet: Rex, Luna, Bolinha

---

## 🔌 Circuito ESP32 (Wokwi)

### Componentes e Pinagem

| Componente | Pino ESP32-S3 | Protocolo | Função |
|---|---|---|---|
| DS18B20 | GPIO4 + R 4.7kΩ pull-up | 1-Wire | Temperatura corporal |
| MPU-6050 | GPIO8 (SDA) / GPIO9 (SCL) | I2C | Acelerômetro → atividade |
| OLED SSD1306 | GPIO8 (SDA) / GPIO9 (SCL) | I2C compartilhado | Display local |
| LED Verde | GPIO5 + R 220Ω | Digital | Pisca a cada MQTT publicado |
| LED Vermelho | GPIO6 + R 220Ω | Digital | Liga quando há alerta de saúde |
| LED Azul | GPIO7 + R 220Ω | Digital | WiFi conectado |

### Tópicos MQTT

| Tópico | Direção | Conteúdo |
|---|---|---|
| `FutureVet/sensors/rex` | ESP32 → HiveMQ | Leituras dos sensores em JSON |
| `FutureVet/status/rex` | ESP32 → HiveMQ | Status de conexão (retain=true) |
| `FutureVet/sensors/#` | HiveMQ → Servidor | Assinatura de todos os pets |

### Bibliotecas necessárias no Wokwi

```
OneWire
DallasTemperature
Adafruit MPU6050
Adafruit Unified Sensor
Adafruit SSD1306
Adafruit GFX Library
PubSubClient
ArduinoJson
```

---

## ⚙️ Como Executar

### Pré-requisitos

- Python 3.10+
- pip

### 1. Instalar dependências

```bash
# Mínimo (apenas servidor + simulador)
pip install paho-mqtt requests

# Completo (inclui visão computacional)
pip install paho-mqtt requests opencv-python numpy ultralytics
```

---

### 2. Servidor HTTP + Bridge MQTT

```bash
python FutureVet_server.py
```

O terminal exibirá o IP da máquina na rede local:

```
══════════════════════════════════════════════════════════════
  FutureVet — Servidor HTTP + Bridge MQTT
  Local:   http://localhost:8080/api/status
  Rede:    http://192.168.1.100:8080/api/status  ← use no app
  MQTT:    broker.hivemq.com → FutureVet/sensors/#
══════════════════════════════════════════════════════════════
```

> Quando o Wokwi não está rodando, o servidor usa o simulador local automaticamente. Não é necessário nenhuma configuração extra.

---

### 3. Simulador de sensores (opcional — substitui o Wokwi)

```bash
python FutureVet_iot_sensor_simulator.py
```

Útil para testar o servidor e o dashboard sem abrir o Wokwi. Publica dados via MQTT e HTTP simultaneamente.

---

### 4. Visão Computacional

```bash
# Modo demo (sem câmera — gera frames sintéticos)
python FutureVet_visao_computacional.py --demo

# Câmera ao vivo
python FutureVet_visao_computacional.py --source 0

# Vídeo ou imagem
python FutureVet_visao_computacional.py --source video.mp4
python FutureVet_visao_computacional.py --source foto_pet.jpg --image
```

**Controles na janela:**

| Tecla | Ação |
|---|---|
| `Q` | Encerrar |
| `S` | Snapshot manual |
| `D` | Alternar demo / câmera |

---

### 5. Dashboard Web

Abra o arquivo diretamente no navegador:

```
FutureVet_iot_dashboard (2).html
```

Ou com o servidor rodando para dados reais, use qualquer navegador no mesmo computador.

---

### Ordem recomendada para demonstração completa

```bash
# Terminal 1 — servidor
python FutureVet_server.py

# Terminal 2 — Wokwi
# Abra o projeto em wokwi.com e clique ▶ Play

# Terminal 3 — visão computacional (opcional)
python FutureVet_visao_computacional.py --demo

# Navegador — dashboard
# Abra FutureVet_iot_dashboard (2).html
```

---

## 🌐 Endpoints da API

Base URL: `http://localhost:8080`

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/api/latest/{pet_id}` | Leitura mais recente do pet |
| GET | `/api/history/{pet_id}` | Histórico completo da sessão |
| GET | `/api/readings` | Últimas 20 leituras de todos os pets |
| GET | `/api/status` | Diagnóstico: MQTT, buffer, uptime |

**Pets disponíveis:** `rex`, `luna`, `bolinha`

**Exemplo:**
```bash
curl http://localhost:8080/api/latest/rex
curl http://localhost:8080/api/status
```

---

## 🎥 Visão Computacional

### Detecção

O sistema detecta **cão** e **gato** usando o modelo YOLOv8n treinado no dataset COCO. Confiança mínima padrão: **0.45**.

### Comportamentos inferidos

| Comportamento | Critério |
|---|---|
| 🏃 Ativo | Deslocamento > 30px entre frames |
| 💤 Deitado | Proporção largura/altura > 1.8 |
| 🍖 Comendo/Bebendo | Bounding box na região inferior do frame |
| 🐾 Parado | Nenhum dos anteriores |

### Snapshots

A cada 150 frames (configurável) ou ao pressionar `S`, o sistema salva:

```
snapshots_FutureVet/
├── futureVet_20260512_173811_f1050.png   # frame anotado com bounding boxes
└── futureVet_20260512_173811_f1050.json  # metadados da detecção
```

**Formato do JSON de snapshot:**
```json
{
  "timestamp": "2026-05-12T17:38:11.864358",
  "frame": 1050,
  "pets": 1,
  "deteccoes": [
    {
      "classe": "dog",
      "confianca": 0.70,
      "box": [428, 196, 965, 711]
    }
  ]
}
```

---

## 📊 Formato dos Dados IoT

**Payload publicado pelo ESP32 / simulador:**

```json
{
  "pet_id": "rex",
  "pet_name": "Rex",
  "species": "dog",
  "timestamp": "2026-05-12T20:04:52.945812+00:00",
  "sensors": {
    "temperature_celsius": 38.5,
    "heart_rate_bpm": 78,
    "activity_score": 0.078,
    "steps_last_minute": 9,
    "weight_kg": 28.3
  },
  "location": {
    "lat": -23.551211,
    "lng": -46.633430,
    "accuracy_m": 7
  },
  "battery_pct": 95,
  "health_score": 100.0,
  "alerts": [],
  "protocol": "MQTT",
  "firmware": "1.2.0"
}
```

**Alertas gerados automaticamente:**

| Alerta | Condição |
|---|---|
| `HIGH_TEMPERATURE` | Temp > baseline + 1.5°C |
| `ELEVATED_HEART_RATE` | FC > baseline × 1.5 |
| `LOW_ACTIVITY_DAYTIME` | Atividade < 5% entre 9h–17h |

---

## 👥 Integrantes

| Nome | RM | GitHub |
|---|---|---|
| Felipe Furlanetto | RM562766 | [@Felipe-Furlanetto0504](https://github.com/Felipe-Furlanetto0504) |
| Raul Rezende Iemini Aguiar | RM564002 | [@Raul-Rezende](https://github.com/Raul-Rezende) |
| João Victor Caetano Alves da Silva | RM562074 | [@joaocaetano1310](https://github.com/joaocaetano1310) |
| Ryan Victor da Silva Vetoriano | RM565667 | [@ryanvetoriano](https://github.com/ryanvetoriano) |
| João Victor Bueno Castelini da Silva | RM564115 | [@Buenozw](https://github.com/Buenozw) |

---

## 📊 Critérios de Avaliação FIAP

| Critério | Pontos | Como atendemos |
|---|---|---|
| Aplicação técnica de IoT | 50 pts | ESP32-S3 + DS18B20 + MPU-6050 + MQTT + API REST + YOLOv8 |
| Clareza da apresentação em vídeo | 20 pts | Vídeo pitch com demo funcional no YouTube |
| Organização do repositório | 20 pts | README completo, código comentado, estrutura clara |
| Disrupção / Inovação | 10 pts | Rastreamento de comportamento + snapshot vinculado ao prontuário |

---

## 📄 Licença

Projeto acadêmico desenvolvido para fins educacionais — FIAP 2025.