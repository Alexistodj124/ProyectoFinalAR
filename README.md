# Semáforos inteligentes en Av. La Reforma con RL multiagente

Proyecto final de CC3104 Aprendizaje por Refuerzo (UVG, ciclo 2, 2026). Simulamos en SUMO un corredor de Av. La Reforma (zona 9/10) y comparamos agentes RL (Q-Learning, Dyna-Q, DQN, PPO, IDQN, QMIX y MAPPO) contra tres líneas base: tiempo fijo, actuado y max-pressure.

## Instalación
```bash
bash scripts/setup_env.sh      # crea ../.venv e instala SUMO + dependencias
source scripts/env.sh          # activa el venv y exporta SUMO_HOME
python -m pytest -q
```

## Estructura
Las interfaces entre módulos están en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

| Carpeta | Contenido |
|---|---|
| `env/` | Red de Reforma, conteos, generación de demanda y fábrica de entornos |
| `baselines/` | Tiempo fijo, actuado, max-pressure |
| `agents/` | Q-Learning, Dyna-Q, DQN, PPO, IDQN, QMIX, MAPPO, comunicación |
| `experiments/` | Configs YAML, `train.py`, `evaluate.py` |
| `analysis/` | Tablas y gráficas |
| `notebooks/` | Notebooks para Google Colab |
| `web/` | Demo en vivo (FastAPI + React) |
| `docs/` | Informe, slides y figuras |
