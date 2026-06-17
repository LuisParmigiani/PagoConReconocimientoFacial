import cv2
import face_recognition
import sqlite3
import os
import numpy as np
import tkinter as tk
from tkinter import messagebox, simpledialog

# --- 1. CONFIGURACIÓN DE BASE DE DATOS (SQLite3) ---
def inicializar_db():
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    # Crear tabla de usuarios
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
        return False, f"Saldo insuficiente. Tiene ${saldo_actual}"

def registrar_usuario_en_db(nombre, saldo_inicial=1000.0):
    conn = sqlite3.connect('banco.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO usuarios (nombre, saldo) VALUES (?, ?)", (nombre, saldo_inicial))
    conn.commit()
    conn.close()

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
            
            # Intentar extraer el rostro (asume que hay 1 sola cara en la foto)
            encodings = face_recognition.face_encodings(imagen)
            if len(encodings) > 0:
                encodings_conocidos.append(encodings[0])
                nombre = os.path.splitext(archivo)[0]
                nombres_conocidos.append(nombre)
                registrar_usuario_en_db(nombre) # Asegurar que esté en la DB
            
    return encodings_conocidos, nombres_conocidos

# --- 3. REGISTRO DE NUEVO USUARIO CON CÁMARA ---
def registrar_nuevo_usuario():
    # Pedir nombre del usuario
    ventana_dialogo = tk.Tk()
    ventana_dialogo.withdraw()
    
    nombre_usuario = simpledialog.askstring("Registro de Usuario", "Ingrese el nombre del usuario:")
    ventana_dialogo.destroy()
    
    if not nombre_usuario or nombre_usuario.strip() == "":
        messagebox.showwarning("Cancelado", "Registro cancelado: no ingresó nombre.")
        return False
    
    nombre_usuario = nombre_usuario.strip()
    
    # Verificar si el usuario ya existe
    ruta_imagen = os.path.join("dataset_caras", f"{nombre_usuario}.jpg")
    if os.path.exists(ruta_imagen):
        messagebox.showwarning("Usuario Existente", f"El usuario '{nombre_usuario}' ya está registrado.")
        return False
    
    # Abrir cámara para capturar rostro
    cap = cv2.VideoCapture(0)
    
    capturado = False
    mensaje_info = "Presione SPACE para capturar, 'q' para cancelar"
    
    while not capturado:
        ret, frame = cap.read()
        if not ret:
            messagebox.showerror("Error", "No se pudo acceder a la cámara.")
            cap.release()
            cv2.destroyAllWindows()
            return False
        
        # Detectar rostros en el frame
        frame_pequeno = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_frame_pequeno = cv2.cvtColor(frame_pequeno, cv2.COLOR_BGR2RGB)
        ubicaciones_caras = face_recognition.face_locations(rgb_frame_pequeno, model="hog")
        
        # Dibujar rectángulos alrededor de los rostros detectados
        for top, right, bottom, left in ubicaciones_caras:
            top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        
        # Mostrar instrucciones
        cv2.putText(frame, mensaje_info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"Usuario: {nombre_usuario}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        if len(ubicaciones_caras) == 0:
            cv2.putText(frame, "⚠ No se detecta rostro", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        else:
            cv2.putText(frame, f"✓ Rostro detectado", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        cv2.imshow(f'Registro - {nombre_usuario}', frame)
        
        tecla = cv2.waitKey(1) & 0xFF
        
        if tecla == ord(' '):  # SPACE para capturar
            if len(ubicaciones_caras) > 0:
                # Guardar la imagen
                if not os.path.exists("dataset_caras"):
                    os.makedirs("dataset_caras")
                
                cv2.imwrite(ruta_imagen, frame)
                
                # Registrar en DB
                registrar_usuario_en_db(nombre_usuario, saldo_inicial=1000.0)
                
                messagebox.showinfo("Éxito", f"Usuario '{nombre_usuario}' registrado correctamente.\nSaldo inicial: $1000")
                capturado = True
            else:
                messagebox.showwarning("Error", "No se detecta rostro. Intente de nuevo.")
        
        elif tecla == ord('q'):  # Q para cancelar
            messagebox.showinfo("Cancelado", "Registro cancelado.")
            cap.release()
            cv2.destroyAllWindows()
            return False
    
    cap.release()
    cv2.destroyAllWindows()
    return True

# --- 4. LÓGICA DE COBRO CON OPENCV ---
def iniciar_escaneo(monto, encodings_conocidos, nombres_conocidos):
    cap = cv2.VideoCapture(0)
    
    usuario_reconocido = None
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Achicar el frame para procesar más rápido (ideal para procesadores normales)
        frame_pequeno = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_frame_pequeno = cv2.cvtColor(frame_pequeno, cv2.COLOR_BGR2RGB)
        
        # Encontrar caras en el frame actual
        ubicaciones_caras = face_recognition.face_locations(rgb_frame_pequeno, model="hog")
        encodings_actuales = face_recognition.face_encodings(rgb_frame_pequeno, ubicaciones_caras)
        
        for encoding_cara, ubicacion_cara in zip(encodings_actuales, ubicaciones_caras):
            # Comparar con nuestra base de datos en RAM
            distancias = face_recognition.face_distance(encodings_conocidos, encoding_cara)
            
            if len(distancias) > 0:
                mejor_coincidencia_idx = np.argmin(distancias)
                
                # Tolerancia estricta (0.5 o menor significa mayor seguridad)
                if distancias[mejor_coincidencia_idx] < 0.5:
                    usuario_reconocido = nombres_conocidos[mejor_coincidencia_idx]
                    
                    # Dibujar recuadro verde
                    top, right, bottom, left = [coord * 4 for coord in ubicacion_cara]
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.putText(frame, f"Identificando: {usuario_reconocido}...", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        cv2.imshow('Punto de Venta - Presiona "q" para cancelar', frame)
        
        # Si reconocemos a alguien, rompemos el ciclo para cobrar
        if usuario_reconocido:
            cv2.waitKey(2000) # Pausa de 2 segundos para que se vea el recuadro verde
            break
            
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    
    # Procesar el pago en DB
    if usuario_reconocido:
        exito, mensaje_o_saldo = actualizar_saldo(usuario_reconocido, monto)
        if exito:
            messagebox.showinfo("Pago Aprobado", f"Cobro exitoso a {usuario_reconocido}.\nSaldo restante: ${mensaje_o_saldo}")
        else:
            messagebox.showerror("Pago Rechazado", f"Error con {usuario_reconocido}: {mensaje_o_saldo}")
    else:
        messagebox.showwarning("Cancelado", "No se reconoció a nadie o se canceló la operación.")

# --- 5. INTERFAZ GRÁFICA (Tkinter) ---
def arrancar_app():
    inicializar_db()
    
    def actualizar_usuarios_y_recargar():
        """Recarga los usuarios desde el dataset"""
        nonlocal encodings_conocidos, nombres_conocidos
        encodings_conocidos, nombres_conocidos = cargar_dataset()
        lbl_usuarios.config(text=f"Usuarios cargados en RAM: {len(nombres_conocidos)}")
    
    encodings_conocidos, nombres_conocidos = cargar_dataset()
    
    ventana = tk.Tk()
    ventana.title("Sistema de Pago Biométrico")
    ventana.geometry("450x400")
    ventana.eval('tk::PlaceWindow . center')
    
    tk.Label(ventana, text="Punto de Venta", font=("Arial", 18, "bold")).pack(pady=20)
    
    lbl_usuarios = tk.Label(ventana, text=f"Usuarios cargados en RAM: {len(nombres_conocidos)}", font=("Arial", 12))
    lbl_usuarios.pack()
    
    def boton_cobrar_click():
        if len(nombres_conocidos) == 0:
            messagebox.showwarning("Sin Usuarios", "No hay usuarios registrados. Registre uno primero.")
            return
        
        monto = simpledialog.askfloat("Monto", "¿Cuánto desea cobrar?")
        if monto and monto > 0:
            iniciar_escaneo(monto, encodings_conocidos, nombres_conocidos)
    
    def boton_registrar_click():
        if registrar_nuevo_usuario():
            actualizar_usuarios_y_recargar()
    
    btn_registrar = tk.Button(ventana, text="Registrar Nuevo Usuario", command=boton_registrar_click, bg="green", fg="white", font=("Arial", 11), width=28, height=2)
    btn_registrar.pack(pady=15)
    
    btn_cobrar = tk.Button(ventana, text="Iniciar Escaneo y Cobrar", command=boton_cobrar_click, bg="blue", fg="white", font=("Arial", 11), width=28, height=2)
    btn_cobrar.pack(pady=15)
    
    tk.Label(ventana, text="(Asegúrate de tener la cámara conectada)", font=("Arial", 9), fg="gray").pack(pady=10)
    
    ventana.mainloop()


if __name__ == "__main__":
    arrancar_app()