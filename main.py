import os
import cv2
import ssl
import time
import socket
import hashlib
import threading
import numpy as np

from datetime import datetime
from kivymd.app import MDApp
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.storage.jsonstore import JsonStore
from kivy.uix.image import Image
from kivymd.uix.label import MDLabel
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivy.utils import platform

# ==========================================
# CONFIG
# ==========================================

APP_NAME = "Surveillance"
SERVER_PORT = 5000
MAX_CLIENTS = 5
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
JPEG_QUALITY = 65
RECONNECT_DELAY = 5

# ==========================================
# HELPERS
# ==========================================


def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()


class NetworkClient:
    def __init__(self, socket_obj, address):
        self.socket = socket_obj
        self.address = address
        self.connected_at = datetime.now()

def check_permissions():
    if platform == 'android':
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.CAMERA,
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.READ_EXTERNAL_STORAGE,
            Permission.RECORD_AUDIO
        ])


# ==========================================
# MAIN APP
# ==========================================


class SurveillanceApp(MDApp):

    def build(self):

        check_permissions()

        self.title = APP_NAME

        # =============================
        # THEME
        # =============================

        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"

        # =============================
        # STATE
        # =============================

        self.clients = []
        self.is_recording = False
        self.is_full_screen = False
        self.zoom_level = 1.0
        self.video_writer = None
        self.texture = None
        self.server_running = False
        self.client_running = False
        self.frame_counter = 0
        self.last_fps_time = time.time()
        self.current_fps = 0

        # =============================
        # STORAGE
        # =============================

        self.store = JsonStore("settings.json")

        saved_ip = "127.0.0.1"

        if self.store.exists("config"):
            saved_ip = self.store.get("config").get(
                "ip",
                "127.0.0.1"
            )

        # =============================
        # ROOT
        # =============================

        self.root_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=10,
            padding=10,
        )

        # =============================
        # SIDEBAR
        # =============================

        self.sidebar = MDCard(
            orientation="vertical",
            size_hint_x=0.28,
            padding=15,
            spacing=15,
            radius=[25],
            elevation=4,
        )

        # =============================
        # TITLE
        # =============================

        title = MDLabel(
            text=APP_NAME,
            bold=True,
            size_hint_y=None,
            height=80,
        )

        self.sidebar.add_widget(title)

        # =============================
        # CONFIG SECTION
        # =============================

        config_label = MDLabel(
            text="Configuración",
            theme_text_color="Secondary",
            size_hint_y=None,
            height=30,
        )

        self.sidebar.add_widget(config_label)

        self.ip_input = MDTextField(
            text=saved_ip,
            hint_text="IP del Servidor",
            helper_text="Ejemplo: 192.168.1.10",
            helper_text_mode="on_focus",
            mode="rectangle",
            size_hint_y=None,
            height=80,
        )

        self.pass_input = MDTextField(
            text="admin123",
            password=True,
            hint_text="Contraseña",
            helper_text="Ingrese contraseña",
            helper_text_mode="on_focus",
            mode="rectangle",
            size_hint_y=None,
            height=80,
        )

        self.sidebar.add_widget(self.ip_input)
        self.sidebar.add_widget(self.pass_input)

        # =============================
        # BUTTONS
        # =============================

        self.btn_camera = MDRaisedButton(
            text="INICIAR CAMARA",
            md_bg_color=(0.1, 0.6, 0.1, 1),
            size_hint_y=None,
            height=50,
            on_release=self.start_camera_mode,
        )

        self.btn_viewer = MDRaisedButton(
            text="CONECTAR VISOR",
            md_bg_color=(0.1, 0.4, 0.8, 1),
            size_hint_y=None,
            height=50,
            on_release=self.start_viewer_mode,
        )

        self.btn_record = MDRaisedButton(
            text="INICIAR GRABACION",
            md_bg_color=(0.9, 0.2, 0.2, 1),
            size_hint_y=None,
            height=50,
            on_release=self.toggle_recording,
        )

        self.btn_snapshot = MDRaisedButton(
            text="SNAPSHOT",
            md_bg_color=(0.9, 0.5, 0.1, 1),
            size_hint_y=None,
            height=50,
            on_release=self.take_snapshot,
        )

        self.sidebar.add_widget(self.btn_camera)
        self.sidebar.add_widget(self.btn_viewer)
        self.sidebar.add_widget(self.btn_record)
        self.sidebar.add_widget(self.btn_snapshot)

        # =============================
        # STATUS PANEL
        # =============================

        status_title = MDLabel(
            text="Estado del Sistema",
            theme_text_color="Secondary",
            size_hint_y=None,
            height=40,
        )

        self.sidebar.add_widget(status_title)

        self.connection_label = MDLabel(
            text="OFFLINE",
            size_hint_y=None,
            height=30,
        )

        self.fps_label = MDLabel(
            text="FPS: 0",
            size_hint_y=None,
            height=30,
        )

        self.clients_label = MDLabel(
            text="Clientes: 0",
            size_hint_y=None,
            height=30,
        )

        self.record_label = MDLabel(
            text="REC: OFF",
            size_hint_y=None,
            height=30,
        )

        self.sidebar.add_widget(self.connection_label)
        self.sidebar.add_widget(self.fps_label)
        self.sidebar.add_widget(self.clients_label)
        self.sidebar.add_widget(self.record_label)

        # =============================
        # VIDEO AREA
        # =============================

        self.video_layout = MDCard(
            orientation="vertical",
            padding=10,
            spacing=10,
            radius=[25],
            elevation=4,
        )

        # =============================
        # TOP BAR
        # =============================

        self.top_bar = MDBoxLayout(
            size_hint_y=None,
            height=50,
        )

        self.status_label = MDLabel(
            text="Esperando conexión...",
            halign="left",
        )

        self.top_bar.add_widget(
            self.status_label
        )

        self.video_layout.add_widget(
            self.top_bar
        )

        # =============================
        # VIDEO DISPLAY
        # =============================

        self.image_display = Image(
            allow_stretch=True,
            keep_ratio=True,
        )

        self.image_display.bind(
            on_touch_down=self.on_video_touch
        )

        self.video_layout.add_widget(
            self.image_display
        )

        # =============================
        # ROOT ADD
        # =============================

        self.root_layout.add_widget(
            self.sidebar
        )

        self.root_layout.add_widget(
            self.video_layout
        )

        # =============================
        # FPS TIMER
        # =============================

        Clock.schedule_interval(
            self.update_fps_ui,
            1
        )

        return self.root_layout

    # ==========================================
    # UI HELPERS
    # ==========================================

    def show_popup(self, title, message):

        self.dialog = MDDialog(
            title=title,
            text=message,
            buttons=[
                MDFlatButton(
                    text="CERRAR",
                    on_release=lambda x: self.dialog.dismiss()
                )
            ],
        )

        self.dialog.open()

    # ==========================================
    # FULLSCREEN + ZOOM
    # ==========================================

    def on_video_touch(self, instance, touch):
        if not instance.collide_point(*touch.pos):
            return

        if touch.is_double_tap:
            self.toggle_full_screen()
            return

        if self.is_full_screen:
            if self.zoom_level < 3.0:
                self.zoom_level += 0.5
            else:
                self.zoom_level = 1.0

            self.status_label.text = f"Zoom: {self.zoom_level}x"

    def toggle_full_screen(self):
        if not self.is_full_screen:
            self.root_layout.remove_widget(self.sidebar)
            self.is_full_screen = True
        else:
            self.root_layout.clear_widgets()
            self.root_layout.add_widget(self.sidebar)
            self.root_layout.add_widget(self.video_layout)
            self.is_full_screen = False

    # ==========================================
    # VIDEO
    # ==========================================

    def apply_zoom(self, frame):
        if self.zoom_level <= 1.0:
            return frame

        h, w = frame.shape[:2]

        new_h = int(h / self.zoom_level)
        new_w = int(w / self.zoom_level)

        y1 = (h - new_h) // 2
        x1 = (w - new_w) // 2

        cropped = frame[y1:y1 + new_h, x1:x1 + new_w]

        return cv2.resize(cropped, (w, h))

    def update_image(self, frame):
        try:
            frame = self.apply_zoom(frame)

            # HUD Overlay
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cv2.putText(
                frame,
                APP_NAME,
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

            cv2.putText(
                frame,
                current_time,
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

            cv2.putText(
                frame,
                f"FPS: {self.current_fps}",
                (20, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
            )

            if self.is_recording:
                cv2.circle(frame, (30, 160), 10, (0, 0, 255), -1)
                cv2.putText(
                    frame,
                    "REC",
                    (50, 166),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )
            
            if len(frame.shape) == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            buf = cv2.flip(frame_rgb, 0).tobytes()

            if self.texture is None or self.texture.size != (frame.shape[1], frame.shape[0]):
                self.texture = Texture.create(
                    size=(frame.shape[1], frame.shape[0]),
                    colorfmt="rgb",
                )

            self.texture.blit_buffer(buf, colorfmt="rgb", bufferfmt="ubyte")

            self.image_display.texture = self.texture

            self.last_frame = frame.copy()

            self.frame_counter += 1

            if self.is_recording and self.video_writer:
                self.video_writer.write(frame)

        except Exception as e:
            self.status_label.text = f"Error Video: {e}"

    # ==========================================
    # FPS
    # ==========================================

    def update_fps_ui(self, dt):
        now = time.time()
        elapsed = now - self.last_fps_time

        if elapsed >= 1:
            self.current_fps = self.frame_counter
            self.frame_counter = 0
            self.last_fps_time = now

            self.fps_label.text = f"FPS: {self.current_fps}"
            self.clients_label.text = f"Clientes: {len(self.clients)}"

    # ==========================================
    # RECORDING
    # ==========================================

    def toggle_recording(self, instance):
        try:
                
            if not self.is_recording:
                os.makedirs("recordings", exist_ok=True)

                filename = datetime.now().strftime(
                    "recordings/%Y%m%d_%H%M%S.mp4"
                )

                fourcc = cv2.VideoWriter_fourcc(*"mp4v")

                self.video_writer = cv2.VideoWriter(
                    filename,
                    fourcc,
                    20.0,
                    (FRAME_WIDTH, FRAME_HEIGHT),
                )

                self.is_recording = True

                self.record_label.text = "REC: ON"
                self.btn_record.text = "DETENER GRABACION"

                self.status_label.text = f"Grabando: {filename}"

            else:
                self.is_recording = False

                self.record_label.text = "REC: OFF"
                self.btn_record.text = "INICIAR GRABACION"

                if self.video_writer:
                    self.video_writer.release()
                    self.video_writer = None

                self.status_label.text = "Grabación finalizada"

        except Exception as e:
            self.show_popup("Error", str(e))

    # ==========================================
    # SNAPSHOTS
    # ==========================================

    def take_snapshot(self, instance):
        try:
            if not hasattr(self, "last_frame"):
                self.show_popup("Error", "No hay frame disponible")
                return

            os.makedirs("snapshots", exist_ok=True)

            filename = datetime.now().strftime(
                "snapshots/%Y%m%d_%H%M%S.jpg"
            )

            cv2.imwrite(filename, self.last_frame)

            self.show_popup("Snapshot", f"Guardado en:\n{filename}")

        except Exception as e:
            self.show_popup("Error", str(e))

    # ==========================================
    # SERVER
    # ==========================================

    def start_camera_mode(self, instance):
        if self.server_running:
            self.show_popup("Servidor", "El servidor ya está activo")
            return

        self.server_running = True

        self.store.put("config", ip=self.ip_input.text)

        threading.Thread(target=self.run_server, daemon=True).start()

        self.connection_label.text = "SERVER ONLINE"
        self.status_label.text = "Servidor iniciado"

    def run_server(self):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            server_socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1,
            )

            server_socket.bind(("0.0.0.0", SERVER_PORT))
            server_socket.listen(MAX_CLIENTS)

            # Webcam local
            cap = cv2.VideoCapture(0, cv2.CAP_ANDROID)

            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

            threading.Thread(
                target=self.accept_clients,
                args=(server_socket,),
                daemon=True,
            ).start()

            while True:
                ret, frame = cap.read()

                if not ret:
                    continue

                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

                Clock.schedule_once(
                    lambda dt, frm=frame.copy(): self.update_image(frm)
                )

                _, img_encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
                )

                data = img_encoded.tobytes()
                size = len(data).to_bytes(4, byteorder="big")

                disconnected = []

                for client in self.clients:
                    try:
                        client.socket.sendall(size + data)
                    except:
                        disconnected.append(client)

                for dead in disconnected:
                    self.clients.remove(dead)

        except Exception as e:
            Clock.schedule_once(
                lambda dt: self.show_popup("Server Error", str(e))
            )

    def accept_clients(self, server_socket):
        while True:
            try:
                client_socket, addr = server_socket.accept()

                # Authentication
                password_data = client_socket.recv(1024).decode()

                expected = hash_password(self.pass_input.text)

                if password_data != expected:
                    client_socket.send(b"AUTH_FAIL")
                    client_socket.close()
                    continue

                client_socket.send(b"AUTH_OK")

                client = NetworkClient(client_socket, addr)
                self.clients.append(client)

                self.status_label.text = f"Cliente conectado: {addr[0]}"

            except Exception as e:
                self.status_label.text = f"Error Cliente: {e}"

    # ==========================================
    # CLIENT
    # ==========================================

    def start_viewer_mode(self, instance):
        if self.client_running:
            self.show_popup("Cliente", "Ya existe una conexión activa")
            return

        self.client_running = True

        ip = self.ip_input.text

        self.store.put("config", ip=ip)

        threading.Thread(
            target=self.run_client,
            args=(ip,),
            daemon=True,
        ).start()

    def run_client(self, ip):
        while True:
            try:
                self.connection_label.text = "CONNECTING"

                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(10)

                client_socket.connect((ip, SERVER_PORT))

                password_hash = hash_password(self.pass_input.text)

                client_socket.send(password_hash.encode())

                auth_response = client_socket.recv(1024)

                if auth_response != b"AUTH_OK":
                    Clock.schedule_once(
                        lambda dt: self.show_popup(
                            "Autenticación",
                            "Contraseña incorrecta",
                        )
                    )
                    return

                self.connection_label.text = "ONLINE"
                self.status_label.text = "Conectado al servidor"

                while True:
                    size_data = self.receive_exact(client_socket, 4)

                    if not size_data:
                        raise Exception("Servidor desconectado")

                    size = int.from_bytes(size_data, byteorder="big")

                    data = self.receive_exact(client_socket, size)

                    if not data:
                        raise Exception("Frame inválido")

                    frame = cv2.imdecode(
                        np.frombuffer(data, np.uint8),
                        cv2.IMREAD_COLOR,
                    )

                    if frame is not None:
                        Clock.schedule_once(
                            lambda dt, frm=frame.copy(): self.update_image(frm)
                        )

            except Exception as e:
                self.connection_label.text = "OFFLINE"
                self.status_label.text = f"Reconectando en {RECONNECT_DELAY}s"

                time.sleep(RECONNECT_DELAY)

    # ==========================================
    # NETWORK HELPERS
    # ==========================================

    def receive_exact(self, sock, size):
        data = b""

        while len(data) < size:
            packet = sock.recv(size - len(data))

            if not packet:
                return None

            data += packet

        return data


# ==========================================
# START
# ==========================================

if __name__ == "__main__":
    SurveillanceApp().run()