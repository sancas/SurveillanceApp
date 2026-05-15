import os
import cv2
import time
import socket
import hashlib
import threading
import numpy as np

from datetime import datetime

from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.storage.jsonstore import JsonStore

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.textfield import MDTextField
from kivymd.uix.fitimage import FitImage

# ==========================================
# CONFIG
# ==========================================

APP_NAME = "Vigil_Ant"
SERVER_PORT = 5000
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
JPEG_QUALITY = 65


# ==========================================
# HELPERS
# ==========================================


def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()


# ==========================================
# APP
# ==========================================


class SurveillanceApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "BlueGray"

        self.title = APP_NAME

        self.clients = []
        self.texture = None
        self.zoom_level = 1.0
        self.is_recording = False
        self.video_writer = None
        self.frame_counter = 0
        self.current_fps = 0
        self.last_fps_update = time.time()

        self.store = JsonStore("settings.json")

        saved_ip = "127.0.0.1"

        if self.store.exists("config"):
            saved_ip = self.store.get("config").get("ip", "127.0.0.1")

        # ==========================================
        # ROOT SCREEN
        # ==========================================

        screen = MDScreen()

        root = MDBoxLayout(
            orientation="horizontal",
            spacing=10,
            padding=10,
        )

        # ==========================================
        # SIDEBAR
        # ==========================================

        sidebar = MDCard(
            orientation="vertical",
            size_hint_x=0.28,
            padding=15,
            spacing=15,
            radius=[20],
            elevation=4,
        )

        title = MDLabel(
            text="[b]VIGILIX[/b]",
            markup=True,
            halign="center",
            font_style="H4",
            size_hint_y=None,
            height=60,
        )

        sidebar.add_widget(title)

        self.ip_input = MDTextField(
            text=saved_ip,
            hint_text="IP del servidor",
            mode="rectangle",
        )

        self.pass_input = MDTextField(
            text="admin123",
            hint_text="Contraseña",
            password=True,
            mode="rectangle",
        )

        sidebar.add_widget(self.ip_input)
        sidebar.add_widget(self.pass_input)

        self.btn_camera = MDRaisedButton(
            text="INICIAR CAMARA",
            pos_hint={"center_x": 0.5},
        )

        self.btn_camera.bind(on_release=self.start_camera_mode)

        self.btn_viewer = MDRaisedButton(
            text="CONECTAR VISOR",
            pos_hint={"center_x": 0.5},
        )

        self.btn_viewer.bind(on_release=self.start_viewer_mode)

        self.btn_record = MDRaisedButton(
            text="INICIAR GRABACION",
            pos_hint={"center_x": 0.5},
        )

        self.btn_record.bind(on_release=self.toggle_recording)

        self.btn_snapshot = MDRaisedButton(
            text="SNAPSHOT",
            pos_hint={"center_x": 0.5},
        )

        self.btn_snapshot.bind(on_release=self.take_snapshot)

        sidebar.add_widget(self.btn_camera)
        sidebar.add_widget(self.btn_viewer)
        sidebar.add_widget(self.btn_record)
        sidebar.add_widget(self.btn_snapshot)

        self.status_label = MDLabel(
            text="OFFLINE",
            halign="center",
            theme_text_color="Error",
        )

        self.fps_label = MDLabel(
            text="FPS: 0",
            halign="center",
        )

        self.clients_label = MDLabel(
            text="Clientes: 0",
            halign="center",
        )

        sidebar.add_widget(self.status_label)
        sidebar.add_widget(self.fps_label)
        sidebar.add_widget(self.clients_label)

        # ==========================================
        # VIDEO AREA
        # ==========================================

        video_container = MDCard(
            orientation="vertical",
            radius=[20],
            elevation=4,
            padding=10,
        )

        self.top_info = MDLabel(
            text="Esperando conexión...",
            halign="left",
            size_hint_y=None,
            height=40,
        )

        video_container.add_widget(self.top_info)

        self.video = FitImage()

        self.video.bind(on_touch_down=self.video_touch)

        video_container.add_widget(self.video)

        root.add_widget(sidebar)
        root.add_widget(video_container)

        screen.add_widget(root)

        Clock.schedule_interval(self.update_fps_ui, 1)

        return screen

    # ==========================================
    # UI
    # ==========================================

    def show_dialog(self, title, text):
        dialog = MDDialog(
            title=title,
            text=text,
        )

        dialog.open()

    # ==========================================
    # VIDEO
    # ==========================================

    def video_touch(self, instance, touch):
        if touch.is_double_tap:
            if self.zoom_level < 3:
                self.zoom_level += 0.5
            else:
                self.zoom_level = 1.0

            self.top_info.text = f"Zoom: {self.zoom_level}x"

    def apply_zoom(self, frame):
        if self.zoom_level <= 1.0:
            return frame

        h, w = frame.shape[:2]

        new_h = int(h / self.zoom_level)
        new_w = int(w / self.zoom_level)

        y1 = (h - new_h) // 2
        x1 = (w - new_w) // 2

        crop = frame[y1:y1 + new_h, x1:x1 + new_w]

        return cv2.resize(crop, (w, h))

    def update_frame(self, frame):
        try:
            frame = self.apply_zoom(frame)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                timestamp,
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

            if self.is_recording:
                cv2.circle(frame, (30, 120), 10, (0, 0, 255), -1)

            buf = cv2.flip(frame, 0).tobytes()

            if self.texture is None:
                self.texture = Texture.create(
                    size=(frame.shape[1], frame.shape[0]),
                    colorfmt="bgr",
                )

            self.texture.blit_buffer(
                buf,
                colorfmt="bgr",
                bufferfmt="ubyte",
            )

            self.video.texture = self.texture

            self.last_frame = frame.copy()

            self.frame_counter += 1

            if self.is_recording and self.video_writer:
                self.video_writer.write(frame)

        except Exception as e:
            self.top_info.text = str(e)

    # ==========================================
    # FPS
    # ==========================================

    def update_fps_ui(self, dt):
        now = time.time()

        if now - self.last_fps_update >= 1:
            self.current_fps = self.frame_counter
            self.frame_counter = 0
            self.last_fps_update = now

            self.fps_label.text = f"FPS: {self.current_fps}"
            self.clients_label.text = f"Clientes: {len(self.clients)}"

    # ==========================================
    # SNAPSHOTS
    # ==========================================

    def take_snapshot(self, instance):
        try:
            if not hasattr(self, "last_frame"):
                self.show_dialog("Error", "No hay video disponible")
                return

            os.makedirs("snapshots", exist_ok=True)

            filename = datetime.now().strftime(
                "snapshots/%Y%m%d_%H%M%S.jpg"
            )

            cv2.imwrite(filename, self.last_frame)

            self.show_dialog("Snapshot", f"Guardado: {filename}")

        except Exception as e:
            self.show_dialog("Error", str(e))

    # ==========================================
    # RECORDING
    # ==========================================

    def toggle_recording(self, instance):
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

            self.btn_record.text = "DETENER GRABACION"

            self.top_info.text = "Grabando video..."

        else:
            self.is_recording = False

            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None

            self.btn_record.text = "INICIAR GRABACION"

            self.top_info.text = "Grabación finalizada"

    # ==========================================
    # SERVER
    # ==========================================

    def start_camera_mode(self, instance):
        threading.Thread(target=self.run_server, daemon=True).start()

        self.status_label.text = "SERVER ONLINE"

    def run_server(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        server_socket.bind(("0.0.0.0", SERVER_PORT))
        server_socket.listen(5)

        threading.Thread(
            target=self.accept_clients,
            args=(server_socket,),
            daemon=True,
        ).start()

        cap = cv2.VideoCapture(0)

        while True:
            ret, frame = cap.read()

            if not ret:
                continue

            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

            Clock.schedule_once(
                lambda dt, frm=frame.copy(): self.update_frame(frm)
            )

            _, encoded = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
            )

            data = encoded.tobytes()
            size = len(data).to_bytes(4, byteorder="big")

            disconnected = []

            for client in self.clients:
                try:
                    client.sendall(size + data)
                except:
                    disconnected.append(client)

            for dead in disconnected:
                self.clients.remove(dead)

    def accept_clients(self, server_socket):
        while True:
            client_socket, addr = server_socket.accept()

            password = client_socket.recv(1024).decode()

            expected = hash_password(self.pass_input.text)

            if password != expected:
                client_socket.send(b"AUTH_FAIL")
                client_socket.close()
                continue

            client_socket.send(b"AUTH_OK")

            self.clients.append(client_socket)

    # ==========================================
    # CLIENT
    # ==========================================

    def start_viewer_mode(self, instance):
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
                self.status_label.text = "CONNECTING"

                client_socket = socket.socket(
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                )

                client_socket.connect((ip, SERVER_PORT))

                client_socket.send(
                    hash_password(self.pass_input.text).encode()
                )

                auth = client_socket.recv(1024)

                if auth != b"AUTH_OK":
                    self.show_dialog(
                        "Error",
                        "Contraseña incorrecta",
                    )
                    return

                self.status_label.text = "ONLINE"

                while True:
                    size_data = self.receive_exact(client_socket, 4)

                    if not size_data:
                        break

                    size = int.from_bytes(size_data, byteorder="big")

                    data = self.receive_exact(client_socket, size)

                    frame = cv2.imdecode(
                        np.frombuffer(data, np.uint8),
                        cv2.IMREAD_COLOR,
                    )

                    if frame is not None:
                        Clock.schedule_once(
                            lambda dt, frm=frame.copy(): self.update_frame(frm)
                        )

            except Exception:
                self.status_label.text = "RECONNECTING"
                time.sleep(5)

    # ==========================================
    # NETWORK
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