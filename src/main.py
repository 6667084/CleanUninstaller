#!/usr/bin/env python3
import sys
import os

src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

parent_dir = os.path.dirname(src_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

from src import APP_NAME, APP_VERSION, ICON_DIR


def main():
    icon_path = os.path.join(ICON_DIR, "clean-uninstaller.svg")

    from src.main_window import MainWindow
    win = MainWindow(None)

    if os.path.exists(icon_path):
        try:
            pixbuf = Gdk.pixbuf_new_from_file_at_size(icon_path, 64, 64)
            win.set_icon(pixbuf)
        except Exception:
            win.set_icon_name("system-software-install")

    win.show_all()
    win.present()
    Gtk.main()


if __name__ == "__main__":
    main()
