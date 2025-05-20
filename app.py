# TWOWTE Streamlit App – Fix líneas de resultados + cierre de strings
# =============================================================================
#  Esta versión completa corrige:
#  • Unterminated string literal en la consulta de votos
#  • Paréntesis duplicado en conteo de votos
#  • Calcula resultados con DF y STD correctamente
# =============================================================================
import streamlit as st
import sqlite3
import numpy as np
import random
import datetime as dt

DB = "game.db"
conn = sqlite3.connect(DB, check_same_thread=False)
c = conn.cursor()

# ---------- 1. Esquema -------------------------------------------------------
c.execute("""
CREATE TABLE IF NOT EXISTS users(
  username TEXT PRIMARY KEY,
  password TEXT NOT NULL,
  role TEXT NOT NULL,
  is_admin INTEGER NOT NULL,
  coins INTEGER NOT NULL DEFAULT 5,
  active INTEGER NOT NULL DEFAULT 1)
""")

c.execute("CREATE TABLE IF NOT EXISTS settings(clave TEXT PRIMARY KEY, valor TEXT)")

c.execute("""
CREATE TABLE IF NOT EXISTS rounds(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  numero INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS frases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  texto TEXT NOT NULL,
  autor TEXT NOT NULL,
  round_id INTEGER NOT NULL)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS votos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  juez TEXT NOT NULL,
  frase_id INTEGER NOT NULL,
  posicion INTEGER NOT NULL)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS player_round(
  round_id INTEGER NOT NULL,
  username TEXT NOT NULL,
  responses_left INTEGER NOT NULL,
  df_flag INTEGER NOT NULL DEFAULT 0,
  multiplier INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(round_id,username))
""")

c.execute("""
CREATE TABLE IF NOT EXISTS purchases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  round_id INTEGER NOT NULL,
  username TEXT NOT NULL,
  item TEXT NOT NULL,
  meta TEXT)
""")
conn.commit()

# ---------- 2. Seed admin ----------------------------------------------------
if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
    c.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", ("Jlarriva", "FioreIsQueen", "juez", 1, 20, 1))
    conn.commit()

# ---------- 3. Settings defaults --------------------------------------------
DEFAULTS = {
  "titulo": "TWOWTE – Reality de Frases",
  "current_round": "1",
  "reward_first": "10",
  "reward_second": "7",
  "reward_third": "5",
  "reward_45": "3",
  "reward_participate": "1"
}
for k,v in DEFAULTS.items():
    c.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k,v))
conn.commit()
get_setting = lambda k: c.execute("SELECT valor FROM settings WHERE clave=?", (k,)).fetchone()[0]
set_setting = lambda k,v: (c.execute("REPLACE INTO settings VALUES(?,?)", (k,str(v))), conn.commit())

# ---------- 4. Ronda activa --------------------------------------------------
current_round = int(get_setting("current_round"))
open_r = c.execute("SELECT id FROM rounds WHERE numero=? AND status='open'", (current_round,)).fetchone()
if not open_r:
    c.execute("INSERT INTO rounds(numero,status,created_at) VALUES(?,?,?)", (current_round,'open',dt.datetime.utcnow().isoformat()))
    rid = c.lastrowid
    players = c.execute("SELECT username FROM users WHERE active=1").fetchall()
    c.executemany("INSERT INTO player_round(round_id,username,responses_left) VALUES(?,?,1)", [(rid,p[0]) for p in players])
    conn.commit()
    open_r=(rid,)
round_id = open_r[0]

# ---------- 5. Utils ---------------------------------------------------------

def load_users(active_only=False):
    q="SELECT username,password,role,is_admin,coins,active FROM users"+(" WHERE active=1" if active_only else "")
    return {u[0]:u for u in c.execute(q).fetchall()}
users = load_users()

def total_judges():
    return sum(1 for u in users.values() if u[2]=='juez' and u[5]==1)

# ---------- 6. Streamlit config + session ------------------------------------
st.set_page_config(page_title="TWOWTE", page_icon="📝", layout="centered")
if 'user' not in st.session_state:
    st.session_state['user']=None
    st.session_state['is_admin']=False

st.title(get_setting("titulo"))

