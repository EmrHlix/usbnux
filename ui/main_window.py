import os
import pwd
import time
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from core import settings as user_settings
from core.checksum import compute_hash, detect_algo, find_sidecar_hash
from core.disk_detector import format_size, get_usb_drives
from core.dumper import USBDumper, detect_iso_size, get_device_size
from core.formatter import FILESYSTEMS, USBFormatter, sanitize_label
from core.i18n import (LANGUAGE_LABELS, LANGUAGES, _, get_language,
                       set_language)
from core.iso_analyzer import analyze_iso
from core.writer import USBWriter


def _real_user_home():
    """Root olarak calisirken cagiran kullanicinin ev klasorunu dondur."""
    for env in ('PKEXEC_UID', 'SUDO_UID'):
        uid = os.environ.get(env)
        if uid and uid.isdigit():
            try:
                return pwd.getpwuid(int(uid)).pw_dir
            except KeyError:
                pass
    return os.path.expanduser('~')


# Dump çıktısı root yetkili çalıştığı için her yere yazabilir; sistem
# dizinlerine yazılması neredeyse her zaman kullanıcı hatasıdır.
_SENSITIVE_PREFIXES = (
    '/etc/', '/boot/', '/usr/', '/sys/', '/proc/', '/dev/',
    '/sbin/', '/bin/', '/lib/', '/lib32/', '/lib64/',
    '/var/lib/', '/var/log/', '/var/cache/', '/root/',
)


