#!/usr/bin/env python3
import sys

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib

from core import settings as user_settings
from core.i18n import set_language
from ui.main_window import MainWindow


COLOR_SCHEME_MAP = {
    'auto':  Adw.ColorScheme.DEFAULT,
    'light': Adw.ColorScheme.FORCE_LIGHT,
    'dark':  Adw.ColorScheme.FORCE_DARK,
}


def apply_color_scheme(name):
    Adw.StyleManager.get_default().set_color_scheme(
        COLOR_SCHEME_MAP.get(name, Adw.ColorScheme.DEFAULT)
    )


def main():
    cfg = user_settings.load()
    set_language(cfg['language'])

    GLib.set_prgname('io.github.usbnux')
    GLib.set_application_name('USBnux')
    app = Adw.Application(application_id='io.github.usbnux')

    def on_activate(a):
        apply_color_scheme(cfg['color_scheme'])
        MainWindow(a, cfg).present()

    app.connect('activate', on_activate)
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