if not st.session_state['user']:
    st.sidebar.header("Login")
    u=st.sidebar.text_input("Usuario")
    p=st.sidebar.text_input("Contraseña",type="password")
    if st.sidebar.button("Entrar"):
        if u in users and users[u][1]==p and users[u][5]==1:
            st.session_state['user']=u
            st.session_state['is_admin']=bool(users[u][3])
            st.rerun()
        else:
            st.sidebar.error("Credenciales incorrectas o usuario inactivo")
    st.stop()

username = st.session_state['user']
is_admin = st.session_state['is_admin']
st.sidebar.success(f"Conectado como {username}")
if st.sidebar.button("Cerrar sesión"):
    st.session_state.clear(); st.rerun()

# ---------- 7. Tabs ----------------------------------------------------------
tab_names=["Acción","Tienda","Resultados","Historial"]+(["Admin"] if is_admin else [])
tabs=st.tabs(tab_names)

# ================ ACCIÓN =====================================================
with tabs[0]:
    state=c.execute("SELECT responses_left,df_flag FROM player_round WHERE round_id=? AND username=?",(round_id,username)).fetchone()
    if not state:
        st.error("No participas en esta ronda.")
    else:
        left,df_flag=state
        st.info(f"Respuestas restantes: {left}")
        if left>0:
            frase=st.text_input("Tu frase:")
            if st.button("Enviar") and frase.strip():
                c.execute("INSERT INTO frases(texto,autor,round_id) VALUES(?,?,?)",(frase.strip(),username,round_id))
                c.execute("UPDATE player_round SET responses_left=responses_left-1 WHERE round_id=? AND username=?",(round_id,username))
                conn.commit(); st.success("Enviada"); st.rerun()
        # pendientes
        enviados=set(x[0] for x in c.execute("SELECT DISTINCT autor FROM frases WHERE round_id=?",(round_id,)))
        if len(enviados)>=2:
            faltan=[u for u in users if users[u][5]==1 and u not in enviados]
            random.shuffle(faltan)
            st.write("Pendientes:",", ".join(faltan) if faltan else "Todos han enviado")

# ================ TIENDA =====================================================
SHOP={"Doble Respuesta":10,"Triple Respuesta":25,"Desempate Favorable":8,"Ruleta del Tigre":9,"Duplicador de Monedas":12}
with tabs[1]:
    coins=c.execute("SELECT coins FROM users WHERE username=?",(username,)).fetchone()[0]
    st.write(f"Monedas: **{coins}**")
    bought=c.execute("SELECT item FROM purchases WHERE round_id=? AND username=?",(round_id,username)).fetchone()
    if bought:
        st.info(f"Ya compraste {bought[0]} esta ronda.")
    else:
        for itm,price in SHOP.items():
            colA,colB=st.columns([3,1])
            colA.write(f"**{itm}** – {price} monedas")
            if colB.button(f"Comprar {itm}"):
                if coins<price:
                    st.error("Monedas insuficientes")
                else:
                    # efectos
                    if itm=="Doble Respuesta":
                        c.execute("UPDATE player_round SET responses_left=responses_left+1 WHERE round_id=? AND username=?",(round_id,username))
                    elif itm=="Triple Respuesta":
                        c.execute("UPDATE player_round SET responses_left=responses_left+2 WHERE round_id=? AND username=?",(round_id,username))
                    elif itm=="Desempate Favorable":
                        c.execute("UPDATE player_round SET df_flag=1 WHERE round_id=? AND username=?",(round_id,username))
                    elif itm=="Duplicador de Monedas":
                        c.execute("UPDATE player_round SET multiplier=2 WHERE round_id=? AND username=?",(round_id,username))
                    elif itm=="Ruleta del Tigre":
                        with st.expander("Selecciona dos rivales"):
                            r1=st.text_input("Jugador 1")
                            r2=st.text_input("Jugador 2")
                            if st.button("Ejecutar Ruleta"):
                                valid=all(r in users and users[r][5]==1 for r in [r1,r2]) and r1!=r2 and r1 not in ["",username] and r2 not in ["",username]
                                if valid:
                                    loser=random.choice([username,r1,r2])
                                    c.execute("UPDATE users SET coins=coins-3 WHERE username=?",(loser,))
                                    st.success(f"Perdedor: {loser}")
                                else:
                                    st.error("Jugadores inválidos")
                    # cobrar y registrar
                    c.execute("UPDATE users SET coins=coins-? WHERE username=?",(price,username))
                    c.execute("INSERT INTO purchases(round_id,username,item) VALUES(?,?,?)",(round_id,username,itm))
                    conn.commit(); st.success("Compra aplicada"); st.rerun()

