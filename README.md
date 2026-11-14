# 🧠 AGENT SATOSHI — Margin Trader BTC/USDT (ADK + Binance API)

> Agente de Inteligência Artificial autônomo para **operações de trading MARGIN 5x em BTC/USDT**,  
> desenvolvido sobre o **Google ADK 1.16.0**, com lógica determinística, integração nativa com a **Binance API**,  
> e pipeline cognitiva de mercado baseada em **retrações de Fibonacci 4H**.

---

## ⚙️ Visão Geral

O **AGENTE_SATOSHI** é um sistema autônomo de análise e execução de operações no mercado global de criptomoedas, projetado para **tomada de decisão sem emoção**.  
Seu núcleo de raciocínio foi desenvolvido em **Python + ADK (Agent Development Kit)**, executando loops cognitivos para monitorar o BTC/USDT, analisar zonas Fibonacci, calcular ROI e executar entradas e saídas seguras.

O agente é composto por dois módulos principais:

| Módulo | Descrição |
|--------|------------|
| `app/agent.py` | Núcleo de execução autônomo, responsável por analisar, decidir e executar ordens com base em ciclos técnicos. |
| `adk web` | Interface conversacional (chat) do Satoshi, executada via ADK Web UI, onde o usuário pode consultar análises, PnL, ROI e efetuar vendas parciais com confirmação. |

---

## 🧩 Arquitetura do Projeto

```
AGENT_CRIPTO2/
├── app/
│   ├── agent.py                # Núcleo do agente Satoshi (execução autônoma e raciocínio técnico)
│   ├── prompt.py               # Prompt central (regras, personalidade e conduta do agente)
│   ├── __init__.py
│   └── tools/
│       ├── get_market_data.py  # Captura preço e contexto de mercado BTCUSDT
│       ├── get_fib_levels.py   # Calcula retrações de Fibonacci (4H, 300 candles)
│       ├── sell_market.py      # Executa vendas parciais (1% a 40% do valor alavancado)
│       ├── get_accounts_status.py # Retorna saldo, alavancagem e PnL
│       └── __init__.py
├── logs/
│   ├── satoshi_log.jsonl       # Log estruturado por ciclo de execução
│   ├── pnl_history.json        # Histórico de PnL e ROI (30 dias)
│   └── state.json              # Estado persistente (última zona e ciclo)
├── tests/
│   ├── test_satoshi.py         # Testes unitários e integrados (pytest + asyncio)
│   └── __init__.py
├── .env                        # Variáveis de ambiente
├── requirements.txt
└── README.md
```

---

## 🔑 Configuração do Ambiente

### 1. Instalar dependências

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente `.env`

```bash
BNB_API_KEY=SEU_API_KEY_BINANCE
BNB_API_SECRET=SEU_API_SECRET_BINANCE
TRADING_MODE=dry              # dry | real
COOLDOWN_CYCLES=10
BUY_PERCENT=0.4               # 40% do saldo em USDT
LEVERAGE=5                    # Alavancagem padrão
USE_REASONING=on
GOOGLE_API_KEY=SEU_API_KEY_GEMINI
LOG_MAX_BYTES=5242880       # Rotação do log principal em 5 MiB
LOG_BACKUP_COUNT=3          # Mantém até 3 arquivos rotacionados
```

O loop autônomo não carrega o ADK conversacional. Em uma VM com 1 GB de RAM, mantenha apenas os serviços necessários em execução e não inicie o PostgreSQL se a aplicação não estiver usando-o. O log JSONL é rotacionado por tamanho; os arquivos `state.json` e `pnl_history.json` permanecem no diretório `logs/` local.

---

## 🚀 Execução Autônoma (Módulo Técnico)

### ▶️ Rodar o agente autônomo

O núcleo de execução é o **módulo `app/agent.py`**, que analisa o mercado e executa automaticamente compras dentro da zona Fibonacci.

```bash
python -m app.agent
```

Durante a execução, o agente irá:

1. Obter dados do mercado via Binance API.  
2. Calcular níveis de Fibonacci 0.236, 0.382, 0.5, 0.618.  
3. Identificar zonas de entrada seguras (0.382 ±1%).  
4. Executar ordens de compra **apenas se** o preço estiver dentro da zona e não houver cooldown ativo.  
5. Registrar logs estruturados com PnL, ROI e histórico de entradas.

Exemplo de log no terminal:

