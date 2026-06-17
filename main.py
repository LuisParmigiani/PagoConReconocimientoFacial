import cv2
import face_recognition
import sqlite3
import os
import time
import numpy as np
import tkinter as tk
from tkinter import messagebox, simpledialog
from PIL import Image, ImageTk

# --- 1. CONFIGURACIÓN DE BASE DE DATOS (SQLite3) ---
def inicializar_db():
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            saldo REAL NOT NULL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()

def actualizar_saldo(nombre, monto_a_cobrar):
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    cursor.execute("SELECT saldo FROM usuarios WHERE nombre = ?", (nombre,))
    resultado = cursor.fetchone()

    if resultado is None:
        conn.close()
        return False, "Usuario no registrado en DB."

    saldo_actual = resultado[0]
    if saldo_actual >= monto_a_cobrar:
        nuevo_saldo = saldo_actual - monto_a_cobrar
        cursor.execute("UPDATE usuarios SET saldo = ? WHERE nombre = ?", (nuevo_saldo, nombre))
        conn.commit()
        conn.close()
        return True, nuevo_saldo
    else:
        conn.close()
        return False, f"Saldo insuficiente. Tiene ${saldo_actual:.2f}"

def registrar_usuario_en_db(nombre, saldo_inicial=1000.0):
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO usuarios (nombre, saldo) VALUES (?, ?)", (nombre, saldo_inicial))
    conn.commit()
    conn.close()

def obtener_usuarios_db():
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, saldo FROM usuarios ORDER BY id ASC")
    usuarios = cursor.fetchall()
    conn.close()
    return usuarios

def obtener_ruta_imagen_usuario(nombre):
    for extension in (".jpg", ".jpeg", ".png"):
        ruta = os.path.join("dataset_caras", f"{nombre}{extension}")
        if os.path.exists(ruta):
            return ruta
    return None

def obtener_thumbnail_usuario(nombre, tamano=(86, 86)):
    ruta = obtener_ruta_imagen_usuario(nombre)
    imagen = None

    if ruta:
        try:
            imagen = Image.open(ruta).convert("RGB")
            imagen.thumbnail(tamano)
        except Exception:
            imagen = None

    if imagen is None:
        imagen = Image.new("RGB", tamano, (220, 220, 220))
    else:
        fondo = Image.new("RGB", tamano, (220, 220, 220))
        offset_x = (tamano[0] - imagen.width) // 2
        offset_y = (tamano[1] - imagen.height) // 2
        fondo.paste(imagen, (offset_x, offset_y))
        imagen = fondo

    return ImageTk.PhotoImage(imagen)

def modificar_usuario(nombre_actual, nuevo_nombre=None, nuevo_saldo=None):
    nombre_nuevo = nombre_actual if nuevo_nombre is None else nuevo_nombre.strip()
    if not nombre_nuevo:
        return False, "El nombre no puede quedar vacío."

    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM usuarios WHERE nombre = ?", (nombre_actual,))
    usuario = cursor.fetchone()
    if usuario is None:
        conn.close()
        return False, "El usuario ya no existe."

    if nombre_nuevo != nombre_actual:
        cursor.execute("SELECT 1 FROM usuarios WHERE nombre = ?", (nombre_nuevo,))
        if cursor.fetchone() is not None:
            conn.close()
            return False, f"Ya existe un usuario llamado '{nombre_nuevo}'."

    ruta_origen = obtener_ruta_imagen_usuario(nombre_actual)
    ruta_destino = None
    if ruta_origen:
        _, extension = os.path.splitext(ruta_origen)
        ruta_destino = os.path.join("dataset_caras", f"{nombre_nuevo}{extension}")
        if nombre_nuevo != nombre_actual and os.path.exists(ruta_destino):
            conn.close()
            return False, f"Ya existe el archivo de dataset para '{nombre_nuevo}'."

    try:
        if nombre_nuevo != nombre_actual:
            cursor.execute("UPDATE usuarios SET nombre = ? WHERE nombre = ?", (nombre_nuevo, nombre_actual))

        if nuevo_saldo is not None:
            cursor.execute("UPDATE usuarios SET saldo = ? WHERE nombre = ?", (float(nuevo_saldo), nombre_nuevo))

        if ruta_origen and ruta_destino and ruta_origen != ruta_destino:
            os.rename(ruta_origen, ruta_destino)

        conn.commit()
        conn.close()
        return True, nombre_nuevo
    except Exception as error:
        conn.rollback()
        conn.close()
        return False, f"No se pudo modificar el usuario: {error}"

