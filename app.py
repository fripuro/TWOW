# TWOWTE Streamlit App – Versión con Sistema de Tienda, Monedas y Rondas
# =============================================================================
#   ░█▀▄░█░░░▀█▀░█░█░█▀▀░█░█░█▀▀░▀█▀░█▀▀░
#   ░█▀▄░█░░░░█░░█▄█░▀▀█░█░█░█▀▀░░█░░█▀▀░
#   ░▀▀░░▀▀▀░▀▀▀░▀░▀░▀▀▀░▀▀▀░▀▀▀░░▀░░▀▀▀░
# -----------------------------------------------------------------------------
# - Monedas persistentes en users.coins
# - Rondas almacenadas en rounds; nueva tabla player_round para estados por ronda
# - Tienda con objetos: Doble/Triple Respuesta, Desempate Favorable, Ruleta del Tigre, Duplicador de Monedas
# - Admin puede editar monedas, puntos, respuestas, eliminaciones y recompensa por puesto
# - Resultados muestran columna DF y STD; historial de rondas con estadísticas
# - Sesión persiste vía st.session_state['user'] evitando volver a loguear al recargar
# =============================================================================
import streamlit as st
import sqlite3
import numpy as np
import random
import datetime as dt

DB = "game.db"
conn = sqlite3.connect(DB, check_same_thread=False)
c = conn.cursor()