# ================ RESULTADOS =================================================
with tabs[2]:
    num_env=c.execute("SELECT COUNT(DISTINCT autor) FROM frases WHERE round_id=?",(round_id,)).fetchone()[0]
    if num_env==0:
        st.info("Aún sin frases.")
    else:
        need=total_judges()
        got=c.execute("SELECT COUNT(DISTINCT juez) FROM votos WHERE frase_id IN (SELECT id FROM frases WHERE round_id=? )",(round_id,)).fetchone()[0]
        if got<need:
            st.info(f"Faltan votos de {need-got} juez(es)")
        else:
            frases=c.execute("SELECT id,texto,autor FROM frases WHERE round_id=?",(round_id,)).fetchall()
            N=len(frases)
            puntos={fid:0 for fid,_,_ in frases}
            pos_list={fid:[] for fid,_,_ in frases}
            for fid,pos in c.execute("SELECT frase_id,posicion FROM votos WHERE frase_id IN (SELECT id FROM frases WHERE round_id=? )",(round_id,)):
                puntos[fid]+=N+1-pos
                pos_list[fid].append(pos)
            results=[]
            for fid,txt,aut in frases:
                std=float(np.std(pos_list[fid])) if pos_list[fid] else 0.0
                df=c.execute("SELECT df_flag FROM player_round WHERE round_id=? AND username=?",(round_id,aut)).fetchone()[0]
                results.append({"Autor":aut,"Puntos":puntos[fid],"DF":bool(df),"STD":std,"Frase":txt})
            results.sort(key=lambda r:(r["Puntos"],r["DF"],r["STD"]),reverse=True)
            st.table(results)

# ================ HISTORIAL ==================================================
with tabs[3]:
    rounds=c.execute("SELECT id,numero FROM rounds WHERE status='closed' ORDER BY numero").fetchall()
    summary=[]
    wins,avg={},{}
    for u in users: wins[u]=0; avg[u]=[]
    for rid,num in rounds:
        frases=c.execute("SELECT id,autor FROM frases WHERE round_id=?",(rid,)).fetchall()
        N=len(frases)
        pts={a:0 for _,a in frases}
        for fid,pos in c.execute("SELECT frase_id,posicion FROM votos WHERE frase_id IN (SELECT id FROM frases WHERE round_id=? )",(rid,)):
            aut=c.execute("SELECT autor FROM frases WHERE id=?",(fid,)).fetchone()[0]
            pts[aut]+=N+1-pos
        if pts:
            ordered=sorted(pts,key=pts.get,reverse=True)
            wins[ordered[0]]+=1
            for rank,au in enumerate(ordered,1):
                avg[au].append(rank)
    for u in users:
        if avg[u]:
            summary.append({"Jugador":u,"Victorias":wins[u],"Prom":round(np.mean(avg[u]),2)})
    st.table(summary)

# ================ ADMIN ======================================================
if is_admin:
    with tabs[-1]:
        st.header("Panel Admin")
        # recompensas
        st.subheader("Recompensas")
        col1,col2,col3,col4=st.columns(4)
        r1=col1.number_input("1º",value=int(get_setting("reward_first")))
        r2=col2.number_input("2º",value=int(get_setting("reward_second")))
        r3=col3.number_input("3º",value=int(get_setting("reward_third")))
        r45=col4.number_input("4º-5º",value=int(get_setting("reward_45")))
        # TWOWTE Streamlit App – Fix completo
