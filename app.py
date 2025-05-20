# TWOWTE Streamlit App – Sistema completo con Tienda, Monedas y Gestión de Rondas
# =============================================================================
#  (c) 2025 – Versión unificada y revisada
# -----------------------------------------------------------------------------
#  Características principales
#  -------------------------
#  • Base de datos SQLite con usuarios, monedas, rondas, respuestas y tienda.
#  • Solo se crea la cuenta admin (Jlarriva / FioreIsQueen) al iniciar.
#  • Tienda con objetos de efecto inmediato: Doble/Triple Respuesta, Desempate Favorable,
#    Ruleta del Tigre, Duplicador de Monedas.
#  • Sistema de recompensas configurable desde admin.
#  • Eliminación automática del último lugar y creación de la siguiente ronda.
#  • Panel Admin para editar monedas, respuestas, DF, activar/desactivar jugadores…
#  • Historial de rondas con victorias y promedio de puesto.
#  • Login persistente con st.session_state y recarga vía st.rerun().
# =============================================================================

import streamlit as st
import sqlite3
import numpy as np
import random
import datetime as dt

###############################################################################
# 1) Conexión y esquema de la base de datos                                   #
###############################################################################
DB = "game.db"
conn = sqlite3.connect(DB, check_same_thread=False)
c = conn.cursor()

