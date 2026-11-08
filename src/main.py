import os
import secrets

import flet as ft

from music_guessr import config
from music_guessr.app import main

# The web version needs a secret to sign file-upload URLs (playlist import).
os.environ.setdefault("FLET_SECRET_KEY", secrets.token_hex(16))

ft.app(target=main, upload_dir=str(config.upload_dir()))
