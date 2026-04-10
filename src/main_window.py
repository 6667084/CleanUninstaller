import os
import threading
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk, Gio

from . import APP_NAME, ICON_DIR, RESOURCE_DIR
from .scanner import AppScanner, AppInfo
from .uninstaller import Uninstaller, UninstallResult


class MainWindow(Gtk.Window):
    def __init__(self, app=None):
        super().__init__()
        self.set_title(APP_NAME)
        self.set_default_size(960, 640)
        self.set_position(Gtk.WindowPosition.CENTER)

        self._scanner = AppScanner()
        self._uninstaller = Uninstaller()
        self._apps = []
        self._filtered_apps = []
        self._current_app = None
        self._is_scanning = False
        self._is_uninstalling = False
        self._category_filter = "all"

        self._load_css()
        self._build_ui()
        self._connect_signals()

        GLib.idle_add(self._start_scan)

    def _load_css(self):
        css_path = os.path.join(RESOURCE_DIR, "ui", "style.css")
        if os.path.exists(css_path):
            css_provider = Gtk.CssProvider()
            try:
                css_provider.load_from_path(css_path)
                screen = Gdk.Screen.get_default()
                if screen:
                    Gtk.StyleContext.add_provider_for_screen(
                        screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                    )
            except Exception as e:
                print(f"加载CSS失败: {e}")

    def _build_ui(self):
        self.set_name("app-window")

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(main_box)

        self._build_header(main_box)
        self._build_content(main_box)
        self._build_statusbar(main_box)

    def _build_header(self, parent):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.set_name("header-bar")
        header.get_style_context().add_class("header-bar")
        header.set_margin_top(0)
        header.set_margin_bottom(0)

        icon_path = os.path.join(ICON_DIR, "clean-uninstaller.svg")
        if os.path.exists(icon_path):
            img = Gtk.Image.new_from_icon_name("system-software-install", Gtk.IconSize.BUTTON)
            try:
                pixbuf = Gdk.pixbuf_new_from_file_at_size(icon_path, 32, 32)
                img = Gtk.Image.new_from_pixbuf(pixbuf)
            except Exception:
                pass
            header.pack_start(img, False, False, 8)

        title_label = Gtk.Label(label=APP_NAME)
        title_label.set_name("title")
        title_label.get_style_context().add_class("title")
        header.pack_start(title_label, False, False, 4)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_name("search-entry")
        self._search_entry.get_style_context().add_class("search-entry")
        self._search_entry.set_placeholder_text("搜索已安装的软件...")
        self._search_entry.set_hexpand(True)
        self._search_entry.set_size_request(300, -1)
        header.pack_end(self._search_entry, False, False, 16)

        self._refresh_btn = Gtk.Button(label="刷新")
        self._refresh_btn.get_style_context().add_class("btn-primary")
        header.pack_end(self._refresh_btn, False, False, 4)

        parent.pack_start(header, False, False, 0)

        sep = Gtk.Separator()
        parent.pack_start(sep, False, False, 0)

    def _build_content(self, parent):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(200)
        parent.pack_start(paned, True, True, 0)

        self._build_sidebar(paned)

        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        paned.pack2(right_box, True, True)

        self._build_app_list(right_box)

    def _build_sidebar(self, parent):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.set_name("sidebar")
        sidebar.get_style_context().add_class("sidebar")
        sidebar.set_margin_top(8)
        sidebar.set_margin_bottom(8)
        sidebar.set_margin_start(4)
        sidebar.set_margin_end(4)

        cat_label = Gtk.Label(label="分类筛选")
        cat_label.set_halign(Gtk.Align.START)
        cat_label.set_margin_bottom(8)
        cat_label.get_style_context().add_class("category-label")
        sidebar.pack_start(cat_label, False, False, 4)

        self._category_buttons = {}
        self._category_names = {}

        categories = [
            ("all", "全部软件"),
            ("apt", "APT 软件包"),
            ("flatpak", "Flatpak 应用"),
            ("large", "大型软件 (>100MB)"),
        ]

        for cat_id, cat_name in categories:
            btn = Gtk.Button(label=cat_name)
            btn.set_name(f"cat-{cat_id}")
            btn.get_style_context().add_class("category-item")
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_halign(Gtk.Align.FILL)
            btn.connect("clicked", self._on_category_clicked, cat_id)
            sidebar.pack_start(btn, False, False, 2)
            self._category_buttons[cat_id] = btn
            self._category_names[cat_id] = cat_name

        sidebar.pack_start(Gtk.Separator(), False, False, 8)

        self._detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._detail_box.set_margin_start(8)
        self._detail_box.set_margin_end(8)
        sidebar.pack_start(self._detail_box, False, False, 4)

        parent.pack1(sidebar, False, False)

    def _build_app_list(self, parent):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self._list_store = Gtk.ListStore(
            str, str, str, str, str, str, str, object
        )

        self._tree_view = Gtk.TreeView(model=self._list_store)
        self._tree_view.set_name("app-treeview")
        self._tree_view.set_headers_visible(True)
        self._tree_view.set_activate_on_single_click(True)
        self._tree_view.set_rules_hint(True)

        renderer_name = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn("软件名称", renderer_name, text=0)
        col_name.set_expand(True)
        col_name.set_min_width(200)
        col_name.set_resizable(True)
        col_name.set_sort_column_id(0)
        self._tree_view.append_column(col_name)

        renderer_pkg = Gtk.CellRendererText()
        col_pkg = Gtk.TreeViewColumn("包名", renderer_pkg, text=1)
        col_pkg.set_min_width(150)
        col_pkg.set_resizable(True)
        col_pkg.set_sort_column_id(1)
        self._tree_view.append_column(col_pkg)

        renderer_ver = Gtk.CellRendererText()
        col_ver = Gtk.TreeViewColumn("版本", renderer_ver, text=2)
        col_ver.set_min_width(80)
        col_ver.set_resizable(True)
        self._tree_view.append_column(col_ver)

        renderer_size = Gtk.CellRendererText()
        col_size = Gtk.TreeViewColumn("大小", renderer_size, text=3)
        col_size.set_min_width(80)
        col_size.set_sort_column_id(3)
        self._tree_view.append_column(col_size)

        renderer_src = Gtk.CellRendererText()
        col_src = Gtk.TreeViewColumn("来源", renderer_src, text=4)
        col_src.set_min_width(60)
        self._tree_view.append_column(col_src)

        self._tree_view.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=5))

        self._tree_view.get_selection().connect("changed", self._on_selection_changed)
        scrolled.add(self._tree_view)

        parent.pack_start(scrolled, True, True, 0)

        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_bar.set_margin_top(8)
        action_bar.set_margin_bottom(8)
        action_bar.set_margin_start(12)
        action_bar.set_margin_end(12)

        self._selected_label = Gtk.Label(label="未选择软件")
        self._selected_label.set_hexpand(True)
        self._selected_label.set_xalign(0)
        action_bar.pack_start(self._selected_label, True, True, 0)

        self._uninstall_btn = Gtk.Button(label="卸载所选软件")
        self._uninstall_btn.get_style_context().add_class("btn-danger")
        self._uninstall_btn.set_sensitive(False)
        self._uninstall_btn.set_size_request(160, 40)
        action_bar.pack_end(self._uninstall_btn, False, False, 0)

        parent.pack_end(action_bar, False, False, 0)

    def _build_statusbar(self, parent):
        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status_bar.set_name("status-bar")
        status_bar.get_style_context().add_class("status-bar")

        self._status_label = Gtk.Label(label="就绪")
        self._status_label.set_halign(Gtk.Align.START)
        status_bar.pack_start(self._status_label, True, True, 0)

        self._count_label = Gtk.Label(label="共 0 个软件")
        self._count_label.set_halign(Gtk.Align.END)
        status_bar.pack_end(self._count_label, False, False, 0)

        parent.pack_end(status_bar, False, False, 0)

    def _connect_signals(self):
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._refresh_btn.connect("clicked", self._on_refresh_clicked)
        self._uninstall_btn.connect("clicked", self._on_uninstall_clicked)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, widget):
        self._scanner.cancel()
        self._uninstaller.cancel()
        Gtk.main_quit()

    def _start_scan(self):
        if self._is_scanning:
            return
        self._is_scanning = True
        self._status_label.set_text("正在扫描已安装的软件...")
        self._refresh_btn.set_sensitive(False)

        self._progress_dialog = None

        def scan_thread():
            apps = self._scanner.get_installed_apps(
                progress_callback=lambda p, m: GLib.idle_add(self._update_scan_progress, p, m)
            )
            GLib.idle_add(self._scan_complete, apps)

        thread = threading.Thread(target=scan_thread, daemon=True)
        thread.start()

    def _update_scan_progress(self, progress, message):
        self._status_label.set_text(message)
        return False

    def _scan_complete(self, apps):
        self._is_scanning = False
        self._apps = apps
        self._refresh_btn.set_sensitive(True)
        self._apply_filter()
        self._status_label.set_text(f"扫描完成，共发现 {len(apps)} 个已安装软件")

        if self._category_buttons.get("all"):
            self._update_category_counts()

    def _update_category_counts(self):
        for cat_id, btn in self._category_buttons.items():
            count = len(self._get_filtered_by_category(cat_id))
            original_name = self._category_names.get(cat_id, cat_id)
            btn.set_label(f"{original_name} ({count})")

    def _get_filtered_by_category(self, category):
        if category == "all":
            return self._apps
        elif category == "apt":
            return [a for a in self._apps if a.source == "apt"]
        elif category == "flatpak":
            return [a for a in self._apps if a.source == "flatpak"]
        elif category == "large":
            return [a for a in self._apps if self._parse_size_mb(a.size) > 100]
        return self._apps

    def _parse_size_mb(self, size_str):
        try:
            if "GB" in size_str:
                return float(size_str.replace("GB", "").strip()) * 1024
            elif "MB" in size_str:
                return float(size_str.replace("MB", "").strip())
            elif "KB" in size_str:
                return float(size_str.replace("KB", "").strip()) / 1024
        except (ValueError, TypeError):
            pass
        return 0

    def _apply_filter(self):
        search_text = self._search_entry.get_text().strip().lower()

        filtered = self._get_filtered_by_category(self._category_filter)

        if search_text:
            filtered = [
                a for a in filtered
                if search_text in a.display_name.lower()
                or search_text in a.package_name.lower()
                or search_text in a.description.lower()
            ]

        self._filtered_apps = filtered
        self._populate_list()
        self._count_label.set_text(f"显示 {len(filtered)} / {len(self._apps)} 个软件")

    def _populate_list(self):
        self._list_store.clear()
        for app in self._filtered_apps:
            self._list_store.append([
                app.display_name,
                app.package_name,
                app.version,
                app.display_size,
                app.source.upper(),
                app.category,
                app.description,
                app,
            ])

    def _on_search_changed(self, entry):
        self._apply_filter()

    def _on_category_clicked(self, button, cat_id):
        self._category_filter = cat_id
        for cid, btn in self._category_buttons.items():
            ctx = btn.get_style_context()
            if cid == cat_id:
                ctx.add_class("active")
            else:
                ctx.remove_class("active")
        self._apply_filter()

    def _on_selection_changed(self, selection):
        model, tree_iter = selection.get_selected()
        if tree_iter is not None:
            app = model.get_value(tree_iter, 7)
            self._current_app = app
            self._selected_label.set_text(
                f"已选择: {app.display_name} ({app.package_name}) - {app.version} - {app.display_size}"
            )
            self._uninstall_btn.set_sensitive(True)
            self._update_detail_panel(app)
        else:
            self._current_app = None
            self._selected_label.set_text("未选择软件")
            self._uninstall_btn.set_sensitive(False)

    def _update_detail_panel(self, app):
        for child in self._detail_box.get_children():
            self._detail_box.remove(child)

        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{app.display_name}</b>")
        lbl.set_line_wrap(True)
        self._detail_box.pack_start(lbl, False, False, 4)

        if app.description:
            desc_lbl = Gtk.Label(label=app.description[:100])
            desc_lbl.set_line_wrap(True)
            desc_lbl.get_style_context().add_class("text-secondary")
            self._detail_box.pack_start(desc_lbl, False, False, 2)

        info = f"包名: {app.package_name}\n版本: {app.version}"
        if app.display_size:
            info += f"\n大小: {app.display_size}"
        info += f"\n来源: {app.source.upper()}"

        info_lbl = Gtk.Label(label=info)
        info_lbl.set_xalign(0)
        info_lbl.set_line_wrap(True)
        self._detail_box.pack_start(info_lbl, False, False, 4)

        self._detail_box.show_all()

    def _on_refresh_clicked(self, button):
        if not self._is_scanning:
            self._start_scan()

    def _on_uninstall_clicked(self, button):
        if self._current_app is None or self._is_uninstalling:
            return

        app = self._current_app
        self._show_confirm_dialog(app)

    def _show_confirm_dialog(self, app):
        dialog = Gtk.Dialog(
            title="确认卸载",
            parent=self,
            modal=True,
            destroy_with_parent=True,
        )
        dialog.set_default_size(480, 350)
        dialog.add_buttons(
            "取消", Gtk.ResponseType.CANCEL,
            "确认卸载", Gtk.ResponseType.OK,
        )

        content = dialog.get_content_area()
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_spacing(12)

        icon = Gtk.Image.new_from_icon_name("dialog-warning", Gtk.IconSize.DIALOG)
        content.pack_start(icon, False, False, 0)

        warn_label = Gtk.Label()
        warn_label.set_markup(f"<b><span size='large'>确认要卸载以下软件吗？</span></b>")
        content.pack_start(warn_label, False, False, 0)

        info_label = Gtk.Label()
        info_label.set_markup(
            f"<b>{app.display_name}</b>\n"
            f"包名: {app.package_name}\n"
            f"版本: {app.version}\n"
            f"大小: {app.display_size}\n"
            f"来源: {app.source.upper()}"
        )
        info_label.set_justify(Gtk.Justification.CENTER)
        content.pack_start(info_label, False, False, 8)

        content.pack_start(Gtk.Separator(), False, False, 4)

        self._remove_config_check = Gtk.CheckButton(label="删除系统配置文件 (purge)")
        self._remove_config_check.set_active(True)
        content.pack_start(self._remove_config_check, False, False, 4)

        self._remove_residual_check = Gtk.CheckButton(label="清理残留文件和用户数据")
        self._remove_residual_check.set_active(True)
        content.pack_start(self._remove_residual_check, False, False, 4)

        caution_label = Gtk.Label()
        caution_label.set_markup("<span foreground='#E53935'>⚠ 此操作不可撤销，卸载后软件将被完全移除</span>")
        content.pack_start(caution_label, False, False, 8)

        content.show_all()

        response = dialog.run()
        remove_config = self._remove_config_check.get_active()
        remove_residuals = self._remove_residual_check.get_active()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            self._perform_uninstall(app, remove_config, remove_residuals)

    def _perform_uninstall(self, app, remove_config, remove_residuals):
        self._is_uninstalling = True
        self._uninstall_btn.set_sensitive(False)
        self._refresh_btn.set_sensitive(False)

        progress_dialog = Gtk.Dialog(
            title="正在卸载...",
            parent=self,
            modal=True,
            destroy_with_parent=False,
        )
        progress_dialog.set_default_size(560, 420)
        progress_dialog.set_deletable(False)

        content = progress_dialog.get_content_area()
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_spacing(8)

        title_lbl = Gtk.Label()
        title_lbl.set_markup(f"<b>正在卸载: {app.display_name}</b>")
        content.pack_start(title_lbl, False, False, 8)

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_fraction(0.0)
        self._progress_bar.set_show_text(True)
        content.pack_start(self._progress_bar, False, False, 8)

        self._progress_label = Gtk.Label(label="准备中...")
        self._progress_label.set_xalign(0)
        content.pack_start(self._progress_label, False, False, 4)

        log_label = Gtk.Label(label="详细日志:")
        log_label.set_xalign(0)
        content.pack_start(log_label, False, False, 4)

        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_vexpand(True)
        log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self._log_view = Gtk.TextView()
        self._log_view.set_editable(False)
        self._log_view.set_monospace(True)
        self._log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_view.get_style_context().add_class("log-view")
        self._log_buffer = self._log_view.get_buffer()
        log_scroll.add(self._log_view)
        content.pack_start(log_scroll, True, True, 4)

        cancel_btn = Gtk.Button(label="取消卸载")
        cancel_btn.get_style_context().add_class("btn-danger")
        cancel_btn.connect("clicked", lambda w: self._cancel_uninstall(progress_dialog))
        content.pack_start(cancel_btn, False, False, 4)

        content.show_all()
        progress_dialog.show()

        result_holder = [None]

        def uninstall_thread():
            result = self._uninstaller.uninstall_app(
                app,
                remove_config=remove_config,
                remove_residuals=remove_residuals,
                progress_callback=lambda p, m: GLib.idle_add(self._update_progress, p, m),
                log_callback=lambda msg: GLib.idle_add(self._append_log, msg),
            )
            result_holder[0] = result
            GLib.idle_add(self._uninstall_complete, result_holder[0], app, progress_dialog)

        thread = threading.Thread(target=uninstall_thread, daemon=True)
        thread.start()

    def _update_progress(self, progress, message):
        if hasattr(self, '_progress_bar') and self._progress_bar:
            self._progress_bar.set_fraction(progress)
            self._progress_bar.set_text(f"{progress * 100:.0f}%")
        if hasattr(self, '_progress_label') and self._progress_label:
            self._progress_label.set_text(message)
        return False

    def _append_log(self, message):
        if hasattr(self, '_log_buffer') and self._log_buffer:
            end_iter = self._log_buffer.get_end_iter()
            self._log_buffer.insert(end_iter, message + "\n")
            if hasattr(self, '_log_view') and self._log_view:
                mark = self._log_buffer.get_insert()
                self._log_view.scroll_to_mark(mark, 0, False, 0, 0)
        return False

    def _cancel_uninstall(self, dialog):
        self._uninstaller.cancel()
        self._append_log("--- 用户取消了卸载操作 ---")

    def _uninstall_complete(self, result, app, progress_dialog):
        progress_dialog.destroy()
        self._is_uninstalling = False
        self._refresh_btn.set_sensitive(True)
        self._uninstall_btn.set_sensitive(self._current_app is not None)

        self._show_report_dialog(result, app)

        if result.success and result.package_removed:
            self._start_scan()

    def _show_report_dialog(self, result, app):
        dialog = Gtk.Dialog(
            title="卸载报告",
            parent=self,
            modal=True,
            destroy_with_parent=True,
        )
        dialog.set_default_size(520, 450)
        dialog.add_button("确定", Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_spacing(12)

        if result.success:
            icon = Gtk.Image.new_from_icon_name("emblem-default", Gtk.IconSize.DIALOG)
            title_text = "<b><span size='large' foreground='#43A047'>卸载完成</span></b>"
        else:
            icon = Gtk.Image.new_from_icon_name("dialog-error", Gtk.IconSize.DIALOG)
            title_text = "<b><span size='large' foreground='#E53935'>卸载失败</span></b>"

        content.pack_start(icon, False, False, 0)

        title = Gtk.Label()
        title.set_markup(title_text)
        content.pack_start(title, False, False, 4)

        info = f"软件: {app.display_name} ({app.package_name})\n"
        info += f"软件包卸载: {'成功' if result.package_removed else '失败'}\n"

        if result.residual_result:
            rr = result.residual_result
            info += f"\n残留清理报告:\n"
            info += f"  发现残留项: {rr.total_items}\n"
            info += f"  成功清理: {rr.cleaned_items}\n"
            info += f"  清理失败: {rr.failed_items}\n"
            info += f"  释放空间: {self._format_bytes(rr.cleaned_size)}\n"

        if result.errors:
            info += "\n错误信息:\n"
            for err in result.errors:
                info += f"  • {err}\n"

        info_label = Gtk.Label(label=info)
        info_label.set_xalign(0)
        info_label.set_line_wrap(True)
        content.pack_start(info_label, False, False, 8)

        if result.residual_result and result.residual_result.details:
            content.pack_start(Gtk.Separator(), False, False, 4)
            detail_label = Gtk.Label(label="清理详情:")
            detail_label.set_xalign(0)
            content.pack_start(detail_label, False, False, 4)

            detail_scroll = Gtk.ScrolledWindow()
            detail_scroll.set_vexpand(True)
            detail_scroll.set_max_content_height(200)
            detail_scroll.set_min_content_height(100)
            detail_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

            detail_view = Gtk.TextView()
            detail_view.set_editable(False)
            detail_view.set_monospace(True)
            detail_buf = detail_view.get_buffer()

            detail_text = ""
            for d in result.residual_result.details:
                status = "✓" if d["success"] else "✗"
                detail_text += f"{status} [{d['type']}] {d['path']}"
                if d["size"] > 0:
                    detail_text += f" ({self._format_bytes(d['size'])})"
                detail_text += "\n"

            detail_buf.set_text(detail_text)
            detail_scroll.add(detail_view)
            content.pack_start(detail_scroll, True, True, 4)

        content.show_all()
        dialog.run()
        dialog.destroy()

    @staticmethod
    def _format_bytes(size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"