def ingresar_dinero_usuario(nombre, monto):
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    cursor.execute("SELECT saldo FROM usuarios WHERE nombre = ?", (nombre,))
    resultado = cursor.fetchone()
    if resultado is None:
        conn.close()
        return False, "Usuario no registrado en DB."

    nuevo_saldo = float(resultado[0]) + float(monto)
    cursor.execute("UPDATE usuarios SET saldo = ? WHERE nombre = ?", (nuevo_saldo, nombre))
    conn.commit()
    conn.close()
    return True, nuevo_saldo

def eliminar_usuario_completo(nombre):
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE nombre = ?", (nombre,))
    conn.commit()
    conn.close()

    if not os.path.exists("dataset_caras"):
        return True

    eliminados = False
    for extension in (".jpg", ".jpeg", ".png"):
        ruta = os.path.join("dataset_caras", f"{nombre}{extension}")
        if os.path.exists(ruta):
            os.remove(ruta)
            eliminados = True

    return True if eliminados or True else False

# --- 2. CARGA DE MODELOS FACIALES ---
def cargar_dataset(ruta_dataset="dataset_caras"):
    encodings_conocidos = []
    nombres_conocidos = []

    if not os.path.exists(ruta_dataset):
        os.makedirs(ruta_dataset)

    for archivo in os.listdir(ruta_dataset):
        if archivo.endswith((".jpg", ".jpeg", ".png")):
            ruta_imagen = os.path.join(ruta_dataset, archivo)
            imagen = face_recognition.load_image_file(ruta_imagen)
            encodings = face_recognition.face_encodings(imagen, num_jitters=10)
            if len(encodings) > 0:
                encodings_conocidos.append(encodings[0])
                nombre = os.path.splitext(archivo)[0]
                nombres_conocidos.append(nombre)
                registrar_usuario_en_db(nombre)

    return encodings_conocidos, nombres_conocidos