# ------------------------------------------------------
# 1) ESQUEMA DE BASE DE DATOS
# ------------------------------------------------------
# users: username, password, role, is_admin, coins, active
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL,
    role TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    coins INTEGER NOT NULL DEFAULT 5,
    active INTEGER NOT NULL DEFAULT 1
)""")
# settings: clave, valor
c.execute("CREATE TABLE IF NOT EXISTS settings(clave TEXT PRIMARY KEY, valor TEXT)")
# rounds: id, numero, status, created_at
c.execute("""CREATE TABLE IF NOT EXISTS rounds(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
)""")
# frases: id, texto, autor, round_id
c.execute("""CREATE TABLE IF NOT EXISTS frases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    texto TEXT NOT NULL,
    autor TEXT NOT NULL,
    round_id INTEGER NOT NULL
)""")
# votos: id, juez, frase_id, posicion
c.execute("""CREATE TABLE IF NOT EXISTS votos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    juez TEXT NOT NULL,
    frase_id INTEGER NOT NULL,
    posicion INTEGER NOT NULL
)""")
# player_round: round_id, username, responses_left, df_flag, multiplier
c.execute("""CREATE TABLE IF NOT EXISTS player_round(
    round_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    responses_left INTEGER NOT NULL,
    df_flag INTEGER NOT NULL DEFAULT 0,
    multiplier INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(round_id, username)
)""")
# purchases: id, round_id, username, item, meta
c.execute("""CREATE TABLE IF NOT EXISTS purchases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    item TEXT NOT NULL,
    meta TEXT
)""")
conn.commit()

# ------------------------------------------------------
# 2) SEED DE USUARIOS (si no existen)
# ------------------------------------------------------
if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
    seed = [
        ("Jlarriva", "FioreIsQueen", "juez", 1, 20, 1),
        ("Juez1", "j123", "juez", 0, 10, 1),
        ("Juez2", "j234", "juez", 0, 10, 1),
    ] + [(f"User{i}", f"pass{i}", "jugador", 0, 5, 1) for i in range(1, 17)]
    c.executemany("INSERT INTO users VALUES(?,?,?,?,?,?)", seed)
    conn.commit()

# ------------------------------------------------------
# 3) SETTINGS DEFAULTS
# ------------------------------------------------------
defaults = {
    "titulo": "TWOWTE – Reality de Frases",
    "current_round": "1",
    "reward_first": "10",
    "reward_second": "7",
    "reward_third": "5",
    "reward_45": "3",
    "reward_participate": "1"
}
for k, v in defaults.items():
    c.execute("INSERT OR IGNORE INTO settings(clave, valor) VALUES(?,?)", (k, v))
conn.commit()

def set_setting(k, v):
    c.execute("REPLACE INTO settings VALUES(?,?)", (k, str(v)))
    conn.commit()

def get_setting(k):
    return c.execute("SELECT valor FROM settings WHERE clave=?", (k,)).fetchone()[0]

# ------------------------------------------------------
# 4) RONDA ACTUAL – se asegura una abierta
# ------------------------------------------------------
current_round = int(get_setting("current_round"))
active_round = c.execute("SELECT id FROM rounds WHERE numero=? AND status='open'", (current_round,)).fetchone()
if not active_round:
    c.execute("INSERT INTO rounds(numero,status,created_at) VALUES(?,?,?)", (current_round, 'open', dt.datetime.utcnow().isoformat()))
    round_id = c.lastrowid
    # inicializar player_round rows
    users = c.execute("SELECT username FROM users WHERE active=1").fetchall()
    c.executemany("INSERT INTO player_round(round_id, username, responses_left) VALUES(?,?,1)", [(round_id, u[0]) for u in users])
    conn.commit()
    active_round = (round_id,)
round_id = active_round[0]

# ------------------------------------------------------
# 5) UTILIDADES
# ------------------------------------------------------

def load_users(active_only=True):
    if active_only:
        rows = c.execute("SELECT username,password,role,is_admin,coins FROM users WHERE active=1").fetchall()
    else:
        rows = c.execute("SELECT username,password,role,is_admin,coins,active FROM users").fetchall()
    return {r[0]: r for r in rows}

users = load_users(active_only=False)

def total_judges():
    return sum(1 for u in users.values() if u[2] == 'juez' and u[5] == 1 if len(u) >5 else u[2] == 'juez')

# awards list for current settings
rewards = [int(get_setting("reward_first")), int(get_setting("reward_second")), int(get_setting("reward_third"))]

# ------------------------------------------------------
# 6) SESSION / LOGIN
# ------------------------------------------------------
if 'user' not in st.session_state:
    st.session_state['user'] = None
if 'is_admin' not in st.session_state:
    st.session_state['is_admin'] = False

st.set_page_config(page_title="TWOWTE", page_icon="📝", layout="centered")
st.title(get_setting("titulo"))

if not st.session_state['user']:
    st.sidebar.header("Login")
    u = st.sidebar.text_input("Usuario")
    p = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Entrar"):
        if u in users and users[u][1] == p and users[u][5] == 1:
            st.session_state['user'] = u
            st.session_state['is_admin'] = bool(users[u][3])
            st.experimental_rerun()
        else:
            st.sidebar.error("Credenciales incorrectas o usuario deshabilitado")
else:
    username = st.session_state['user']
    is_admin = st.session_state['is_admin']
    st.sidebar.success(f"Conectado como {username}")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.clear(); st.experimental_rerun()

    # --------------------------------------------------
    # 7) TABS PRINCIPALES
    # --------------------------------------------------
    tabs = ["Acción", "Tienda", "Resultados", "Historial"]
    if is_admin:
        tabs.append("Admin")
    t_action, t_shop, t_results, t_history, *t_admin = st.tabs(tabs)

    # --------------------------------------------------
    # ACCIÓN
    # --------------------------------------------------
    with t_action:
        # Responses left
        responses_left = c.execute("SELECT responses_left, df_flag FROM player_round WHERE round_id=? AND username=?", (round_id, username)).fetchone()
        if not responses_left:
            st.error("No estás activo en esta ronda.")
        else:
            left, df_flag = responses_left
            st.info(f"Respuestas restantes esta ronda: {left}")
            if left > 0:
                frase = st.text_input("Tu frase:")
                if st.button("Enviar"):
                    if frase.strip():
                        c.execute("INSERT INTO frases(texto, autor, round_id) VALUES(?,?,?)", (frase.strip(), username, round_id))
                        c.execute("UPDATE player_round SET responses_left = responses_left-1 WHERE round_id=? AND username=?", (round_id, username))
                        conn.commit()
                        st.success("Respuesta registrada")
                        st.experimental_rerun()
            else:
                st.warning("Sin respuestas restantes. Compra Doble/Triple respuesta o espera siguiente ronda.")

            # Lista de pendientes
            enviados = set(r[0] for r in c.execute("SELECT DISTINCT autor FROM frases WHERE round_id=?", (round_id,)))
            if len(enviados) >= 2:
                faltan = [u for u in users if users[u][5]==1 and u not in enviados]
                random.shuffle(faltan)
                st.write("**Pendientes de respuesta:**", ", ".join(faltan) if faltan else "Todos respondieron")

    # --------------------------------------------------
    # TIENDA
    # --------------------------------------------------
    with t_shop:
        st.subheader("Tienda – compra 1 objeto por ronda")
        coins = c.execute("SELECT coins FROM users WHERE username=?", (username,)).fetchone()[0]
        st.write(f"Monedas disponibles: **{coins}**")
        shop_items = {
            "Doble Respuesta": 10,
            "Triple Respuesta": 25,
            "Desempate Favorable": 8,
            "Ruleta del Tigre": 9,
            "Duplicador de Monedas": 12
        }
        for item, price in shop_items.items():
            col1, col2 = st.columns([3,1])
            with col1:
                st.write(f"**{item}** – {price} monedas")
            with col2:
                if st.button(f"Comprar {item}"):
                    if coins < price:
                        st.error("Monedas insuficientes")
                    else:
                        # Aplicar efecto inmediato
                        if item == "Doble Respuesta":
                            c.execute("UPDATE player_round SET responses_left = 2 WHERE round_id=? AND username=?", (round_id, username))
                        elif item == "Triple Respuesta":
                            c.execute("UPDATE player_round SET responses_left = 3 WHERE round_id=? AND username=?", (round_id, username))
                        elif item == "Desempate Favorable":
                            c.execute("UPDATE player_round SET df_flag=1 WHERE round_id=? AND username=?", (round_id, username))
                        elif item == "Ruleta del Tigre":
                            p1 = st.text_input("Jugador 1", key=f"r1_{random.random()}")
                            p2 = st.text_input("Jugador 2", key=f"r2_{random.random()}")
                            if st.button("Confirmar Ruleta"):
                                if p1 not in users or p2 not in users or p1==p2 or p1==username or p2==username:
                                    st.error("Participantes inválidos")
                                else:
                                    loser = random.choice([username, p1, p2])
                                    c.execute("UPDATE users SET coins = coins - 3 WHERE username=?", (loser,))
                                    st.success(f"Perdedor de la Ruleta: {loser}")
                        elif item == "Duplicador de Monedas":
                            c.execute("UPDATE player_round SET multiplier=2 WHERE round_id=? AND username=?", (round_id, username))
                        # Cobrar y registrar compra
                        c.execute("UPDATE users SET coins=coins-? WHERE username=?", (price, username))
                        c.execute("INSERT INTO purchases(round_id, username, item) VALUES(?,?,?)", (round_id, username, item))
                        conn.commit()
                        st.success("Compra realizada y efecto aplicado")
                        st.experimental_rerun()

    # --------------------------------------------------
    # RESULTADOS
    # --------------------------------------------------
    with t_results:
        submitted_players = c.execute("SELECT COUNT(DISTINCT autor) FROM frases WHERE round_id=?", (round_id,)).fetchone()[0]
        judges_needed = total_judges()
        votes_ready = c.execute("SELECT COUNT(DISTINCT juez) FROM votos WHERE frase_id IN (SELECT id FROM frases WHERE round_id=?)", (round_id,)).fetchone()[0]
        if submitted_players==0:
            st.info("Sin respuestas aún.")
        elif votes_ready < judges_needed:
            st.info(f"Esperando votos de {judges_needed - votes_ready} juez(es) …")
        else:
            # Calcular resultados
            frases_round = c.execute("SELECT id, texto, autor FROM frases WHERE round_id=?", (round_id,)).fetchall()
            N = len(frases_round)
            puntos, positions = {}, {}
            for fid, txt, aut in frases_round:
                puntos[fid] = 0
                positions[fid] = []
            for fid, pos in c.execute("SELECT frase_id, posicion FROM votos WHERE frase_id IN (SELECT id FROM frases WHERE round_id=?)", (round_id,)):
                puntos[fid] += N + 1 - pos
                positions[fid].append(pos)
            results = []
            for fid, txt, aut in frases_round:
                std = float(np.std(positions[fid])) if positions[fid] else 0.0
                df = c.execute("SELECT df_flag FROM player_round WHERE round_id=? AND username=?", (round_id, aut)).fetchone()[0]
                results.append({"Autor": aut, "Frase": txt, "Puntos": puntos[fid], "DF": bool(df), "STD": std})
            # aplicar desempate
            def sort_key(r):
                return (r["Puntos"], r["DF"], r["STD"])
            results.sort(key=sort_key, reverse=True)
            st.table(results)

    # --------------------------------------------------
    # HISTORIAL
    # --------------------------------------------------
    with t_history:
        st.subheader("Historial de rondas")
        rounds_info = c.execute("SELECT id, numero, status FROM rounds ORDER BY numero").fetchall()
        st.write("Total de rondas:", len(rounds_info))
        # estadísticas
        wins = {u:0 for u in users}
        avg_positions = {u:[] for u in users}
        for rid, num, stt in rounds_info:
            frases_r = c.execute("SELECT id, autor FROM frases WHERE round_id=?", (rid,)).fetchall()
            N = len(frases_r)
            pts = {}
            for fid, aut in frases_r:
                pts[aut]=0
            for fid, pos in c.execute("SELECT frase_id, posicion FROM votos WHERE frase_id IN (SELECT id FROM frases WHERE round_id=?)", (rid,)):
                aut = c.execute("SELECT autor FROM frases WHERE id=?", (fid,)).fetchone()[0]
                pts[aut] += N + 1 - pos
            if pts:
                winner = max(pts, key=pts.get)
                wins[winner]+=1
                sorted_pos = sorted(pts.values(), reverse=True)
                ranking = {a: rank+1 for rank, a in enumerate(sorted(pts, key=pts.get, reverse=True))}
                for a, rk in ranking.items():
                    avg_positions[a].append(rk)
        stats = []
        for u in users:
            if avg_positions[u]:
                stats.append({"Jugador":u, "Victorias":wins[u], "Promedio": round(np.mean(avg_positions[u]),2)})
        st.table(stats)

    # --------------------------------------------------
    # ADMIN
    # --------------------------------------------------
    if is_admin:
        with t_admin[0]:
            st.header("Panel de Administración")
            # Modificar recompensas
            st.subheader("Recompensas por ronda")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                r1 = st.number_input("1º", min_value=0, value=int(get_setting("reward_first")))
            with col2:
                r2 = st.number_input("2º", min_value=0, value=int(get_setting("reward_second")))
            with col3:
                r3 = st.number_input("3º", min_value=0, value=int(get_setting("reward_third")))
            with col4:
                r45 = st.number_input("4º-5º", min_value=0, value=int(get_setting("reward_45")))
            if st.button("Guardar recompensas"):
                set_setting("reward_first", r1); set_setting("reward_second", r2)
                set_setting("reward_third", r3); set_setting("reward_45", r45)
                st.success("Guardado")
            st.markdown("---")
            # Ajustes a jugador
            st.subheader("Ajustar jugador")
            sel_user = st.selectbox("Jugador", list(users.keys()))
            colA, colB, colC = st.columns(3)
            with colA:
                delta_coins = st.number_input("±Monedas", value=0)
            with colB:
                delta_resp = st.number_input("±Respuestas", value=0)
            with colC:
                delta_df = st.checkbox("Dar/Remover DF")
            if st.button("Aplicar ajustes"):
                if delta_coins!=0:
                    c.execute("UPDATE users SET coins = coins + ? WHERE username=?", (delta_coins, sel_user))
                if delta_resp!=0:
                    c.execute("UPDATE player_round SET responses_left = responses_left + ? WHERE round_id=? AND username=?", (delta_resp, round_id, sel_user))
                if delta_df:
                    current = c.execute("SELECT df_flag FROM player_round WHERE round_id=? AND username=?", (round_id, sel_user)).fetchone()[0]
                    c.execute("UPDATE player_round SET df_flag=? WHERE round_id=? AND username=?", (0 if current else 1, round_id, sel_user))
                conn.commit(); st.success("Ajustes aplicados")
            st.markdown("---")
            # Eliminar / Rehabilitar
            st.subheader("Eliminar / Rehabilitar jugador")
            colDel, colRe = st.columns(2)
            with colDel:
                del_user = st.selectbox("Eliminar", [u for u in users if users[u][5]==1])
                if st.button("Eliminar"):
                    c.execute("UPDATE users SET active=0 WHERE username=?", (del_user,))
                    conn.commit(); st.success("Eliminado")
            with colRe:
                rec_user = st.selectbox("Rehabilitar", [u for u in users if users[u][5]==0])
                if st.button("Rehabilitar"):
                    c.execute("UPDATE users SET active=1 WHERE username=?", (rec_user,))
                    conn.commit(); st.success("Rehabilitado")
            st.markdown("---")
            # Cerrar ronda
            if st.button("Cerrar ronda y asignar premios"):
                # calcular ranking final (como arriba) --------------------------------
                frases_round = c.execute("SELECT id, autor FROM frases WHERE round_id=?", (round_id,)).fetchall()
                if not frases_round:
                    st.error("No hay frases para cerrar la ronda.")
                else:
                    # ranking por puntos
                    N=len(frases_round)
                    pts={a:0 for _,a in frases_round}
                    for fid, pos in c.execute("SELECT frase_id, posicion FROM votos WHERE frase_id IN (SELECT id FROM frases WHERE round_id=?)", (round_id,)):
                        a=c.execute("SELECT autor FROM frases WHERE id=?", (fid,)).fetchone()[0]
                        pts[a]+=N+1-pos
                    order=sorted(pts,key=pts.get,reverse=True)
                    # asignar premios
                    rewards_list=[int(get_setting("reward_first")),int(get_setting("reward_second")),int(get_setting("reward_third")),int(get_setting("reward_45")),int(get_setting("reward_45"))]
                    for i,u in enumerate(order):
                        reward=rewards_list[i] if i<len(rewards_list) else int(get_setting("reward_participate"))
                        mult=c.execute("SELECT multiplier FROM player_round WHERE round_id=? AND username=?",(round_id,u)).fetchone()[0]
                        c.execute("UPDATE users SET coins = coins + ? WHERE username=?",(reward*mult,u))
                    # eliminar último
                    last=order[-1]
                    c.execute("UPDATE users SET active=0 WHERE username=?",(last,))
                    # cerrar ronda y crear nueva -----------------------------------
                    c.execute("UPDATE rounds SET status='closed' WHERE id=?",(round_id,))
                    new_num=current_round+1; set_setting("current_round", new_num)
                    c.execute("INSERT INTO rounds(numero,status,created_at) VALUES(?,?,?)", (new_num,'open',dt.datetime.utcnow().isoformat()))
                    new_rid=c.lastrowid
                    active_players=c.execute("SELECT username FROM users WHERE active=1").fetchall()
                    c.executemany("INSERT INTO player_round(round_id, username, responses_left) VALUES(?,?,1)",[(new_rid,u[0]) for u in active_players])
                    conn.commit()
                    st.success(f"Ronda {current_round} cerrada. Eliminado: {last}. Nueva ronda creada.")
                    st.experimental_rerun()
