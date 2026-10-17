"""Backend FastAPI de la demo en vivo (contrato en docs/ARCHITECTURE.md, seccion 8).

La demo corre DOS simulaciones a la vez, asi que necesita TraCI por socket (cada
SumoEnvironment de sumo-rl abre su propia conexion con etiqueta). libsumo solo permite
una simulacion por proceso, por eso aqui se desactiva antes de que se importe sumo_rl.
"""
import os

os.environ.pop("LIBSUMO_AS_TRACI", None)