# Usuarios
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL,
    role TEXT NOT NULL,            -- 'jugador' | 'juez'
    is_admin INTEGER NOT NULL,     -- 1 = sí, 0 = no
    coins INTEGER NOT NULL DEFAULT 5,
    active INTEGER NOT NULL DEFAULT 1
)""")
# Ajustes globales
c.execute("CREATE TABLE IF NOT EXISTS settings(clave TEXT PRIMARY KEY, valor TEXT)")
# Rondas
c.execute("""CREATE TABLE IF NOT EXISTS rounds(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    status TEXT NOT NULL,          -- 'open' | 'closed'
    created_at TEXT NOT NULL
)""")
# Respuestas / Frases
c.execute("""CREATE TABLE IF NOT EXISTS frases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    texto TEXT NOT NULL,
    autor TEXT NOT NULL,
    round_id INTEGER NOT NULL
)""")
# Votos
c.execute("""CREATE TABLE IF NOT EXISTS votos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    juez TEXT NOT NULL,
    frase_id INTEGER NOT NULL,
    posicion INTEGER NOT NULL
)""")
# Estado del jugador por ronda
c.execute("""CREATE TABLE IF NOT EXISTS player_round(
    round_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    responses_left INTEGER NOT NULL,
    df_flag INTEGER NOT NULL DEFAULT 0,
    multiplier INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(round_id, username)
)""")
# Compras
c.execute("""CREATE TABLE IF NOT EXISTS purchases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    item TEXT NOT NULL,
    meta TEXT
)""")
conn.commit()

###############################################################################
# 2) Seed: solo la cuenta admin si DB está vacía                               #
###############################################################################
if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
    admin = ("Jlarriva", "FioreIsQueen", "juez", 1, 20, 1)
    c.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", admin)
    conn.commit()

###############################################################################
# 3) Ajustes por defecto                                                      #
###############################################################################
DEFAULT_SETTINGS = {
    "titulo": "TWOWTE – Reality de Frases",
    "current_round": "1",
    "reward_first": "10",
    "reward_second": "7",
    "reward_third": "5",
    "reward_45": "3",
    "reward_participate": "1"
}
for k, v in DEFAULT_SETTINGS.items():
    c.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
conn.commit()

get_setting = lambda k: c.execute("SELECT valor FROM settings WHERE clave=?", (k,)).fetchone()[0]
set_setting = lambda k, v: (c.execute("REPLACE INTO settings VALUES(?,?)", (k, str(v))), conn.commit())

###############################################################################
# 4) Garantizar ronda abierta                                                 #
###############################################################################
current_round = int(get_setting("current_round"))
open_round = c.execute("SELECT id FROM rounds WHERE numero=? AND status='open'", (current_round,)).fetchone()
if not open_round:
    c.execute("INSERT INTO rounds(numero,status,created_at) VALUES(?,?,?)", (current_round, 'open', dt.datetime.utcnow().isoformat()))
    round_id = c.lastrowid
    active_players = c.execute("SELECT username FROM users WHERE active=1").fetchall()
    c.executemany("INSERT INTO player_round(round_id,username,responses_left) VALUES(?,?,1)", [(round_id, u[0]) for u in active_players])
    conn.commit()
    open_round = (round_id,)
round_id = open_round[0]

###############################################################################
# 5) Utilidades                                                              #
###############################################################################

def load_users(include_inactive=False):
    q = "SELECT username,password,role,is_admin,coins,active FROM users" + ("" if include_inactive else " WHERE active=1")
    return {u[0]: u for u in c.execute(q).fetchall()}

users = load_users(include_inactive=True)

def total_judges():
    return sum(1 for u in users.values() if u[2] == 'juez' and u[5] == 1)

###############################################################################
# 6) Streamlit – Config y sesión                                             #
###############################################################################
st.set_page_config(page_title="TWOWTE", page_icon="📝", layout="centered")
if 'user' not in st.session_state:
    st.session_state['user'] = None
    st.session_state['is_admin'] = False

st.title(get_setting("titulo"))

###############################################################################
# 7) LOGIN                                                                   #
###############################################################################
if not st.session_state['user']:
    st.sidebar.header("Login")
    u_input = st.sidebar.text_input("Usuario")
    p_input = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Entrar"):
        if u_input in users and users[u_input][1] == p_input and users[u_input][5] == 1:
            st.session_state['user'] = u_input
            st.session_state['is_admin'] = bool(users[u_input][3])
            st.rerun()
        else:
            st.sidebar.error("Credenciales incorrectas o cuenta inactiva.")
    st.stop()

username = st.session_state['user']
is_admin = st.session_state['is_admin']
st.sidebar.success(f"Conectado como {username}")
if st.sidebar.button("Cerrar sesión"):
    st.session_state.clear(); st.rerun()

###############################################################################
# 8) Declarar pestañas principales                                           #
###############################################################################
base_tabs = ["Acción", "Tienda", "Resultados", "Historial"]
if is_admin:
    base_tabs.append("Admin")
page_tabs = st.tabs(base_tabs)

t_action, t_shop, t_results, t_history = page_tabs[:4]
t_admin = page_tabs[4] if is_admin else None

###############################################################################
# 9) Acción: enviar frases                                                   #
###############################################################################
with t_action:
    player_state = c.execute("SELECT responses_left, df_flag FROM player_round WHERE round_id=? AND username=?", (round_id, username)).fetchone()
    if not player_state:
        st.error("No estás habilitado en esta ronda.")
    else:
        left, df_flag = player_state
        st.info(f"Respuestas restantes esta ronda: {left}")
        if left > 0:
            texto = st.text_input("Tu frase:")
            if st.button("Enviar respuesta"):
                if texto.strip():
                    c.execute("INSERT INTO frases(texto,autor,round_id) VALUES(?,?,?)", (texto.strip(), username, round_id))
                    c.execute("UPDATE player_round SET responses_left = responses_left - 1 WHERE round_id=? AND username=?", (round_id, username))
                    conn.commit()
                    st.success("Respuesta enviada.")
                    st.rerun()
        else:
            st.warning("Sin respuestas disponibles. Compra Doble/Triple Respuesta o espera la próxima ronda.")

        # Mostrar pendientes cuando haya ≥2 envíos
        total_envios = c.execute("SELECT COUNT(DISTINCT autor) FROM frases WHERE round_id=?", (round_id,)).fetchone()[0]
        if total_envios >= 2:
            enviados = set(r[0] for r in c.execute("SELECT DISTINCT autor FROM frases WHERE round_id=?", (round_id,)))
            faltan = [u for u in users if users[u][5] == 1 and u not in enviados]
            random.shuffle(faltan)
            st.write("**Aún no han enviado:** " + (", ".join(faltan) if faltan else "Todos han enviado"))

###############################################################################
# 10) Tienda                                                                 #
###############################################################################
with t_shop:
    st.subheader("Tienda de Objetos – un solo objeto por ronda")
    coins = c.execute("SELECT coins FROM users WHERE username=?", (username,)).fetchone()[0]
    st.write(f"Monedas disponibles: **{coins}**")

    SHOP = {
        "Doble Respuesta": 10,
        "Triple Respuesta": 25,
        "Desempate Favorable": 8,
        "Ruleta del Tigre": 9,
        "Duplicador de Monedas": 12
    }

    # Verificar si ya compró algo esta ronda
    already_bought = c.execute("SELECT item FROM purchases WHERE round_id=? AND username=?", (round_id, username)).fetchone()
    if already_bought:
        st.info(f"Ya compraste: **{already_bought[0]}** esta ronda.")
    else:
        for item, price in SHOP.items():
            colL, colR = st.columns([3, 1])
            with colL:
                st.write(f"**{item}** – {price} monedas")
            with colR:
                if st.button(f"Comprar {item}"):
                    if coins < price:
                        st.error("No tienes suficientes monedas.")
                    else:
                        # Aplicar efecto
                        if item == "Doble Respuesta":
                            c.execute("UPDATE player_round SET responses_left = responses_left + 1 WHERE round_id=? AND username=?", (round_id, username))
                        elif item == "Triple Respuesta":
                            c.execute("UPDATE player_round SET responses_left = responses_left + 2 WHERE round_id=? AND username=?", (round_id, username))
                        elif item == "Desempate Favorable":
                            c.execute("UPDATE player_round SET df_flag = 1 WHERE round_id=? AND username=?", (round_id, username))
                        elif item == "Duplicador de Monedas":
                            c.execute("UPDATE player_round SET multiplier = 2 WHERE round_id=? AND username=?", (round_id, username))
                        elif item == "Ruleta del Tigre":
                            with st.expander("Selecciona a los otros dos jugadores"):
                                p1 = st.text_input("Jugador 1")
                                p2 = st.text_input("Jugador 2")
                                if st.button("Jugar Ruleta"):
                                    valid = all(p in users and users[p][5] == 1 for p in [p1, p2]) and p1 != p2 and p1 not in [username, ""] and p2 not in [username, ""]
                                    if not valid:
                                        st.error("Jugadores inválidos o repetidos.")
                                    else:
                                        loser = random.choice([username, p1, p2])
                                        c.execute("UPDATE users SET coins = coins - 3 WHERE username=?", (loser,))
                                        st.success(f"La bala alcanzó a **{loser}**. Pierde 3 monedas.")
                        # Cobrar y registrar compra
                        c.execute("UPDATE users SET coins = coins - ? WHERE username=?", (price, username))
                        c.execute("INSERT INTO purchases(round_id, username, item) VALUES(?,?,?)", (round_id, username, item))
                        conn.commit()
                        st.success("Compra realizada y efecto aplicado.")
                        st.rerun()

###############################################################################
# 11) Resultados                                                             #
###############################################################################
with t_results:
    submitted = c.execute("SELECT COUNT(DISTINCT autor) FROM frases WHERE round_id=?", (round_id,)).fetchone()[0]
    if submitted == 0:
        st.info("Aún no hay respuestas.")
    else:
        needed = total_judges()
        voted = c.execute("SELECT COUNT(DISTINCT juez) FROM votos WHERE frase_id IN (SELECT id FROM frases WHERE round_id=?))", (round_id,)).fetchone()[0]
        if voted < needed:
            st.info(f"Faltan votos de {needed - voted} juez(es)...")
        else:
            # Calcular puntos
            frases = c.execute("SELECT id, texto, autor FROM frases WHERE round_id=?", (round_id,)).fetchall()
            N = len(frases)
            pts, pos_list = {}, {fid: [] for fid, _, _ in frases}
            for fid, _, _ in frases:
                pts[fid] = 0
            for fid, pos in c.execute("SELECT frase_id, posicion FROM votos WHERE frase_id 