def _is_sensitive_system_path(path):
    """Yol bir sistem dizininin altına düşüyorsa True döner."""
    try:
        real = os.path.realpath(path) + '/'
    except OSError:
        return False
    return any(real.startswith(p) for p in _SENSITIVE_PREFIXES)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, cfg):
        super().__init__(application=app)
        self._cfg = cfg
        self.set_title(_('window.title'))
        self.set_default_size(620, 600)
        self.set_resizable(False)

        self._iso_path  = None
        self._iso_type  = None
        self._drives    = []
        self._writer      = None
        self._writing     = False
        self._start_time  = None
        self._timer_id    = None

        # Checksum durumu
        self._sidecar       = {}
        self._cks_expected  = None
        self._cks_algo      = None
        self._cks_result    = None
        self._cks_running   = False
        self._cks_cancelled = False

        # USB -> ISO cekme durumu
        self._dumper              = None
        self._dumping             = False
        self._dump_output         = None
        self._dump_detected_size  = None
        self._dump_detected_kind  = None
        self._dump_start_time     = None
        self._dump_timer_id       = None

        # Format durumu
        self._formatter         = None
        self._formatting        = False
        self._format_start_time = None
        self._format_timer_id   = None

        self._install_actions()
        self._build_ui()
        self._setup_drag_and_drop()
        self._refresh_drives()

        if os.geteuid() != 0:
            GLib.idle_add(self._warn_no_root)

    # ------------------------------------------------------------------ Actions / menu

    def _install_actions(self):
        scheme_action = Gio.SimpleAction.new_stateful(
            'color-scheme',
            GLib.VariantType.new('s'),
            GLib.Variant.new_string(self._cfg.get('color_scheme', 'auto')),
        )
        scheme_action.connect('change-state', self._on_color_scheme_change)
        self.add_action(scheme_action)

        lang_action = Gio.SimpleAction.new_stateful(
            'language',
            GLib.VariantType.new('s'),
            GLib.Variant.new_string(get_language()),
        )
        lang_action.connect('change-state', self._on_language_change)
        self.add_action(lang_action)

    def _on_color_scheme_change(self, action, value):
        scheme = value.get_string()
        self._cfg['color_scheme'] = scheme
        user_settings.save(self._cfg)
        from main import apply_color_scheme
        apply_color_scheme(scheme)
        action.set_state(value)

    def _on_language_change(self, action, value):
        new_lang = value.get_string()
        if new_lang == get_language():
            return
        if self._busy():
            self._show_busy_dialog()
            return
        self._cfg['language'] = new_lang
        user_settings.save(self._cfg)
        set_language(new_lang)
        action.set_state(value)
        app = self.get_application()
        new_window = MainWindow(app, self._cfg)
        new_window.present()
        self.destroy()

    def _busy(self):
        return (self._writing or self._dumping
                or self._formatting or self._cks_running)

    def _show_busy_dialog(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('lang.busy_title'),
            body=_('lang.busy_body'),
        )
        dialog.add_response('ok', _('btn.ok'))
        dialog.present()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        self._view_stack = Adw.ViewStack()

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self._view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)

        header = Adw.HeaderBar()
        header.set_title_widget(switcher)

        # Hamburger menü (sol üst)
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name('open-menu-symbolic')
        menu_button.set_menu_model(self._build_main_menu())
        header.pack_start(menu_button)
        root.append(header)

        write_page = self._build_write_page()
        self._view_stack.add_titled_with_icon(
            write_page, 'write', _('page.write'), 'document-send-symbolic')

        dump_page = self._build_dump_page()
        self._view_stack.add_titled_with_icon(
            dump_page, 'dump', _('page.dump'), 'document-save-symbolic')

        format_page = self._build_format_page()
        self._view_stack.add_titled_with_icon(
            format_page, 'format', _('page.format'), 'drive-harddisk-symbolic')

        root.append(self._view_stack)

    def _build_main_menu(self):
        menu = Gio.Menu()

        view_menu = Gio.Menu()
        view_menu.append(_('menu.view.system'), 'win.color-scheme::auto')
        view_menu.append(_('menu.view.light'),  'win.color-scheme::light')
        view_menu.append(_('menu.view.dark'),   'win.color-scheme::dark')
        menu.append_submenu(_('menu.view'), view_menu)

        lang_menu = Gio.Menu()
        for lang in LANGUAGES:
            lang_menu.append(LANGUAGE_LABELS[lang], f'win.language::{lang}')
        menu.append_submenu(_('menu.language'), lang_menu)

        return menu

    def _make_label_factory(self):
        factory = Gtk.SignalListItemFactory()
        def setup(_f, item):
            item.set_child(Gtk.Label(xalign=0))
        def bind(_f, item):
            obj = item.get_item()
            item.get_child().set_text(obj.get_string() if obj else '')
        factory.connect('setup', setup)
        factory.connect('bind', bind)
        return factory

    def _make_page_scroll(self):
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(640)
        clamp.set_tightening_threshold(480)
        scroll.set_child(clamp)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(24)
        content.set_margin_bottom(32)
        content.set_margin_start(16)
        content.set_margin_end(16)
        clamp.set_child(content)
        return scroll, content

    def _build_write_page(self):
        scroll, content = self._make_page_scroll()

        iso_grp = Adw.PreferencesGroup()
        iso_grp.set_title(_('write.iso_group'))
        content.append(iso_grp)

        self._iso_row = Adw.ActionRow()
        self._iso_row.set_title(_('write.iso_none'))
        self._iso_row.set_subtitle(_('write.iso_hint'))

        browse_btn = Gtk.Button(label=_('btn.browse'))
        browse_btn.set_valign(Gtk.Align.CENTER)
        browse_btn.add_css_class('suggested-action')
        browse_btn.connect('clicked', self._on_browse)
        self._iso_row.add_suffix(browse_btn)
        iso_grp.add(self._iso_row)

        drv_grp = Adw.PreferencesGroup()
        drv_grp.set_title(_('write.drive_group'))
        content.append(drv_grp)

        drv_row = Adw.ActionRow()
        drv_row.set_title(_('write.drive_label'))

        self._drives_model = Gtk.StringList.new([])
        self._drive_combo = Gtk.DropDown(
            model=self._drives_model,
            factory=self._make_label_factory(),
            list_factory=self._make_label_factory(),
        )
        self._drive_combo.set_valign(Gtk.Align.CENTER)
        self._drive_combo.set_hexpand(True)
        drv_row.add_suffix(self._drive_combo)

        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name('view-refresh-symbolic')
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.set_tooltip_text(_('btn.refresh'))
        refresh_btn.connect('clicked', lambda _b: self._refresh_drives())
        drv_row.add_suffix(refresh_btn)
        drv_grp.add(drv_row)

        opt_grp = Adw.PreferencesGroup()
        opt_grp.set_title(_('write.opts_group'))
        content.append(opt_grp)

        scheme_row = Adw.ActionRow()
        scheme_row.set_title(_('write.scheme'))
        scheme_row.set_subtitle(_('write.scheme_hint'))
        scheme_model = Gtk.StringList.new(['MBR', 'GPT'])
        self._scheme_combo = Gtk.DropDown(
            model=scheme_model,
            selected=1,
            factory=self._make_label_factory(),
            list_factory=self._make_label_factory(),
        )
        self._scheme_combo.set_valign(Gtk.Align.CENTER)
        scheme_row.add_suffix(self._scheme_combo)
        opt_grp.add(scheme_row)

        self._type_row = Adw.ActionRow()
        self._type_row.set_title(_('write.iso_type'))
        self._type_row.set_subtitle(_('misc.dash'))
        opt_grp.add(self._type_row)

        self._cks_row = Adw.ActionRow()
        self._cks_row.set_title(_('write.cks'))
        self._cks_row.set_subtitle(_('write.cks_pick_iso'))

        self._cks_btn = Gtk.Button(label=_('btn.verify'))
        self._cks_btn.set_valign(Gtk.Align.CENTER)
        self._cks_btn.set_sensitive(False)
        self._cks_btn.connect('clicked', self._on_verify_click)
        self._cks_row.add_suffix(self._cks_btn)
        opt_grp.add(self._cks_row)

        status_grp = Adw.PreferencesGroup()
        status_grp.set_title(_('write.status_group'))
        content.append(status_grp)

        prog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        prog_box.set_margin_start(12)
        prog_box.set_margin_end(12)
        prog_box.set_margin_top(12)
        prog_box.set_margin_bottom(12)

        self._status_lbl = Gtk.Label(label=_('write.status_ready'))
        self._status_lbl.set_halign(Gtk.Align.START)
        self._status_lbl.set_wrap(True)
        prog_box.append(self._status_lbl)

        self._progress = Gtk.ProgressBar()
        self._progress.set_show_text(True)
        self._progress.set_text('0%')
        prog_box.append(self._progress)

        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        prog_box.append(bottom_row)

        self._file_lbl = Gtk.Label(label='')
        self._file_lbl.set_halign(Gtk.Align.START)
        self._file_lbl.set_hexpand(True)
        self._file_lbl.set_ellipsize(3)
        self._file_lbl.set_max_width_chars(55)
        self._file_lbl.add_css_class('caption')
        bottom_row.append(self._file_lbl)

        self._timer_lbl = Gtk.Label(label='')
        self._timer_lbl.set_halign(Gtk.Align.END)
        self._timer_lbl.add_css_class('caption')
        bottom_row.append(self._timer_lbl)

        status_grp.add(prog_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                          spacing=12, halign=Gtk.Align.CENTER)
        content.append(btn_box)

        self._write_btn = Gtk.Button(label=_('btn.write'))
        self._write_btn.add_css_class('suggested-action')
        self._write_btn.add_css_class('pill')
        self._write_btn.set_sensitive(False)
        self._write_btn.connect('clicked', self._on_write)
        btn_box.append(self._write_btn)

        self._cancel_btn = Gtk.Button(label=_('btn.cancel'))
        self._cancel_btn.add_css_class('destructive-action')
        self._cancel_btn.add_css_class('pill')
        self._cancel_btn.set_visible(False)
        self._cancel_btn.connect('clicked', self._on_cancel)
        btn_box.append(self._cancel_btn)

        return scroll

    def _build_dump_page(self):
        scroll, content = self._make_page_scroll()

        src_grp = Adw.PreferencesGroup()
        src_grp.set_title(_('dump.source_group'))
        content.append(src_grp)

        src_row = Adw.ActionRow()
        src_row.set_title(_('write.drive_label'))

        self._dump_drives_model = Gtk.StringList.new([])
        self._dump_drive_combo = Gtk.DropDown(
            model=self._dump_drives_model,
            factory=self._make_label_factory(),
            list_factory=self._make_label_factory(),
        )
        self._dump_drive_combo.set_valign(Gtk.Align.CENTER)
        self._dump_drive_combo.set_hexpand(True)
        self._dump_drive_combo.connect('notify::selected', self._on_dump_drive_changed)
        src_row.add_suffix(self._dump_drive_combo)

        d_refresh_btn = Gtk.Button()
        d_refresh_btn.set_icon_name('view-refresh-symbolic')
        d_refresh_btn.set_valign(Gtk.Align.CENTER)
        d_refresh_btn.set_tooltip_text(_('btn.refresh'))
        d_refresh_btn.connect('clicked', lambda _b: self._refresh_drives())
        src_row.add_suffix(d_refresh_btn)
        src_grp.add(src_row)

        info_grp = Adw.PreferencesGroup()
        info_grp.set_title(_('dump.detect_group'))
        content.append(info_grp)

        self._dump_type_row = Adw.ActionRow()
        self._dump_type_row.set_title(_('dump.content_type'))
        self._dump_type_row.set_subtitle(_('misc.dash'))
        info_grp.add(self._dump_type_row)

        self._dump_size_row = Adw.ActionRow()
        self._dump_size_row.set_title(_('dump.output_size'))
        self._dump_size_row.set_subtitle(_('misc.dash'))
        info_grp.add(self._dump_size_row)

        out_grp = Adw.PreferencesGroup()
        out_grp.set_title(_('dump.output_group'))
        content.append(out_grp)

        self._dump_out_row = Adw.ActionRow()
        self._dump_out_row.set_title(_('dump.output_none'))
        self._dump_out_row.set_subtitle(_('dump.output_hint'))

        pick_btn = Gtk.Button(label=_('btn.pick_output'))
        pick_btn.set_valign(Gtk.Align.CENTER)
        pick_btn.add_css_class('suggested-action')
        pick_btn.connect('clicked', self._on_dump_pick_output)
        self._dump_out_row.add_suffix(pick_btn)
        out_grp.add(self._dump_out_row)

        d_status_grp = Adw.PreferencesGroup()
        d_status_grp.set_title(_('write.status_group'))
        content.append(d_status_grp)

        d_prog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        d_prog_box.set_margin_start(12)
        d_prog_box.set_margin_end(12)
        d_prog_box.set_margin_top(12)
        d_prog_box.set_margin_bottom(12)

        self._dump_status_lbl = Gtk.Label(label=_('write.status_ready'))
        self._dump_status_lbl.set_halign(Gtk.Align.START)
        self._dump_status_lbl.set_wrap(True)
        d_prog_box.append(self._dump_status_lbl)

        self._dump_progress = Gtk.ProgressBar()
        self._dump_progress.set_show_text(True)
        self._dump_progress.set_text('0%')
        d_prog_box.append(self._dump_progress)

        d_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        d_prog_box.append(d_bottom)

        self._dump_file_lbl = Gtk.Label(label='')
        self._dump_file_lbl.set_halign(Gtk.Align.START)
        self._dump_file_lbl.set_hexpand(True)
        self._dump_file_lbl.set_ellipsize(3)
        self._dump_file_lbl.set_max_width_chars(55)
        self._dump_file_lbl.add_css_class('caption')
        d_bottom.append(self._dump_file_lbl)

        self._dump_timer_lbl = Gtk.Label(label='')
        self._dump_timer_lbl.set_halign(Gtk.Align.END)
        self._dump_timer_lbl.add_css_class('caption')
        d_bottom.append(self._dump_timer_lbl)

        d_status_grp.add(d_prog_box)

        d_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                            spacing=12, halign=Gtk.Align.CENTER)
        content.append(d_btn_box)

        self._dump_btn = Gtk.Button(label=_('btn.dump'))
        self._dump_btn.add_css_class('suggested-action')
        self._dump_btn.add_css_class('pill')
        self._dump_btn.set_sensitive(False)
        self._dump_btn.connect('clicked', self._on_dump_start)
        d_btn_box.append(self._dump_btn)

        self._dump_cancel_btn = Gtk.Button(label=_('btn.cancel'))
        self._dump_cancel_btn.add_css_class('destructive-action')
        self._dump_cancel_btn.add_css_class('pill')
        self._dump_cancel_btn.set_visible(False)
        self._dump_cancel_btn.connect('clicked', self._on_dump_cancel)
        d_btn_box.append(self._dump_cancel_btn)

        return scroll

    def _build_format_page(self):
        scroll, content = self._make_page_scroll()

        drv_grp = Adw.PreferencesGroup()
        drv_grp.set_title(_('fmt.drive_group'))
        content.append(drv_grp)

        drv_row = Adw.ActionRow()
        drv_row.set_title(_('write.drive_label'))

        self._fmt_drives_model = Gtk.StringList.new([])
        self._fmt_drive_combo = Gtk.DropDown(
            model=self._fmt_drives_model,
            factory=self._make_label_factory(),
            list_factory=self._make_label_factory(),
        )
        self._fmt_drive_combo.set_valign(Gtk.Align.CENTER)
        self._fmt_drive_combo.set_hexpand(True)
        drv_row.add_suffix(self._fmt_drive_combo)

        f_refresh_btn = Gtk.Button()
        f_refresh_btn.set_icon_name('view-refresh-symbolic')
        f_refresh_btn.set_valign(Gtk.Align.CENTER)
        f_refresh_btn.set_tooltip_text(_('btn.refresh'))
        f_refresh_btn.connect('clicked', lambda _b: self._refresh_drives())
        drv_row.add_suffix(f_refresh_btn)
        drv_grp.add(drv_row)

        opt_grp = Adw.PreferencesGroup()
        opt_grp.set_title(_('fmt.opts_group'))
        content.append(opt_grp)

        fs_row = Adw.ActionRow()
        fs_row.set_title(_('fmt.fs'))
        fs_row.set_subtitle(_('fmt.fs_hint'))
        fs_model = Gtk.StringList.new(list(FILESYSTEMS))
        self._fmt_fs_combo = Gtk.DropDown(
            model=fs_model,
            selected=0,
            factory=self._make_label_factory(),
            list_factory=self._make_label_factory(),
        )
        self._fmt_fs_combo.set_valign(Gtk.Align.CENTER)
        fs_row.add_suffix(self._fmt_fs_combo)
        opt_grp.add(fs_row)

        scheme_row = Adw.ActionRow()
        scheme_row.set_title(_('fmt.scheme'))
        scheme_row.set_subtitle(_('fmt.scheme_hint'))
        scheme_model = Gtk.StringList.new(['MBR', 'GPT'])
        self._fmt_scheme_combo = Gtk.DropDown(
            model=scheme_model,
            selected=0,
            factory=self._make_label_factory(),
            list_factory=self._make_label_factory(),
        )
        self._fmt_scheme_combo.set_valign(Gtk.Align.CENTER)
        scheme_row.add_suffix(self._fmt_scheme_combo)
        opt_grp.add(scheme_row)

        label_row = Adw.ActionRow()
        label_row.set_title(_('fmt.label'))
        label_row.set_subtitle(_('fmt.label_hint'))
        self._fmt_label_entry = Gtk.Entry()
        self._fmt_label_entry.set_valign(Gtk.Align.CENTER)
        self._fmt_label_entry.set_placeholder_text(_('fmt.label_placeholder'))
        self._fmt_label_entry.set_max_length(32)
        label_row.add_suffix(self._fmt_label_entry)
        opt_grp.add(label_row)

        f_status_grp = Adw.PreferencesGroup()
        f_status_grp.set_title(_('write.status_group'))
        content.append(f_status_grp)

        f_prog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        f_prog_box.set_margin_start(12)
        f_prog_box.set_margin_end(12)
        f_prog_box.set_margin_top(12)
        f_prog_box.set_margin_bottom(12)

        self._fmt_status_lbl = Gtk.Label(label=_('write.status_ready'))
        self._fmt_status_lbl.set_halign(Gtk.Align.START)
        self._fmt_status_lbl.set_wrap(True)
        f_prog_box.append(self._fmt_status_lbl)

        self._fmt_progress = Gtk.ProgressBar()
        self._fmt_progress.set_show_text(True)
        self._fmt_progress.set_text('0%')
        f_prog_box.append(self._fmt_progress)

        f_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        f_prog_box.append(f_bottom)

        self._fmt_phase_lbl = Gtk.Label(label='')
        self._fmt_phase_lbl.set_halign(Gtk.Align.START)
        self._fmt_phase_lbl.set_hexpand(True)
        self._fmt_phase_lbl.add_css_class('caption')
        f_bottom.append(self._fmt_phase_lbl)

        self._fmt_timer_lbl = Gtk.Label(label='')
        self._fmt_timer_lbl.set_halign(Gtk.Align.END)
        self._fmt_timer_lbl.add_css_class('caption')
        f_bottom.append(self._fmt_timer_lbl)

        f_status_grp.add(f_prog_box)

        f_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                            spacing=12, halign=Gtk.Align.CENTER)
        content.append(f_btn_box)

        self._fmt_btn = Gtk.Button(label=_('btn.format'))
        self._fmt_btn.add_css_class('destructive-action')
        self._fmt_btn.add_css_class('pill')
        self._fmt_btn.set_sensitive(False)
        self._fmt_btn.connect('clicked', self._on_format)
        f_btn_box.append(self._fmt_btn)

        self._fmt_cancel_btn = Gtk.Button(label=_('btn.cancel'))
        self._fmt_cancel_btn.add_css_class('destructive-action')
        self._fmt_cancel_btn.add_css_class('pill')
        self._fmt_cancel_btn.set_visible(False)
        self._fmt_cancel_btn.connect('clicked', self._on_format_cancel)
        f_btn_box.append(self._fmt_cancel_btn)

        return scroll

    # ------------------------------------------------------------------ Drive

    def _refresh_drives(self):
        self._drives = get_usb_drives()
        for model in (self._drives_model,
                      self._dump_drives_model,
                      self._fmt_drives_model):
            while model.get_n_items():
                model.remove(0)
        if self._drives:
            for d in self._drives:
                self._drives_model.append(d['display'])
                self._dump_drives_model.append(d['display'])
                self._fmt_drives_model.append(d['display'])
        else:
            none_lbl = _('drives.none')
            self._drives_model.append(none_lbl)
            self._dump_drives_model.append(none_lbl)
            self._fmt_drives_model.append(none_lbl)
        self._update_write_btn()
        self._on_dump_drive_changed()
        self._update_format_btn()

    # ------------------------------------------------------------------ ISO

    def _on_browse(self, _btn):
        chooser = Gtk.FileChooserDialog(
            title=_('chooser.iso_title'),
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button(_('btn.cancel'), Gtk.ResponseType.CANCEL)
        chooser.add_button(_('btn.select'), Gtk.ResponseType.ACCEPT)

        f = Gtk.FileFilter()
        f.set_name(_('chooser.iso_filter'))
        f.add_pattern('*.iso')
        f.add_pattern('*.ISO')
        f.add_mime_type('application/x-iso9660-image')
        chooser.add_filter(f)

        all_f = Gtk.FileFilter()
        all_f.set_name(_('chooser.all_files'))
        all_f.add_pattern('*')
        chooser.add_filter(all_f)

        start_dir = _real_user_home()
        if start_dir and os.path.isdir(start_dir):
            chooser.set_current_folder(Gio.File.new_for_path(start_dir))

        chooser.connect('response', self._on_file_chosen)
        chooser.show()

    def _on_file_chosen(self, chooser, response):
        chooser.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        path = chooser.get_file().get_path()
        self._load_iso(path)

    def _load_iso(self, path):
        if not path or not os.path.isfile(path):
            return
        if not path.lower().endswith('.iso'):
            toast = Adw.MessageDialog(
                transient_for=self,
                heading=_('dnd.invalid'),
                body=_('dnd.iso_only'),
            )
            toast.add_response('ok', _('btn.ok'))
            toast.present()
            return
        self._iso_path = path
        name = os.path.basename(path)
        size = os.path.getsize(path)
        self._iso_row.set_title(name)
        self._iso_row.set_subtitle(format_size(size))
        self._type_row.set_subtitle(_('dump.detecting'))
        self._iso_type = None
        self._reset_checksum_state()
        self._cks_row.set_subtitle(_('write.cks_searching'))
        self._cks_btn.set_sensitive(False)
        self._update_write_btn()
        threading.Thread(target=self._bg_analyze, daemon=True).start()
        threading.Thread(target=self._bg_find_sidecar, daemon=True).start()

    # ------------------------------------------------------------------ Drag&Drop

    def _setup_drag_and_drop(self):
        target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        target.connect('drop', self._on_drop)
        target.connect('enter', self._on_drag_enter)
        target.connect('leave', self._on_drag_leave)
        self.add_controller(target)

    def _on_drop(self, _target, value, _x, _y):
        if self._writing or self._cks_running:
            return False
        path = value.get_path() if isinstance(value, Gio.File) else None
        if not path:
            return False
        self._load_iso(path)
        return True

    def _on_drag_enter(self, _target, _x, _y):
        if not self._writing and not self._cks_running:
            self._iso_row.add_css_class('accent')
        return Gdk.DragAction.COPY

    def _on_drag_leave(self, _target):
        self._iso_row.remove_css_class('accent')

    def _bg_analyze(self):
        t = analyze_iso(self._iso_path)
        GLib.idle_add(self._apply_type, t)

    def _apply_type(self, iso_type):
        self._iso_type = iso_type
        labels = {'windows': _('write.iso_type.win'),
                  'linux':   _('write.iso_type.linux')}
        self._type_row.set_subtitle(labels.get(iso_type, iso_type or _('misc.dash')))
        self._update_write_btn()
        return False

    # ------------------------------------------------------------------ Checksum

    def _reset_checksum_state(self):
        self._sidecar       = {}
        self._cks_expected  = None
        self._cks_algo      = None
        self._cks_result    = None
        self._cks_running   = False
        self._cks_cancelled = False
        self._cks_row.set_subtitle(_('misc.dash'))
        self._cks_btn.set_label(_('btn.verify'))
        self._cks_btn.set_sensitive(False)

    def _bg_find_sidecar(self):
        path = self._iso_path
        info = find_sidecar_hash(path)
        GLib.idle_add(self._apply_sidecar, path, info)

    def _apply_sidecar(self, path, info):
        if path != self._iso_path:
            return False
        self._sidecar = info
        sources = info.get('source', {})
        algo_priority = ('sha256', 'sha512', 'sha1', 'md5')
        for algo in algo_priority:
            if algo in info:
                src = sources.get(algo, '?')
                self._cks_row.set_subtitle(_(
                    'write.cks_found',
                    algo=algo.upper(),
                    prefix=info[algo][:12],
                    src=src,
                ))
                self._cks_btn.set_sensitive(True)
                return False
        self._cks_row.set_subtitle(_('write.cks_none'))
        self._cks_btn.set_sensitive(True)
        return False

    def _on_verify_click(self, _btn):
        if self._cks_running:
            self._cks_cancelled = True
            return
        self._open_verify_dialog()

    def _open_verify_dialog(self):
        prefill = ''
        prefill_algo = None
        for algo in ('sha256', 'sha512', 'sha1', 'md5'):
            if algo in self._sidecar:
                prefill = self._sidecar[algo]
                prefill_algo = algo
                break

        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('verify.title'),
            body=_('verify.body'),
        )
        dialog.add_response('cancel', _('btn.cancel'))
        dialog.add_response('verify', _('btn.verify'))
        dialog.set_response_appearance('verify', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('verify')
        dialog.set_close_response('cancel')

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)

        entry = Gtk.Entry()
        entry.set_placeholder_text(_('verify.placeholder'))
        entry.set_hexpand(True)
        if prefill:
            entry.set_text(prefill)
        box.append(entry)

        info_lbl = Gtk.Label(xalign=0)
        info_lbl.add_css_class('caption')
        info_lbl.add_css_class('dim-label')
        if prefill_algo:
            info_lbl.set_label(_(
                'verify.prefill',
                algo=prefill_algo.upper(),
                src=self._sidecar.get('source', {}).get(prefill_algo, '?'),
            ))
        else:
            info_lbl.set_label(_('verify.no_prefill'))
        box.append(info_lbl)

        dialog.set_extra_child(box)
        dialog.connect('response', self._on_verify_dialog_response, entry)
        dialog.present()

    def _on_verify_dialog_response(self, dialog, response, entry):
        text = entry.get_text().strip().lower()
        dialog.destroy()
        if response != 'verify':
            return
        algo = detect_algo(text)
        if not algo:
            self._cks_row.set_subtitle(_('write.cks_invalid'))
            return
        self._cks_expected = text
        self._cks_algo     = algo
        self._cks_result   = None
        self._start_hashing()

    def _start_hashing(self):
        self._cks_running   = True
        self._cks_cancelled = False
        self._cks_btn.set_label(_('btn.stop'))
        self._cks_btn.set_sensitive(True)
        self._update_write_btn()
        threading.Thread(target=self._bg_hash, daemon=True).start()

    def _bg_hash(self):
        path = self._iso_path
        algo = self._cks_algo
        try:
            result = compute_hash(
                path, algo,
                progress_cb=lambda done, total: GLib.idle_add(
                    self._update_hash_progress, path, done, total),
                cancelled_cb=lambda: self._cks_cancelled,
            )
            GLib.idle_add(self._finish_hash, path, result, None)
        except InterruptedError:
            GLib.idle_add(self._finish_hash, path, None, 'cancelled')
        except OSError as e:
            GLib.idle_add(self._finish_hash, path, None, str(e))

    def _update_hash_progress(self, path, done, total):
        if path != self._iso_path or not self._cks_running:
            return False
        pct = (done / total * 100) if total else 0
        self._cks_row.set_subtitle(_(
            'write.cks_progress',
            algo=self._cks_algo.upper(),
            pct=pct,
            done=format_size(done),
            total=format_size(total),
        ))
        return False

    def _finish_hash(self, path, computed, error):
        if path != self._iso_path:
            return False
        self._cks_running = False
        self._cks_btn.set_label(_('btn.verify'))
        if error == 'cancelled':
            self._cks_row.set_subtitle(_('write.cks_cancelled'))
            self._cks_result = None
        elif error:
            self._cks_row.set_subtitle(_('write.cks_error', error=error))
            self._cks_result = None
        elif computed.lower() == self._cks_expected.lower():
            self._cks_row.set_subtitle(_('write.cks_match', algo=self._cks_algo.upper()))
            self._cks_result = 'match'
        else:
            self._cks_row.set_subtitle(_(
                'write.cks_mismatch',
                algo=self._cks_algo.upper(),
                expected=self._cks_expected[:10],
                got=computed[:10],
            ))
            self._cks_result = 'mismatch'
        self._update_write_btn()
        return False

    # ------------------------------------------------------------------ Write

    def _update_write_btn(self):
        ok = (
            self._iso_path is not None
            and os.path.exists(self._iso_path)
            and bool(self._drives)
            and not self._writing
            and not self._cks_running
        )
        self._write_btn.set_sensitive(ok)

    def _on_write(self, _btn):
        sel = self._drive_combo.get_selected()
        if sel >= len(self._drives):
            return
        drive  = self._drives[sel]
        scheme = 'MBR' if self._scheme_combo.get_selected() == 0 else 'GPT'

        body = _('write.confirm_body', drive=drive['display'])
        if self._cks_result == 'mismatch':
            body = _('write.confirm_cks_fail') + body

        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('write.confirm_title'),
            body=body,
        )
        dialog.add_response('cancel', _('btn.cancel'))
        dialog.add_response('write',  _('btn.write').strip())
        dialog.set_response_appearance('write', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')

        opts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        opts_box.set_margin_top(12)

        win11_check = Gtk.CheckButton(label=_('write.opt_bypass'))
        if self._iso_type != 'windows':
            win11_check.set_sensitive(False)
            win11_check.set_tooltip_text(_('write.opt_bypass_only_win'))
        opts_box.append(win11_check)

        verify_check = Gtk.CheckButton(label=_('write.opt_verify'))
        opts_box.append(verify_check)

        dialog.set_extra_child(opts_box)
        dialog.connect('response', self._on_confirmed,
                       drive, scheme, win11_check, verify_check)
        dialog.present()

    def _on_confirmed(self, _dialog, response, drive, scheme,
                      win11_check, verify_check):
        if response != 'write':
            return
        bypass = (self._iso_type == 'windows' and win11_check.get_active())
        verify = verify_check.get_active()
        self._start_write(drive, scheme,
                          bypass_win11_checks=bypass,
                          verify_after_write=verify)

    def _start_write(self, drive, scheme,
                     bypass_win11_checks=False,
                     verify_after_write=False):
        self._writing = True
        self._write_btn.set_visible(False)
        self._cancel_btn.set_visible(True)
        self._cancel_btn.set_sensitive(True)
        self._progress.set_fraction(0)
        self._progress.set_text('0%')
        self._file_lbl.set_text('')

        self._start_time = time.monotonic()
        self._timer_lbl.set_text('0:00')
        self._timer_id = GLib.timeout_add(1000, self._tick_timer)

        self._writer = USBWriter(
            iso_path             = self._iso_path,
            drive_path           = drive['path'],
            iso_type             = self._iso_type or 'linux',
            partition_scheme     = scheme,
            bypass_win11_checks  = bypass_win11_checks,
            verify_after_write   = verify_after_write,
            on_progress          = lambda f: GLib.idle_add(self._ui_progress, f),
            on_status            = lambda m: GLib.idle_add(self._ui_status,   m),
            on_file_status       = lambda m: GLib.idle_add(self._ui_file_status, m),
            on_done              = lambda ok, m: GLib.idle_add(self._ui_done, ok, m),
        )
        self._writer.start()

    def _tick_timer(self):
        if not self._writing:
            return False
        elapsed = int(time.monotonic() - self._start_time)
        m, s = divmod(elapsed, 60)
        self._timer_lbl.set_text(f'{m}:{s:02d}')
        return True

    def _on_cancel(self, _btn):
        if self._writer:
            self._writer.cancel()
        self._cancel_btn.set_sensitive(False)
        self._ui_status(_('st.cancelling'))

    # ------------------------------------------------------------------ Write callbacks

    def _ui_progress(self, frac):
        self._progress.set_fraction(frac)
        self._progress.set_text(f'{frac * 100:.0f}%')
        return False

    def _ui_status(self, msg):
        self._status_lbl.set_text(msg)
        self._file_lbl.set_text('')
        return False

    def _ui_file_status(self, msg):
        self._file_lbl.set_text(msg)
        return False

    def _ui_done(self, success, message):
        self._writing = False
        self._write_btn.set_visible(True)
        self._cancel_btn.set_visible(False)
        self._update_write_btn()

        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        if self._start_time is not None:
            elapsed = int(time.monotonic() - self._start_time)
            m, s = divmod(elapsed, 60)
            self._timer_lbl.set_text(_('res.elapsed', m=m, s=s))

        if success:
            self._progress.set_fraction(1.0)
            self._progress.set_text('100%')

        self._status_lbl.set_text(message)
        self._file_lbl.set_text('')

        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('res.success') if success else _('res.error'),
            body=message,
        )
        dialog.add_response('ok', _('btn.ok'))
        if not success:
            dialog.set_response_appearance('ok', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.present()
        return False

    # ------------------------------------------------------------------ USB → ISO

    def _on_dump_drive_changed(self, *_args):
        sel = self._dump_drive_combo.get_selected()
        if not self._drives or sel >= len(self._drives):
            self._dump_type_row.set_subtitle(_('misc.dash'))
            self._dump_size_row.set_subtitle(_('misc.dash'))
            self._dump_detected_size = None
            self._dump_detected_kind = None
            self._update_dump_btn()
            return
        drive = self._drives[sel]
        self._dump_type_row.set_subtitle(_('dump.detecting'))
        self._dump_size_row.set_subtitle(_('misc.dash'))
        self._dump_detected_size = None
        self._dump_detected_kind = None
        self._update_dump_btn()
        threading.Thread(target=self._bg_detect_dump,
                         args=(drive['path'],), daemon=True).start()

    def _bg_detect_dump(self, path):
        size_iso, kind = detect_iso_size(path)
        size_dev = get_device_size(path)
        GLib.idle_add(self._apply_dump_detection, path, size_iso, size_dev, kind)

    def _apply_dump_detection(self, path, size_iso, size_dev, kind):
        sel = self._dump_drive_combo.get_selected()
        if (not self._drives or sel >= len(self._drives)
                or self._drives[sel]['path'] != path):
            return False
        if kind == 'iso9660' and size_iso:
            size = size_iso
            type_text = _('dump.iso9660_ok')
        else:
            size = size_dev
            type_text = _('dump.iso9660_none')
        self._dump_type_row.set_subtitle(type_text)
        self._dump_size_row.set_subtitle(
            format_size(size) if size else _('dump.size_unknown')
        )
        self._dump_detected_size = size
        self._dump_detected_kind = kind
        self._update_dump_btn()
        return False

    def _on_dump_pick_output(self, _btn):
        chooser = Gtk.FileChooserDialog(
            title=_('chooser.dump_title'),
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.SAVE,
        )
        chooser.add_button(_('btn.cancel'), Gtk.ResponseType.CANCEL)
        chooser.add_button(_('btn.save'),   Gtk.ResponseType.ACCEPT)
        chooser.set_current_name(_('chooser.dump_default'))

        start_dir = _real_user_home()
        if start_dir and os.path.isdir(start_dir):
            chooser.set_current_folder(Gio.File.new_for_path(start_dir))

        chooser.connect('response', self._on_dump_output_chosen)
        chooser.show()

    def _on_dump_output_chosen(self, chooser, response):
        chooser.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        f = chooser.get_file()
        path = f.get_path() if f else None
        if not path:
            return
        if not path.lower().endswith('.iso'):
            path += '.iso'
        if _is_sensitive_system_path(path):
            self._confirm_sensitive_output(path)
            return
        self._accept_dump_output(path)

    def _confirm_sensitive_output(self, path):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('dump.sensitive_title'),
            body=_('dump.sensitive_body', path=path),
        )
        dialog.add_response('cancel', _('btn.cancel'))
        dialog.add_response('accept', _('dump.sensitive_continue'))
        dialog.set_response_appearance('accept', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')

        def on_response(_d, resp):
            if resp == 'accept':
                self._accept_dump_output(path)

        dialog.connect('response', on_response)
        dialog.present()

    def _accept_dump_output(self, path):
        self._dump_output = path
        self._dump_out_row.set_title(os.path.basename(path))
        self._dump_out_row.set_subtitle(path)
        self._update_dump_btn()

    def _update_dump_btn(self):
        ok = (bool(self._drives)
              and self._dump_detected_size
              and self._dump_output
              and not self._dumping)
        self._dump_btn.set_sensitive(bool(ok))

    def _on_dump_start(self, _btn):
        sel = self._dump_drive_combo.get_selected()
        if not self._drives or sel >= len(self._drives):
            return
        drive = self._drives[sel]

        warn = ''
        if self._dump_detected_kind != 'iso9660':
            warn = _('dump.confirm_warn')

        body = _('dump.confirm_body',
                 drive=drive['display'],
                 output=self._dump_output,
                 size=format_size(self._dump_detected_size),
                 warn=warn)
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('dump.confirm_title'),
            body=body,
        )
        dialog.add_response('cancel', _('btn.cancel'))
        dialog.add_response('start',  _('btn.start'))
        dialog.set_response_appearance('start', Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response('start')
        dialog.set_close_response('cancel')
        dialog.connect('response', self._on_dump_confirmed, drive)
        dialog.present()

    def _on_dump_confirmed(self, _dialog, response, drive):
        if response != 'start':
            return
        self._start_dump(drive)

    def _start_dump(self, drive):
        self._dumping = True
        self._dump_btn.set_visible(False)
        self._dump_cancel_btn.set_visible(True)
        self._dump_cancel_btn.set_sensitive(True)
        self._dump_progress.set_fraction(0)
        self._dump_progress.set_text('0%')
        self._dump_file_lbl.set_text('')

        self._dump_start_time = time.monotonic()
        self._dump_timer_lbl.set_text('0:00')
        self._dump_timer_id = GLib.timeout_add(1000, self._dump_tick_timer)

        self._dumper = USBDumper(
            drive_path     = drive['path'],
            output_path    = self._dump_output,
            size_bytes     = self._dump_detected_size,
            on_progress    = lambda f: GLib.idle_add(self._dump_ui_progress, f),
            on_status      = lambda m: GLib.idle_add(self._dump_ui_status, m),
            on_file_status = lambda m: GLib.idle_add(self._dump_ui_file_status, m),
            on_done        = lambda ok, m: GLib.idle_add(self._dump_ui_done, ok, m),
        )
        self._dumper.start()

    def _dump_tick_timer(self):
        if not self._dumping:
            return False
        elapsed = int(time.monotonic() - self._dump_start_time)
        m, s = divmod(elapsed, 60)
        self._dump_timer_lbl.set_text(f'{m}:{s:02d}')
        return True

    def _on_dump_cancel(self, _btn):
        if self._dumper:
            self._dumper.cancel()
        self._dump_cancel_btn.set_sensitive(False)
        self._dump_status_lbl.set_text(_('st.cancelling'))

    def _dump_ui_progress(self, frac):
        self._dump_progress.set_fraction(frac)
        self._dump_progress.set_text(f'{frac * 100:.0f}%')
        return False

    def _dump_ui_status(self, msg):
        self._dump_status_lbl.set_text(msg)
        self._dump_file_lbl.set_text('')
        return False

    def _dump_ui_file_status(self, msg):
        self._dump_file_lbl.set_text(msg)
        return False

    def _dump_ui_done(self, success, message):
        self._dumping = False
        self._dump_btn.set_visible(True)
        self._dump_cancel_btn.set_visible(False)
        self._update_dump_btn()

        if self._dump_timer_id is not None:
            GLib.source_remove(self._dump_timer_id)
            self._dump_timer_id = None
        if self._dump_start_time is not None:
            elapsed = int(time.monotonic() - self._dump_start_time)
            m, s = divmod(elapsed, 60)
            self._dump_timer_lbl.set_text(_('res.elapsed', m=m, s=s))

        if success:
            self._dump_progress.set_fraction(1.0)
            self._dump_progress.set_text('100%')

        self._dump_status_lbl.set_text(message)
        self._dump_file_lbl.set_text('')

        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('res.success') if success else _('res.error'),
            body=message,
        )
        dialog.add_response('ok', _('btn.ok'))
        if not success:
            dialog.set_response_appearance('ok', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.present()
        return False

    # ------------------------------------------------------------------ Format

    def _update_format_btn(self):
        ok = bool(self._drives) and not self._formatting
        self._fmt_btn.set_sensitive(ok)

    def _on_format(self, _btn):
        sel = self._fmt_drive_combo.get_selected()
        if not self._drives or sel >= len(self._drives):
            return
        drive  = self._drives[sel]
        fs     = FILESYSTEMS[self._fmt_fs_combo.get_selected()]
        scheme = 'MBR' if self._fmt_scheme_combo.get_selected() == 0 else 'GPT'
        label  = sanitize_label(fs, self._fmt_label_entry.get_text())

        body = _('fmt.confirm_body',
                 drive=drive['display'], fs=fs, scheme=scheme, label=label)
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('fmt.confirm_title'),
            body=body,
        )
        dialog.add_response('cancel', _('btn.cancel'))
        dialog.add_response('format', _('btn.format').strip())
        dialog.set_response_appearance('format', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', self._on_format_confirmed,
                       drive, fs, scheme, label)
        dialog.present()

    def _on_format_confirmed(self, _dialog, response, drive, fs, scheme, label):
        if response != 'format':
            return
        self._start_format(drive, fs, scheme, label)

    def _start_format(self, drive, fs, scheme, label):
        self._formatting = True
        self._fmt_btn.set_visible(False)
        self._fmt_cancel_btn.set_visible(True)
        self._fmt_cancel_btn.set_sensitive(True)
        self._fmt_progress.set_fraction(0)
        self._fmt_progress.set_text('0%')
        self._fmt_phase_lbl.set_text('')

        self._format_start_time = time.monotonic()
        self._fmt_timer_lbl.set_text('0:00')
        self._format_timer_id = GLib.timeout_add(1000, self._format_tick_timer)

        self._formatter = USBFormatter(
            drive_path       = drive['path'],
            filesystem       = fs,
            label            = label,
            partition_scheme = scheme,
            on_progress      = lambda f: GLib.idle_add(self._fmt_ui_progress, f),
            on_status        = lambda m: GLib.idle_add(self._fmt_ui_status, m),
            on_done          = lambda ok, m: GLib.idle_add(self._fmt_ui_done, ok, m),
        )
        self._formatter.start()

    def _format_tick_timer(self):
        if not self._formatting:
            return False
        elapsed = int(time.monotonic() - self._format_start_time)
        m, s = divmod(elapsed, 60)
        self._fmt_timer_lbl.set_text(f'{m}:{s:02d}')
        return True

    def _on_format_cancel(self, _btn):
        if self._formatter:
            self._formatter.cancel()
        self._fmt_cancel_btn.set_sensitive(False)
        self._fmt_status_lbl.set_text(_('st.cancelling'))

    def _fmt_ui_progress(self, frac):
        self._fmt_progress.set_fraction(frac)
        self._fmt_progress.set_text(f'{frac * 100:.0f}%')
        return False

    def _fmt_ui_status(self, msg):
        self._fmt_status_lbl.set_text(msg)
        return False

    def _fmt_ui_done(self, success, message):
        self._formatting = False
        self._fmt_btn.set_visible(True)
        self._fmt_cancel_btn.set_visible(False)
        self._update_format_btn()

        if self._format_timer_id is not None:
            GLib.source_remove(self._format_timer_id)
            self._format_timer_id = None
        if self._format_start_time is not None:
            elapsed = int(time.monotonic() - self._format_start_time)
            m, s = divmod(elapsed, 60)
            self._fmt_timer_lbl.set_text(_('res.elapsed', m=m, s=s))

        if success:
            self._fmt_progress.set_fraction(1.0)
            self._fmt_progress.set_text('100%')

        self._fmt_status_lbl.set_text(message.splitlines()[0])
        self._fmt_phase_lbl.set_text('')

        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('res.success') if success else _('res.error'),
            body=message,
        )
        dialog.add_response('ok', _('btn.ok'))
        if not success:
            dialog.set_response_appearance('ok', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.present()
        if success:
            GLib.timeout_add(1500, lambda: (self._refresh_drives(), False)[1])
        return False

    # ------------------------------------------------------------------ Root check

    def _warn_no_root(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_('root.title'),
            body=_('root.body'),
        )
        dialog.add_response('ok', _('btn.understood'))
        dialog.present()
        return False