# (sección previa idéntica a la mostrada; continúo desde el panel admin)

        if st.button("Guardar recompensas"):
            set_setting("reward_first", r1)
            set_setting("reward_second", r2)
            set_setting("reward_third", r3)
            set_setting("reward_45", r45)
            st.success("Recompensas guardadas")

        st.markdown("---")
        # Ajustes individuales
        st.subheader("Ajustar jugador en la ronda")
        usuario_sel = st.selectbox("Jugador activo", [u for u in users if users[u][5] == 1])
        d_coins = st.number_input("±Monedas", value=0, step=1)
        d_resp  = st.number_input("±Respuestas", value=0, step=1)
        toggle_df = st.checkbox("Alternar Desempate Favorable")

        if st.button("Aplicar ajustes"):
            if d_coins:
                c.execute("UPDATE users SET coins = coins + ? WHERE username=?", (d_coins, usuario_sel))
            if d_resp:
                c.execute(
                    "UPDATE player_round SET responses_left = responses_left + ? WHERE round_id=? AND username=?",
                    (d_resp, round_id, usuario_sel))
            if toggle_df:
                cur_df = c.execute(
                    "SELECT df_flag FROM player_round WHERE round_id=? AND username=?",
                    (round_id, usuario_sel)).fetchone()[0]
                c.execute("UPDATE player_round SET df_flag=? WHERE round_id=? AND username=?",
                          (0 if cur_df else 1, round_id, usuario_sel))
            conn.commit()
            st.success("Ajustes aplicados")
            st.rerun()

        st.markdown("---")
        # Activar / desactivar
        st.subheader("Activar / Desactivar cuentas")
        colA, colB = st.columns(2)
        with colA:
            des = st.selectbox("Desactivar jugador", [u for u in users if users[u][5] == 1])
            if st.button("Desactivar"):
                c.execute("UPDATE users SET active=0 WHERE username=?", (des,))
                conn.commit()
                st.success(f"{des} desactivado"); st.rerun()
        with colB:
            act = st.selectbox("Reactivar jugador", [u for u in users if users[u][5] == 0])
            if st.button("Reactivar"):
                c.execute("UPDATE users SET active=1 WHERE username=?", (act,))
                conn.commit()
                st.success(f"{act} reactivado"); st.rerun()

        st.markdown("---")
        # Cerrar ronda
        if st.button("Cerrar ronda y otorgar premios"):
            # Grabar ranking
            frases = c.execute("SELECT id, autor FROM frases WHERE round_id=?", (round_id,)).fetchall()
            if not frases:
                st.error("No hay respuestas")
            else:
                N = len(frases)
                pts = {a: 0 for _, a in frases}
                for fid, pos in c.execute(
                    "SELECT frase_id, posicion FROM votos WHERE frase_id IN "
                    "(SELECT id FROM frases WHERE round_id=?)", (round_id,)):
                    autor = c.execute("SELECT autor FROM frases WHERE id=?", (fid,)).fetchone()[0]
                    pts[autor] += N + 1 - pos

                ranking = sorted(pts, key=pts.get, reverse=True)
                recompensas = [
                    int(get_setting("reward_first")),
                    int(get_setting("reward_second")),
                    int(get_setting("reward_third")),
                    int(get_setting("reward_45")),
                    int(get_setting("reward_45"))
                ]
                for i, jugador in enumerate(ranking):
                    premio = recompensas[i] if i < len(recompensas) else int(get_setting("reward_participate"))
                    mult   = c.execute(
                        "SELECT multiplier FROM player_round WHERE round_id=? AND username=?",
                        (round_id, jugador)).fetchone()[0]
                    c.execute("UPDATE users SET coins = coins + ? WHERE username=?", (premio * mult, jugador))

                eliminado = ranking[-1]
                c.execute("UPDATE users SET active=0 WHERE username=?", (eliminado,))
                # Cerrar ronda
                c.execute("UPDATE rounds SET status='closed' WHERE id=?", (round_id,))
                # Siguiente ronda
                next_num = current_round + 1
                set_setting("current_round", next_num)
                c.execute("INSERT INTO rounds(numero,status,created_at) VALUES(?,?,?)",
                          (next_num, 'open', dt.datetime.utcnow().isoformat()))
                new_rid = c.lastrowid
                activos = c.execute("SELECT username FROM users WHERE active=1").fetchall()
                c.executemany(
                    "INSERT INTO player_round(round_id,username,responses_left) VALUES(?,?,1)",
                    [(new_rid, p[0]) for p in activos])
                conn.commit()
                st.success(f"Ronda cerrada. Eliminado: {eliminado}. Ronda {next_num} abierta.")
                st.rerun()


