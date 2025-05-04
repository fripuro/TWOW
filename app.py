import streamlit as st
import sqlite3

# ----------------------
# Configuración de participantes y roles
# Reemplaza con los nombres y contraseñas de tus amigos.
participants = {
    "Alice": {"password": "alice123", "role": "jugador", "is_admin": False},
    "Bob":   {"password": "bob123",   "role": "jugador", "is_admin": False},
    "Cara":  {"password": "cara123",  "role": "jugador", "is_admin": False},
    "Juez1": {"password": "juez123",  "role": "juez",    "is_admin": False},
    "Juez2": {"password": "juez321",  "role": "juez",    "is_admin": False},
    "Juez3": {"password": "juez231",  "role": "juez",    "is_admin": True},  # Cuenta de administrador/jurado
}

# ----------------------
# Conexión a la base de datos SQLite (persistente en el archivo game.db)
conn = sqlite3.connect('game.db', check_same_thread=False)
c = conn.cursor()

# Crear tablas si no existen: frases y votos
c.execute('''
    CREATE TABLE IF NOT EXISTS frases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        texto TEXT NOT NULL,
        autor TEXT NOT NULL
    )
''')
c.execute('''
    CREATE TABLE IF NOT EXISTS votos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        juez TEXT NOT NULL,
        frase_id INTEGER NOT NULL,
        posicion INTEGER NOT NULL
    )
''')
conn.commit()

# ----------------------
# Interfaz de Streamlit
st.title("Reality Show de Frases Anónimo")

# Panel de login en la barra lateral
st.sidebar.header("Inicia sesión")
username = st.sidebar.text_input("Usuario")
password = st.sidebar.text_input("Contraseña", type="password")

# Verificar credenciales
if username in participants and participants[username]["password"] == password:
    role = participants[username]["role"]
    is_admin = participants[username].get("is_admin", False)
    st.sidebar.success(f"Conectado como {username} ({role})")

    # Crear pestañas: Acción y Resultados
    tab1, tab2 = st.tabs(["Acción", "Resultados"])

    # Pestaña de acción: enviar frase o votar según rol
    with tab1:
        if role == "jugador":
            # Comprobar si ya envió frase
            sent = c.execute("SELECT * FROM frases WHERE autor=?", (username,)).fetchone()
            if sent:
                st.info("Ya enviaste tu frase de esta ronda:")
                st.write(f"**{sent[1]}**")
            else:
                new_phrase = st.text_input("Escribe tu frase:")
                if st.button("Enviar frase"):
                    if new_phrase.strip():
                        c.execute(
                            "INSERT INTO frases(texto, autor) VALUES(?, ?)",
                            (new_phrase, username)
                        )
                        conn.commit()
                        st.success("¡Frase registrada con éxito!")
                    else:
                        st.error("La frase no puede estar vacía.")

        elif role == "juez":
            # Mostrar todas las frases para ranking
            phrases = c.execute("SELECT id, texto FROM frases").fetchall()
            if not phrases:
                st.warning("Aún no hay frases para votar.")
            else:
                st.write("Selecciona el orden de las frases (1 = mejor):")
                options = [f"{pid}: {txt}" for pid, txt in phrases]
                ranking = st.multiselect(
                    "Arrastra de arriba a abajo", options,
                    default=options
                )
                if st.button("Registrar voto"):
                    for pos, item in enumerate(ranking, start=1):
                        fid = int(item.split(":")[0])
                        c.execute(
                            "INSERT INTO votos(juez, frase_id, posicion) VALUES(?, ?, ?)",
                            (username, fid, pos)
                        )
                    conn.commit()
                    st.success("Voto guardado correctamente.")
        else:
            st.error("Usuario sin rol asignado.")

    # Pestaña de resultados: cálculo y tabla final
    with tab2:
        st.subheader("Resultados de la ronda")
        phrases = c.execute("SELECT id, texto, autor FROM frases").fetchall()
        votes = c.execute("SELECT frase_id, posicion FROM votos").fetchall()

        if not votes or not phrases:
            st.info("Aún no hay suficientes datos para mostrar resultados.")
        else:
            N = len(phrases)
            scores = {pid: 0 for pid, _, _ in phrases}
            for fid, pos in votes:
                scores[fid] += N + 1 - pos
            results = []
            for pid, txt, auth in phrases:
                results.append({
                    "ID": pid,
                    "Frase": txt,
                    "Autor": auth,
                    "Puntos": scores.get(pid, 0)
                })
            results.sort(key=lambda x: x["Puntos"], reverse=True)

            # Control de reinicio para administrador
            if is_admin:
                admin_exp = st.expander("Administración de ronda (solo admin)")
                with admin_exp:
                    st.write("Reiniciar borrará frases y votos actuales.")
                    confirm = st.checkbox("Confirmo reiniciar la ronda actual")
                    if st.button("Reiniciar ronda"):
                        if confirm:
                            c.execute("DELETE FROM frases")
                            c.execute("DELETE FROM votos")
                            conn.commit()
                            st.success("Ronda reiniciada con éxito.")
                        else:
                            st.error("Marca la casilla de confirmación antes de reiniciar.")
            st.table(results)

else:
    if username or password:
        st.sidebar.error("Usuario o contraseña incorrectos.")
    st.sidebar.info("Ingresa tus credenciales para continuar.")
