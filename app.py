import streamlit as st
import sqlite3
import numpy as np

DB_PATH = "game.db"

###############################
# 1) BASE DE DATOS y USUARIOS
###############################
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# TABLAS PRINCIPALES -------------------------------------------------

c.execute("""
CREATE TABLE IF NOT EXISTS frases (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    texto   TEXT    NOT NULL,
    autor   TEXT    NOT NULL
)""")

c.execute("""
CREATE TABLE IF NOT EXISTS votos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    juez      TEXT    NOT NULL,
    frase_id  INTEGER NOT NULL,
    posicion  INTEGER NOT NULL
)""")

c.execute("""
CREATE TABLE IF NOT EXISTS settings (
    clave  TEXT PRIMARY KEY,
    valor  TEXT
)""")

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username  TEXT PRIMARY KEY,
    password  TEXT NOT NULL,
    role      TEXT NOT NULL,          -- 'jugador' | 'juez'
    is_admin  INTEGER NOT NULL DEFAULT 0
)""")
conn.commit()

# SEED inicial de usuarios si la tabla está vacía --------------------
if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
    seed_users = [
        ("Jlarriva", "FioreIsQueen", "juez", 1),  # Admin‑juez
        ("Juez1", "juez123", "juez", 0),
        ("Juez2", "juez234", "juez", 0),
    ] + [(f"User{i}", f"pass{i}", "jugador", 0) for i in range(1, 21)]
    c.executemany("INSERT INTO users(username, password, role, is_admin) VALUES(?,?,?,?)", seed_users)
    conn.commit()

# Título por defecto si no existe ------------------------------------
c.execute("INSERT OR IGNORE INTO settings(clave, valor) VALUES('titulo', 'Reality Show de Frases 💬')")
conn.commit()

###############################
# 2) FUNCIONES UTILITARIAS
###############################

def load_users():
    rows = c.execute("SELECT username, password, role, is_admin FROM users").fetchall()
    return {u: {"password": p, "role": r, "is_admin": bool(a)} for u, p, r, a in rows}


def total_judges(users):
    return sum(1 for u in users.values() if u["role"] == "juez")


def get_setting(key: str, default: str = "") -> str:
    row = c.execute("SELECT valor FROM settings WHERE clave=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str):
    c.execute("REPLACE INTO settings(clave, valor) VALUES(?,?)", (key, value))
    conn.commit()


def build_unique_labels(phrases):
    """Genera etiquetas únicas (sin mostrar IDs) manejando duplicados."""
    seen, labels, mapping = {}, [], {}
    for pid, txt in phrases:
        base = txt.strip()
        suffix = ""
        while base + suffix in seen:
            suffix = f" ({seen[base]})"
            seen[base] += 1
        seen[base] = seen.get(base, 1)
        label = base + suffix
        labels.append(label)
        mapping[label] = pid
    return labels, mapping


def votos_completos(users):
    judges_needed = total_judges(users)
    count = c.execute("SELECT COUNT(DISTINCT juez) FROM votos").fetchone()[0]
    return count >= judges_needed, judges_needed - count

###############################
# 3) INTERFAZ STREAMLIT
###############################

st.set_page_config(page_title="TWOW", page_icon="💬", layout="centered")

st.title(get_setting("titulo"))

# --- LOGIN ----------------------------------------------------------
st.sidebar.header("Inicia sesión")
username = st.sidebar.text_input("Usuario")
password_input = st.sidebar.text_input("Contraseña", type="password")

users = load_users()

if username in users and users[username]["password"] == password_input:
    role = users[username]["role"]
    is_admin = users[username]["is_admin"]
    st.sidebar.success(f"Conectado como {username} ({role})")

    tab_action, tab_results = st.tabs(["Acción", "Resultados"])

    # ================================================================
    # PESTAÑA 1: ACCIÓN
    # ================================================================
    with tab_action:
        if role == "jugador":
            sent = c.execute("SELECT texto FROM frases WHERE autor=?", (username,)).fetchone()
            if sent:
                st.info("Ya enviaste tu frase de esta ronda:")
                st.write(f"**{sent[0]}**")
            else:
                new_phrase = st.text_input("Escribe tu frase:")
                if st.button("Enviar frase"):
                    if new_phrase.strip():
                        c.execute("INSERT INTO frases(texto, autor) VALUES(?,?)", (new_phrase.strip(), username))
                        conn.commit()
                        st.success("¡Frase registrada!")
                        st.experimental_rerun()
                    else:
                        st.error("La frase no puede estar vacía.")

        elif role == "juez":
            phrases = c.execute("SELECT id, texto FROM frases").fetchall()
            if not phrases:
                st.warning("Aún no hay frases para votar.")
            else:
                st.write("Arrastra / selecciona el orden de las frases (1 = mejor):")
                labels, label_to_id = build_unique_labels(phrases)
                ranking = st.multiselect("Selecciona en orden de preferencia", labels, default=[])
                if len(ranking) != len(labels):
                    st.info("Selecciona todas las frases para completar tu votación.")
                else:
                    if st.button("Registrar voto"):
                        c.execute("DELETE FROM votos WHERE juez=?", (username,))
                        for pos, lab in enumerate(ranking, start=1):
                            fid = label_to_id[lab]
                            c.execute("INSERT INTO votos(juez, frase_id, posicion) VALUES(?,?,?)", (username, fid, pos))
                        conn.commit()
                        st.success("¡Voto registrado!")

        else:
            st.error("Rol no reconocido.")

    # ================================================================
    # PESTAÑA 2: RESULTADOS y ADMINISTRACIÓN
    # ================================================================
    with tab_results:
        st.subheader("Resultados de la ronda")

        if is_admin:
            with st.expander("Panel de administración"):
                # ---- Cambiar título ----------------------------------
                new_title = st.text_input("Frase de cabecera", get_setting("titulo"))
                if st.button("Actualizar título"):
                    set_setting("titulo", new_title.strip() or "Reality Show de Frases 💬")
                    st.success("Título actualizado. Recarga la página.")

                st.markdown("---")
                # ---- Reiniciar ronda ---------------------------------
                confirm_reset = st.checkbox("Confirmo reiniciar la ronda")
                if st.button("Reiniciar ronda"):
                    if confirm_reset:
                        c.execute("DELETE FROM frases")
                        c.execute("DELETE FROM votos")
                        conn.commit()
                        st.success("Ronda reiniciada.")
                    else:
                        st.error("Marca la casilla para confirmar.")

                st.markdown("---")
                # ---- Gestión de usuarios -----------------------------
                st.subheader("Agregar participante")
                col_u, col_p = st.columns(2)
                with col_u:
                    new_user = st.text_input("Nuevo usuario", key="new_user")
                with col_p:
                    new_pass = st.text_input("Contraseña", type="password", key="new_pass")
                new_role = st.selectbox("Rol", ["jugador", "juez"], key="new_role")
                new_admin = st.checkbox("Es administrador", key="new_admin")
                if st.button("Agregar participante"):
                    if not new_user or not new_pass:
                        st.error("Usuario y contraseña no pueden estar vacíos.")
                    else:
                        try:
                            c.execute("INSERT INTO users(username, password, role, is_admin) VALUES(?,?,?,?)",
                                      (new_user.strip(), new_pass.strip(), new_role, int(new_admin)))
                            conn.commit()
                            st.success("Usuario agregado.")
                            st.experimental_rerun()
                        except sqlite3.IntegrityError:
                            st.error("Ese usuario ya existe.")

                st.markdown("---")
                st.subheader("Eliminar participante")
                users = load_users()  # refrescar
                del_candidates = [u for u in users if u != username]
                if del_candidates:
                    user_del = st.selectbox("Selecciona usuario", del_candidates, key="del_user")
                    if st.button("Eliminar usuario"):
                        c.execute("DELETE FROM users WHERE username=?", (user_del,))
                        conn.commit()
                        st.success("Usuario eliminado.")
                        st.experimental_rerun()
                else:
                    st.info("No hay otros usuarios para borrar.")

        # ----- Mostrar resultados cuando TODOS los jueces hayan votado -----
        users = load_users()  # asegurar estado actualizado
        ready, faltan = votos_completos(users)
        if ready:
            phrases = c.execute("SELECT id, texto, autor FROM frases").fetchall()
            if not phrases:
                st.info("No hay frases registradas.")
            else:
                N = len(phrases)
                puntos = {pid: 0 for pid, _, _ in phrases}
                posiciones_por_juez = {pid: [] for pid, _, _ in phrases}
                for fid, pos in c.execute("SELECT frase_id, posicion FROM votos").fetchall():
                    puntos[fid] += N + 1 - pos
                    posiciones_por_juez[fid].append(pos)

                resultados = []
                for pid, txt, autor in phrases:
                    pos_list = posiciones_por_juez[pid]
                    std = float(np.std(pos_list)) if pos_list else 0.0
                    resultados.append({"Frase": txt, "Autor": autor, "Puntos": puntos[pid], "STD": std})

                resultados.sort(key=lambda x: (x["Puntos"], x["STD"]))
                resultados = resultados[::-1]
                st.table([{k: v for k, v in r.items() if k != "STD"} for r in resultados])
        else:
            st.info(f"Esperando votos de {faltan} juez(es) para mostrar resultados…")

else:
    if username or password_input:
        st.sidebar.error("Credenciales incorrectas.")
    st.sidebar.info("Ingresa usuario y contraseña.")