# --- 3. REGISTRO DE NUEVO USUARIO CON CÁMARA ---
def registrar_nuevo_usuario(encodings_conocidos, nombres_conocidos):
    ventana_dialogo = tk.Tk()
    ventana_dialogo.withdraw()

    nombre_usuario = simpledialog.askstring("Registro de Usuario", "Ingrese el nombre del usuario:")
    ventana_dialogo.destroy()

    if not nombre_usuario or nombre_usuario.strip() == "":
        messagebox.showwarning("Cancelado", "Registro cancelado: no ingresó nombre.")
        return False

    nombre_usuario = nombre_usuario.strip()

    ruta_imagen = os.path.join("dataset_caras", f"{nombre_usuario}.jpg")
    if os.path.exists(ruta_imagen):
        messagebox.showwarning("Usuario Existente", f"El usuario '{nombre_usuario}' ya está registrado.")
        return False

    cap = cv2.VideoCapture(0)
    capturado = False

    while not capturado:
        ret, frame = cap.read()
        if not ret:
            messagebox.showerror("Error", "No se pudo acceder a la cámara.")
            cap.release()
            cv2.destroyAllWindows()
            return False

        frame_pequeno = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_frame_pequeno = cv2.cvtColor(frame_pequeno, cv2.COLOR_BGR2RGB)
        ubicaciones_caras = face_recognition.face_locations(rgb_frame_pequeno, model="hog")

        for top, right, bottom, left in ubicaciones_caras:
            top, right, bottom, left = top * 2, right * 2, bottom * 2, left * 2
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

        cv2.putText(frame, "SPACE para capturar  |  Q para cancelar", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
        cv2.putText(frame, f"Usuario: {nombre_usuario}", (10, 65),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        estado = "Rostro detectado" if ubicaciones_caras else "No se detecta rostro"
        color_e = (0, 255, 0) if ubicaciones_caras else (0, 0, 255)
        cv2.putText(frame, estado, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color_e, 2)

        cv2.imshow(f'Registro - {nombre_usuario}', frame)
        tecla = cv2.waitKey(1) & 0xFF

        if tecla == ord(' '):
            if not ubicaciones_caras:
                messagebox.showwarning("Error", "No se detecta rostro. Intente de nuevo.")
            else:
                encodings_captura = face_recognition.face_encodings(rgb_frame_pequeno, ubicaciones_caras)
                if len(encodings_captura) > 0 and len(encodings_conocidos) > 0:
                    distancias = face_recognition.face_distance(encodings_conocidos, encodings_captura[0])
                    mejor_idx = np.argmin(distancias)
                    if distancias[mejor_idx] < 0.45:
                        nombre_dup = nombres_conocidos[mejor_idx]
                        cap.release()
                        cv2.destroyAllWindows()
                        messagebox.showwarning(
                            "Rostro ya registrado",
                            f"Esta persona ya existe como '{nombre_dup}'.\nNo se puede registrar dos veces."
                        )
                        return False

                if not os.path.exists("dataset_caras"):
                    os.makedirs("dataset_caras")

                cv2.imwrite(ruta_imagen, frame)
                registrar_usuario_en_db(nombre_usuario, saldo_inicial=1000.0)
                messagebox.showinfo("Exito", f"Usuario '{nombre_usuario}' registrado.\nSaldo inicial: $1000")
                capturado = True

        elif tecla == ord('q'):
            messagebox.showinfo("Cancelado", "Registro cancelado.")
            cap.release()
            cv2.destroyAllWindows()
            return False

    cap.release()
    cv2.destroyAllWindows()
    return True

# --- 4. VERIFICACIÓN DE VIDA (rPPG diferencial G-R + consistencia temporal) ---
def _señal_diff(R, G, B):
    """
    (G-R)/(G+R+B) normalizada: cancela variaciones de pantalla que afectan
    R y G por igual, y amplifica el pulso real donde G y R van en fases opuestas.
    """
    d = (G - R) / (G + R + B + 1e-6)
    return d - d.mean()

def _analizar_ventana(señal, fps):
    """Devuelve (ratio_hr, peak_snr, freq_dominante) para un fragmento."""
    n  = len(señal)
    sw = (señal - np.mean(señal)) * np.hanning(n)
    esp  = np.abs(np.fft.rfft(sw))
    freq = np.fft.rfftfreq(n, d=1.0 / fps)
    m_hr   = (freq >= 0.7) & (freq <= 3.0)
    m_util = (freq >= 0.15) & (freq <= 5.0)
    pot_hr   = np.sum(esp[m_hr] ** 2)
    pot_util = np.sum(esp[m_util] ** 2)
    ratio_hr = pot_hr / pot_util if pot_util > 0 else 0.0
    hr_esp   = esp[m_hr]
    if hr_esp.size > 0 and np.mean(hr_esp ** 2) > 0:
        peak_snr = float(np.max(hr_esp) ** 2 / np.mean(hr_esp ** 2))
        freq_dom = float(freq[m_hr][np.argmax(hr_esp)])
    else:
        peak_snr, freq_dom = 0.0, 0.0
    return ratio_hr, peak_snr, freq_dom

def verificar_liveness_rppg(cap, duracion_segundos=10, encodings_conocidos=None, nombres_conocidos=None):
    """
    Cuatro condiciones simultáneas sobre la señal diferencial (G-R)/(G+R+B):

      1. std_diff   ≥ umbral  → la señal no es plana (hay variación real)
      2. ratio_hr   ≥ umbral  → energía en banda cardíaca 0.7-3 Hz (42-180 bpm)
      3. peak_snr   ≥ umbral  → pico espectral nítido, no ruido disperso
      4. consistencia≥ umbral → la frecuencia dominante es estable entre ventanas

    La condición 4 es la clave contra fotos en pantallas:
      - Pulso cardíaco: mismo Hz en TODAS las ventanas temporales
      - Temblor de mano sujetando el celular: la frecuencia salta entre ventanas
        porque la persona ajusta el agarre o la mano se cansa
    """
    VENTANA = "Verificacion Biometrica"

    señales_r, señales_g, señales_b = [], [], []
    tiempo_inicio = time.time()
    frame_count = 0
    votos_recono = {}
    VOTOS_MIN_RECONO = 5

    while True:
        t = time.time() - tiempo_inicio
        if t >= duracion_segundos:
            break

        ret, frame = cap.read()
        if not ret:
            break

        frame_d = frame.copy()
        h_f, w_f = frame_d.shape[:2]
        frame_count += 1

        frame_peq = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_peq   = cv2.cvtColor(frame_peq, cv2.COLOR_BGR2RGB)
        ubicaciones = face_recognition.face_locations(rgb_peq, model="hog")

        if len(ubicaciones) > 0:
            top, right, bottom, left = ubicaciones[0]
            top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4

            roi = frame[top:bottom, left:right]
            if roi.size > 0:
                h_r, w_r = roi.shape[:2]
                iy, ix = int(h_r * 0.15), int(w_r * 0.10)
                roi_piel = roi[iy:h_r - iy, ix:w_r - ix]
                if roi_piel.size > 0:
                    señales_b.append(float(np.mean(roi_piel[:, :, 0])))
                    señales_g.append(float(np.mean(roi_piel[:, :, 1])))
                    señales_r.append(float(np.mean(roi_piel[:, :, 2])))

            cv2.rectangle(frame_d, (left, top), (right, bottom), (0, 200, 255), 2)
            cv2.putText(frame_d, "Leyendo pulso...", (left, top - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)

            # Reconocimiento simultáneo al liveness (cada 5 frames, usando frame completo)
            if frame_count % 5 == 0 and encodings_conocidos:
                rgb_full = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                encs = face_recognition.face_encodings(rgb_full, [(top, right, bottom, left)])
                if encs:
                    dist = face_recognition.face_distance(encodings_conocidos, encs[0])
                    if len(dist) > 0:
                        idx = np.argmin(dist)
                        if dist[idx] < 0.45:
                            nom = nombres_conocidos[idx]
                            votos_recono[nom] = votos_recono.get(nom, 0) + 1

            if votos_recono:
                mejor_nom = max(votos_recono, key=votos_recono.get)
                v = votos_recono[mejor_nom]
                color_id = (50, 255, 50) if v >= VOTOS_MIN_RECONO else (0, 200, 255)
                cv2.putText(frame_d, f"ID: {mejor_nom}  ({v}/{VOTOS_MIN_RECONO})",
                           (left, bottom + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color_id, 2)
        else:
            cv2.putText(frame_d, "Acerque el rostro a la camara", (10, h_f // 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)

        # ── Header ──
        cv2.rectangle(frame_d, (0, 0), (w_f, 45), (30, 30, 30), -1)
        cv2.putText(frame_d, "VERIFICANDO PERSONA REAL  (rPPG)", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        cv2.putText(frame_d, "Permanezca quieto con buena iluminacion", (10, h_f - 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # ── Barra de progreso ──
        bar_y    = h_f - 30
        progreso = min(t / duracion_segundos, 1.0)
        barra_x  = 10 + int((w_f - 20) * progreso)
        cv2.rectangle(frame_d, (10, bar_y), (w_f - 10, bar_y + 18), (60, 60, 60), -1)
        cv2.rectangle(frame_d, (10, bar_y), (barra_x,  bar_y + 18), (0, 180, 100), -1)
        cv2.rectangle(frame_d, (10, bar_y), (w_f - 10, bar_y + 18), (160, 160, 160), 1)
        seg_rest = max(0, int(duracion_segundos - t + 0.99))
        cv2.putText(frame_d, f"{seg_rest}s", (w_f - 42, bar_y + 14),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        # ── Mini-gráfico de la señal diferencial G-R ──
        n_sig = min(len(señales_g), len(señales_r), len(señales_b))
        if n_sig > 5:
            sig_disp = _señal_diff(
                np.array(señales_r[-80:]),
                np.array(señales_g[-80:]),
                np.array(señales_b[-80:])
            )
            gx, gy, gw, gh = w_f - 158, h_f - 128, 143, 62
            cv2.rectangle(frame_d, (gx - 2, gy - 18), (gx + gw + 2, gy + gh + 2), (40, 40, 40), -1)
            cv2.putText(frame_d, "Señal diferencial G-R", (gx, gy - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.32, (100, 255, 150), 1)
            s_min, s_max = sig_disp.min(), sig_disp.max()
            s_rng = max(s_max - s_min, 1e-6)
            pts = []
            for i, v in enumerate(sig_disp):
                px = gx + int(i * gw / len(sig_disp))
                py = gy + gh - int((v - s_min) / s_rng * gh)
                pts.append([px, py])
            pts_arr = np.array(pts, dtype=np.int32)
            if len(pts_arr) > 1:
                cv2.polylines(frame_d, [pts_arr], isClosed=False, color=(0, 230, 130), thickness=1)

        cv2.imshow(VENTANA, frame_d)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            cv2.destroyWindow(VENTANA)
            return False, 0.0, "", None

    cv2.destroyWindow(VENTANA)

    n_min = min(len(señales_g), len(señales_r), len(señales_b))
    if n_min < 60:
        return False, 0.0, "Pocas muestras", None

    R = np.array(señales_r[:n_min], dtype=np.float64)
    G = np.array(señales_g[:n_min], dtype=np.float64)
    B = np.array(señales_b[:n_min], dtype=np.float64)
    fps_real = n_min / duracion_segundos

    # ── Señal diferencial global ──────────────────────────────────────────
    diff = _señal_diff(R, G, B)
    std_diff = float(np.std(diff))

    ratio_hr, peak_snr, _ = _analizar_ventana(diff, fps_real)

    # ── Consistencia temporal ─────────────────────────────────────────────
    # Ventanas de 3 s con paso de 1.5 s → 5-6 ventanas en 10 s.
    # Un corazón real mantiene la misma frecuencia en todas las ventanas.
    # Un temblor de mano cambia de frecuencia a medida que la persona
    # ajusta el agarre o cansa el brazo.
    win_len  = int(4.0 * fps_real)   # 4 s → resolución 0.25 Hz, más estable que 3 s
    win_paso = int(1.5 * fps_real)
    freqs_dom = []
    i = 0
    while i + win_len <= n_min:
        _, _, fd = _analizar_ventana(diff[i:i + win_len], fps_real)
        if fd > 0:
            freqs_dom.append(fd)
        i += win_paso

    consistencia = max(0.0, 1.0 - np.std(freqs_dom) / 0.40) if len(freqs_dom) >= 3 else 0.0

    # ── Score y decisión ──────────────────────────────────────────────────
    score = round(
        0.25 * min(std_diff  / 0.0008, 1.0) +
        0.25 * min(ratio_hr  / 0.25,   1.0) +
        0.20 * min(peak_snr  / 4.0,    1.0) +
        0.30 * consistencia,
        3
    )

    # Umbrales calibrados para webcam real (señal rPPG es débil en la vida real)
    STD_UMBRAL          = 0.0002   # antes 0.0004
    RATIO_UMBRAL        = 0.10     # antes 0.15
    SNR_UMBRAL          = 1.5      # antes 2.5
    CONSISTENCIA_UMBRAL = 0.20     # antes 0.45

    ok_std    = std_diff     >= STD_UMBRAL
    ok_ratio  = ratio_hr     >= RATIO_UMBRAL
    ok_snr    = peak_snr     >= SNR_UMBRAL
    ok_consist= consistencia >= CONSISTENCIA_UMBRAL
    es_vivo   = ok_std and ok_ratio and ok_snr and ok_consist

    diag = (
        f"std={std_diff:.5f}({'OK' if ok_std else 'FAIL'})  "
        f"ratio={ratio_hr:.3f}({'OK' if ok_ratio else 'FAIL'})  "
        f"snr={peak_snr:.2f}({'OK' if ok_snr else 'FAIL'})  "
        f"consist={consistencia:.3f}({'OK' if ok_consist else 'FAIL'})\n"
        f"muestras={n_min}  fps={fps_real:.1f}"
    )
    print(f"[rPPG] {diag}")   # visible en la terminal para calibración

    usuario_reconocido = None
    if votos_recono:
        mejor_nom = max(votos_recono, key=votos_recono.get)
        if votos_recono[mejor_nom] >= VOTOS_MIN_RECONO:
            usuario_reconocido = mejor_nom

    return es_vivo, score, diag, usuario_reconocido

# --- 5. LÓGICA DE COBRO CON OPENCV ---
def iniciar_escaneo(monto, encodings_conocidos, nombres_conocidos):
    cap = cv2.VideoCapture(0)

    # ── ETAPA 1: Verificación de liveness (rPPG diferencial) ────────────────
    es_vivo, score_liveness, diag_liveness, usuario_reconocido = verificar_liveness_rppg(
        cap, encodings_conocidos=encodings_conocidos, nombres_conocidos=nombres_conocidos
    )

    if not es_vivo:
        cap.release()
        cv2.destroyAllWindows()
        messagebox.showerror(
            "Verificacion Fallida",
            f"No se detecto señal de vida  (score: {score_liveness:.3f})\n\n"
            f"{diag_liveness}\n\n"
            "Causas posibles:\n"
            "  • Foto o pantalla\n"
            "  • Poca iluminacion\n"
            "  • Movimiento excesivo\n\n"
            "Intentelo de nuevo quieto y con buena luz."
        )
        return

    # Pantalla de confirmacion
    ret, frame_ok = cap.read()
    if ret:
        h_ok, w_ok = frame_ok.shape[:2]
        overlay = frame_ok.copy()
        cv2.rectangle(overlay, (0, 0), (w_ok, h_ok), (0, 60, 0), -1)
        cv2.addWeighted(overlay, 0.35, frame_ok, 0.65, 0, frame_ok)
        cv2.putText(frame_ok, "PERSONA REAL VERIFICADA", (w_ok // 2 - 195, h_ok // 2 - 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 100), 3)
        cv2.putText(frame_ok, f"Score de liveness: {score_liveness:.3f}", (w_ok // 2 - 130, h_ok // 2 + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 255, 180), 2)
        cv2.imshow("Liveness OK", frame_ok)
        cv2.waitKey(1400)
        cv2.destroyWindow("Liveness OK")

    # ── ETAPA 2: ya resuelta durante liveness ────────────────────────────────
    if not usuario_reconocido:
        cap.release()
        cv2.destroyAllWindows()
        messagebox.showwarning(
            "No Identificado",
            "Se verificó que eres una persona real,\n"
            "pero no se pudo identificar a nadie.\n\n"
            "Asegurate de estar registrado y mirar\n"
            "directamente a la cámara durante la verificación."
        )
        return

    cap.release()
    cv2.destroyAllWindows()

    exito, resultado = actualizar_saldo(usuario_reconocido, monto)
    if exito:
        messagebox.showinfo(
            "Pago Aprobado",
            f"Cobro exitoso a {usuario_reconocido}\n"
            f"Monto cobrado:    ${monto:.2f}\n"
            f"Saldo restante:   ${resultado:.2f}\n\n"
            f"Score de liveness: {score_liveness:.3f}"
        )
    else:
        messagebox.showerror("Pago Rechazado", f"Error con {usuario_reconocido}:\n{resultado}")

# --- 6. INTERFAZ GRÁFICA (Tkinter) ---
def arrancar_app():
    inicializar_db()

    def actualizar_usuarios_y_recargar():
        nonlocal encodings_conocidos, nombres_conocidos
        encodings_conocidos, nombres_conocidos = cargar_dataset()
        lbl_usuarios.config(text=f"Usuarios cargados: {len(nombres_conocidos)}")

    def abrir_gestion_usuarios():
        ventana_gestion = tk.Toplevel(ventana)
        ventana_gestion.title("Ver o Modificar Usuarios")
        ventana_gestion.geometry("1100x650")
        ventana_gestion.configure(bg="#f4f4f4")
        ventana_gestion.transient(ventana)
        ventana_gestion.grab_set()

        referencias_imagenes = []

        cabecera = tk.Frame(ventana_gestion, bg="#f4f4f4")
        cabecera.pack(fill="x", padx=16, pady=(16, 10))

        tk.Label(cabecera, text="Ver o Modificar Usuarios", font=("Arial", 18, "bold"), bg="#f4f4f4").pack(side="left")
        tk.Button(
            cabecera,
            text="Volver",
            command=ventana_gestion.destroy,
            bg="#666666",
            fg="white",
            font=("Arial", 10, "bold"),
            width=12,
            relief="flat"
        ).pack(side="right")

        info = tk.Label(
            ventana_gestion,
            text="Los cambios se reflejan automáticamente en la lista y en el dataset.",
            bg="#f4f4f4",
            fg="#555555",
            font=("Arial", 10)
        )
        info.pack(anchor="w", padx=18, pady=(0, 8))

        marco_principal = tk.Frame(ventana_gestion, bg="#f4f4f4")
        marco_principal.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        canvas = tk.Canvas(marco_principal, bg="#ffffff", highlightthickness=0)
        scrollbar = tk.Scrollbar(marco_principal, orient="vertical", command=canvas.yview)
        contenedor = tk.Frame(canvas, bg="#ffffff")

        contenedor.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=contenedor, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        encabezados = ["ID", "Nombre", "Saldo", "Foto", "Acciones"]
        anchos = [60, 220, 120, 140, 460]
        for columna, (titulo, ancho) in enumerate(zip(encabezados, anchos)):
            tk.Label(
                contenedor,
                text=titulo,
                bg="#ececec",
                fg="#222222",
                font=("Arial", 10, "bold"),
                width=max(1, ancho // 10),
                anchor="w",
                padx=10,
                pady=8,
                relief="solid",
                borderwidth=1,
            ).grid(row=0, column=columna, sticky="nsew")

        for columna, ancho in enumerate(anchos):
            contenedor.grid_columnconfigure(columna, weight=1, minsize=ancho)

        def refrescar_listado():
            referencias_imagenes.clear()
            for widget in contenedor.winfo_children():
                if int(widget.grid_info().get("row", 0)) > 0:
                    widget.destroy()

            usuarios = obtener_usuarios_db()
            if not usuarios:
                tk.Label(
                    contenedor,
                    text="No hay usuarios cargados.",
                    bg="#ffffff",
                    fg="#666666",
                    font=("Arial", 11),
                    anchor="w",
                    padx=10,
                    pady=18,
                ).grid(row=1, column=0, columnspan=5, sticky="ew")
                return

            for fila, (usuario_id, nombre, saldo) in enumerate(usuarios, start=1):
                fondo = "#ffffff" if fila % 2 else "#fafafa"
                tk.Label(contenedor, text=str(usuario_id), bg=fondo, anchor="w", padx=10, pady=12, relief="solid", borderwidth=1).grid(row=fila, column=0, sticky="nsew")
                tk.Label(contenedor, text=nombre, bg=fondo, anchor="w", padx=10, pady=12, relief="solid", borderwidth=1).grid(row=fila, column=1, sticky="nsew")
                tk.Label(contenedor, text=f"${float(saldo):.2f}", bg=fondo, anchor="w", padx=10, pady=12, relief="solid", borderwidth=1).grid(row=fila, column=2, sticky="nsew")

                foto_frame = tk.Frame(contenedor, bg=fondo, relief="solid", borderwidth=1)
                foto_frame.grid(row=fila, column=3, sticky="nsew")
                thumb = obtener_thumbnail_usuario(nombre)
                referencias_imagenes.append(thumb)
                tk.Label(foto_frame, image=thumb, bg=fondo).pack(padx=10, pady=8)

                acciones = tk.Frame(contenedor, bg=fondo, relief="solid", borderwidth=1)
                acciones.grid(row=fila, column=4, sticky="nsew")

                def ejecutar_modificar(nombre_actual=nombre):
                    nuevo_nombre = simpledialog.askstring(
                        "Modificar usuario",
                        "Nuevo nombre (dejar vacío para mantener el actual):",
                        initialvalue=nombre_actual,
                        parent=ventana_gestion,
                    )
                    if nuevo_nombre is None:
                        return

                    nuevo_nombre = nuevo_nombre.strip() or nombre_actual
                    nuevo_saldo = simpledialog.askfloat(
                        "Modificar saldo",
                        "Nuevo saldo actual (cancelar para mantener el actual):",
                        initialvalue=float(saldo),
                        parent=ventana_gestion,
                    )

                    exito, resultado = modificar_usuario(nombre_actual, nuevo_nombre=nuevo_nombre, nuevo_saldo=nuevo_saldo)
                    if exito:
                        messagebox.showinfo("Usuario modificado", f"Usuario actualizado a '{resultado}'.")
                        ventana_gestion.after(0, forzar_recarga_total)
                    else:
                        messagebox.showerror("Error", resultado)

                def ejecutar_ingreso(nombre_actual=nombre):
                    monto = simpledialog.askfloat(
                        "Ingresar dinero",
                        "Monto a ingresar:",
                        parent=ventana_gestion,
                    )
                    if monto is None:
                        return
                    if monto <= 0:
                        messagebox.showwarning("Monto inválido", "El monto debe ser mayor que cero.")
                        return

                    exito, resultado = ingresar_dinero_usuario(nombre_actual, monto)
                    if exito:
                        messagebox.showinfo("Saldo actualizado", f"Nuevo saldo de '{nombre_actual}': ${resultado:.2f}")
                        ventana_gestion.after(0, forzar_recarga_total)
                    else:
                        messagebox.showerror("Error", resultado)

                def ejecutar_eliminar(nombre_actual=nombre):
                    confirmar = messagebox.askyesno(
                        "Eliminar usuario",
                        f"¿Seguro que quieres eliminar a '{nombre_actual}' y su dataset?",
                        parent=ventana_gestion,
                    )
                    if not confirmar:
                        return

                    eliminar_usuario_completo(nombre_actual)
                    ventana_gestion.after(0, forzar_recarga_total)

                tk.Button(acciones, text="Modificar", command=ejecutar_modificar, bg="#f0ad4e", fg="white", font=("Arial", 9, "bold"), width=12, relief="flat").pack(side="left", padx=6, pady=10)
                tk.Button(acciones, text="Ingresar dinero", command=ejecutar_ingreso, bg="#5cb85c", fg="white", font=("Arial", 9, "bold"), width=14, relief="flat").pack(side="left", padx=6, pady=10)
                tk.Button(acciones, text="Eliminar", command=ejecutar_eliminar, bg="#d9534f", fg="white", font=("Arial", 9, "bold"), width=10, relief="flat").pack(side="left", padx=6, pady=10)

        def forzar_recarga_total():
            actualizar_usuarios_y_recargar()
            refrescar_listado()
            ventana_gestion.update_idletasks()
            canvas.yview_moveto(0)

        refrescar_listado()
        ventana_gestion.after(50, lambda: canvas.yview_moveto(0))

    encodings_conocidos, nombres_conocidos = cargar_dataset()

    ventana = tk.Tk()
    ventana.title("Sistema de Pago Biométrico")
    ventana.geometry("450x420")
    ventana.eval('tk::PlaceWindow . center')

    tk.Label(ventana, text="Punto de Venta", font=("Arial", 18, "bold")).pack(pady=18)
    tk.Label(ventana, text="Protegido con verificacion de persona real (rPPG diferencial)",
             font=("Arial", 9), fg="#555").pack()

    lbl_usuarios = tk.Label(ventana, text=f"Usuarios cargados: {len(nombres_conocidos)}",
                            font=("Arial", 12))
    lbl_usuarios.pack(pady=8)

    def boton_cobrar_click():
        if len(nombres_conocidos) == 0:
            messagebox.showwarning("Sin Usuarios", "No hay usuarios registrados. Registre uno primero.")
            return
        monto = simpledialog.askfloat("Monto", "Cuanto desea cobrar?")
        if monto and monto > 0:
            iniciar_escaneo(monto, encodings_conocidos, nombres_conocidos)

    def boton_registrar_click():
        if registrar_nuevo_usuario(encodings_conocidos, nombres_conocidos):
            actualizar_usuarios_y_recargar()

    btn_registrar = tk.Button(ventana, text="Registrar Nuevo Usuario",
                              command=boton_registrar_click,
                              bg="#27ae60", fg="white", font=("Arial", 11), width=28, height=2)
    btn_registrar.pack(pady=12)

    btn_cobrar = tk.Button(ventana, text="Iniciar Escaneo y Cobrar",
                           command=boton_cobrar_click,
                           bg="#2980b9", fg="white", font=("Arial", 11), width=28, height=2)
    btn_cobrar.pack(pady=12)

    btn_gestion = tk.Button(ventana, text="Ver o Modificar Usuarios",
                            command=abrir_gestion_usuarios,
                            bg="#777777", fg="white", font=("Arial", 11), width=28, height=2)
    btn_gestion.pack(pady=8)

    tk.Label(ventana, text="(Asegurate de tener buena iluminacion y camara conectada)",
             font=("Arial", 9), fg="gray").pack(pady=8)

    ventana.mainloop()


if __name__ == "__main__":
    arrancar_app()
