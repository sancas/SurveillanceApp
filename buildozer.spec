[app]

# (str) Título de tu aplicación
title = Vigil_Ant

# (str) Nombre del paquete
package.name = surveillancepro

# (str) Dominio del paquete
package.domain = org.ant

# (str) Directorio donde se encuentra el main.py
source.dir = .

# (str) Versión de la aplicación
version = 1.0.0

# (list) Extensiones de archivos a incluir
source.include_exts = py,png,jpg,kv,atlas

# (list) Requerimientos de la aplicación
requirements = python3, kivy, kivymd, opencv, numpy, pillow

# (str) Orientación
orientation = all

# -----------------------------------------------------------------------------
# PERMISOS ANDROID
# -----------------------------------------------------------------------------
android.permissions = INTERNET, CAMERA, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, ACCESS_NETWORK_STATE, WAKE_LOCK, RECORD_AUDIO

# (int) Target Android API
android.api = 33
android.minapi = 24

# (list) Arquitecturas
android.archs = arm64-v8a, armeabi-v7a

# (bool) Pantalla completa
fullscreen = 1

[buildozer]
log_level = 2
bin_dir = ./bin
