import os
import sys

APP_NAME = "CleanUninstaller"
APP_VERSION = "1.1.1"
APP_ID = "com.cleanuninstaller.app"

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")
ICON_DIR = os.path.join(RESOURCE_DIR, "icons")
UI_DIR = os.path.join(RESOURCE_DIR, "ui")

INSTALL_DIR = "/opt/clean-uninstaller"