```
🚀 Satoshi Agent (MARGIN 5x) iniciado — Modo: 💻 Dry-Run

⏱️ Ciclo 2 iniciado em 2025-11-02 20:05:51
[📈] BTCUSDT → Preço: 110207.39
[🔢] Nível 0.382: 111244.26 (zona: 110131.82 — 111244.26)
[💠] Total alavancado: $35.36
[💰] USDT_free: 3.50 | BTC_free: 0.00028
🚫 Cooldown ativo: 9 ciclos restantes.
```

---

## 💬 Execução Conversacional (ADK Web)

### ▶️ Iniciar o ambiente ADK

O ADK provê uma interface de chat interativa com o agente Satoshi:

```bash
adk web --port 8085
```

Acesse no navegador:

> http://127.0.0.1:8085

### O que o Satoshi pode fazer via chat:

- 📊 Mostrar níveis de Fibonacci e zonas de entrada  
- 💵 Exibir saldo e valor alavancado  
- 📈 Calcular ROI e variação de 30 dias  
- 💰 Executar **vendas parciais entre 1% e 40%** do valor alavancado (com confirmação)  
- 🧠 Explicar o racional técnico da estratégia  

### O que o Satoshi **NÃO faz via chat**:

- ❌ Não executa **compras manuais**
- ❌ Não responde assuntos fora do mercado cripto
- ❌ Não realiza **vendas acima de 40%** (essas devem ser feitas manualmente via dashboard do Oraicle)
- ❌ Não especula sobre o futuro — apenas analisa dados reais e técnicos

---

## 🧱 Lógica de Trading

### Estratégia Fibonacci 4H

| Nível | Significado | Ação |
|-------|--------------|------|
| 0.236 | Correção rasa | Apenas observação |
| 0.382 | **Zona de ouro (entrada potencial)** | Compra automatizada |
| 0.5   | Reversão intermediária | Aguardar confirmação |
| 0.618 | Zona de sobrecompra | Reavaliação ou saída |

### Ciclo Cognitivo

Cada ciclo (loop) é executado a cada **120 segundos** (configurável).

1. Lê preços e volatilidade.  
2. Recalcula retrações Fibonacci.  
3. Verifica ROI consolidado.  
4. Decide entre **"ENTRY_READY"** ou **"NO_ENTRY"**.  
5. Loga todas as decisões no `logs/satoshi_log.jsonl`.

---

## 🔍 Testes Automatizados

Executar todos os testes:

```bash
pytest -v --maxfail=1 --disable-warnings
```

Resultado esperado:

```
6 passed, 3 warnings in 4.08s
```

Os testes validam:
- Cálculo Fibonacci
- Leitura de saldos margin
- Simulação de ordens
- ROI / PnL 30 dias
- Execução assíncrona com asyncio

---

## 📊 Monitoramento de Logs

| Arquivo | Função |
|----------|---------|
| `logs/satoshi_log.jsonl` | Histórico detalhado de cada ciclo |
| `logs/pnl_history.json` | Evolução do colateral (30 dias) |
| `logs/state.json` | Última zona e ciclo de execução |

---

## ⚖️ Conduta e Ética Operacional

O agente Satoshi é projetado para operar **sem emoção**, **sem especulação** e **sem intervenção humana**.  
Ele segue uma conduta técnica e racional definida em `prompt.py`:

- Não realiza compras manuais (apenas o módulo autônomo decide).  
- Vendas limitadas entre **1% e 40%** do valor alavancado.  
- Sempre confirma antes de executar.  
- Rejeita assuntos fora do contexto financeiro e cripto.  

---

## 🧮 KPIs do Agente

| Métrica | Descrição |
|----------|------------|
| ROI Consolidado (%) | Retorno sobre o colateral inicial |
| PnL 30d (USDT) | Variação acumulada de 30 dias |
| Total Alavancado | Valor total em margem (BTC + USDT) |
| Cooldown Ciclos | Tempo restante entre entradas consecutivas |
| Entradas Ativas | Número de operações abertas no ciclo atual |

---

## 🧠 Tecnologias Utilizadas

- **Python 3.10+**
- **Google ADK (1.16.0)** — Reasoning Agents Framework
- **Binance Python SDK**
- **Asyncio + Tenacity**
- **dotenv**
- **pytest (asyncio mode)**

---

## 🧩 Licença

Este projeto é de uso técnico restrito para fins de estudo, validação e automação experimental de estratégias quantitativas com IA.  
Não constitui recomendação financeira ou consultoria de investimento.

© 2025 — Desenvolvido por **Zack Mariano** 🧠⚡  
**GenAI Engineering**