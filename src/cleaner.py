import os
import subprocess
import shutil
import glob
from dataclasses import dataclass, field
from typing import List, Optional, Callable


@dataclass
class ResidualItem:
    path: str
    item_type: str
    size: int = 0
    description: str = ""

    @property
    def display_size(self) -> str:
        if self.size < 1024:
            return f"{self.size} B"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        elif self.size < 1024 * 1024 * 1024:
            return f"{self.size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.size / (1024 * 1024 * 1024):.2f} GB"

    @property
    def exists(self) -> bool:
        if self.path.startswith("["):
            return True
        return os.path.exists(self.path)


@dataclass
class CleanResult:
    total_items: int = 0
    cleaned_items: int = 0
    failed_items: int = 0
    total_size: int = 0
    cleaned_size: int = 0
    details: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_items": self.total_items,
            "cleaned_items": self.cleaned_items,
            "failed_items": self.failed_items,
            "total_size": self.total_size,
            "cleaned_size": self.cleaned_size,
            "details": self.details,
            "errors": self.errors,
        }


class ResidualCleaner:
    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _generate_name_variants(self, package_name: str, display_name: str = "") -> List[str]:
        variants = set()
        variants.add(package_name)

        name_lower = package_name.lower()
        variants.add(name_lower)

        for sep in ("-", "_", "."):
            parts = name_lower.split(sep)
            if len(parts) > 1:
                variants.add(parts[0])
                variants.add(sep.join(parts[:-1]))

        if display_name:
            dn = display_name.strip()
            variants.add(dn)
            variants.add(dn.lower())
            dn_no_space = dn.replace(" ", "").lower()
            variants.add(dn_no_space)
            dn_lower = dn.lower()
            for sep in ("-", "_", "."):
                parts = dn_lower.split(sep)
                if len(parts) > 1:
                    variants.add(parts[0])

        cleaned = set()
        for v in variants:
            v = v.strip()
            if v and len(v) >= 2:
                cleaned.add(v)
        return list(cleaned)

    def scan_residuals(self, package_name: str, source: str = "apt",
                       display_name: str = "", app_icon_name: str = "") -> List[ResidualItem]:
        self._cancelled = False
        items = []
        seen_paths = set()

        name_variants = self._generate_name_variants(package_name, display_name)

        if source == "apt":
            items.extend(self._scan_config_files(package_name, name_variants))
            items.extend(self._scan_cache_files(package_name, name_variants))
            items.extend(self._scan_user_data(package_name, name_variants))
            items.extend(self._scan_user_config(package_name, name_variants))
            items.extend(self._scan_user_cache(package_name, name_variants))
            items.extend(self._scan_system_cache(package_name))
            items.extend(self._scan_desktop_files(package_name, name_variants))
            items.extend(self._scan_icon_files(package_name, name_variants, app_icon_name))
            items.extend(self._scan_bin_files(package_name, name_variants))
            items.extend(self._scan_dpkg_config(package_name))
            items.extend(self._scan_orphan_deps())
        elif source == "flatpak":
            items.extend(self._scan_flatpak_user_data(package_name, name_variants))
            items.extend(self._scan_flatpak_desktop(package_name, name_variants))
            items.extend(self._scan_flatpak_cache(package_name, name_variants))

        unique_items = []
        for item in items:
            if item.path not in seen_paths:
                seen_paths.add(item.path)
                if item.exists:
                    if source == "apt" and not item.path.startswith("[") and self._is_dpkg_owned(item.path):
                        continue
                    unique_items.append(item)

        return unique_items

    def clean_residuals(
        self,
        items: List[ResidualItem],
        progress_callback: Optional[Callable] = None
    ) -> CleanResult:
        self._cancelled = False
        result = CleanResult()
        result.total_items = len(items)
        result.total_size = sum(item.size for item in items)

        for i, item in enumerate(items):
            if self._cancelled:
                break

            if progress_callback:
                progress = (i + 1) / len(items) if items else 1.0
                progress_callback(progress, f"正在清理: {os.path.basename(item.path)}")

            success = self._clean_single_item(item)
            detail = {
                "path": item.path,
                "type": item.item_type,
                "size": item.size,
                "success": success,
            }

            if success:
                result.cleaned_items += 1
                result.cleaned_size += item.size
            else:
                result.failed_items += 1
                result.errors.append(f"无法删除: {item.path}")

            result.details.append(detail)

        return result

    def _clean_single_item(self, item: ResidualItem) -> bool:
        try:
            path = item.path
            if path.startswith("[孤立依赖]"):
                dep_name = path.replace("[孤立依赖] ", "").strip()
                if dep_name:
                    res = subprocess.run(
                        ["pkexec", "apt-get", "purge", "-y", dep_name],
                        capture_output=True, text=True, timeout=60,
                        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
                    )
                    return res.returncode == 0
                return True
            if not os.path.exists(path):
                return True
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
                return True
            elif os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                return not os.path.exists(path)
        except PermissionError:
            try:
                result = subprocess.run(
                    ["pkexec", "rm", "-rf", path],
                    capture_output=True, text=True, timeout=30
                )
                return result.returncode == 0
            except Exception:
                return False
        except Exception:
            return False

        return False

    def _is_dpkg_owned(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        system_paths = ("/usr/bin/", "/usr/lib/", "/usr/share/applications/",
                        "/usr/share/icons/", "/usr/share/pixmaps/")
        if not any(path.startswith(p) for p in system_paths):
            return False
        try:
            result = subprocess.run(
                ["dpkg", "-S", path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except Exception:
            pass
        return False

    def _scan_config_files(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        for name in name_variants:
            config_dirs = [
                f"/etc/{name}",
                f"/etc/{name}.d",
                f"/usr/local/etc/{name}",
            ]
            for d in config_dirs:
                if os.path.exists(d):
                    size = self._get_dir_size(d)
                    items.append(ResidualItem(
                        path=d,
                        item_type="系统配置文件",
                        size=size,
                        description=f"系统级配置目录: {d}"
                    ))
        return items

    def _scan_cache_files(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        for name in name_variants:
            cache_patterns = [
                f"/var/cache/{name}",
                f"/var/cache/apt/archives/{name}*",
                f"/var/lib/{name}",
                f"/var/log/{name}*",
                f"/tmp/{name}*",
            ]
            for pattern in cache_patterns:
                for path in glob.glob(pattern):
                    if os.path.exists(path):
                        size = self._get_path_size(path)
                        items.append(ResidualItem(
                            path=path,
                            item_type="系统缓存/日志",
                            size=size,
                            description=f"系统缓存或日志: {path}"
                        ))
        return items

    def _scan_user_data(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        data_dir = os.path.join(home, ".local", "share")

        for name in name_variants:
            patterns = [
                os.path.join(data_dir, name),
                os.path.join(home, f".{name}"),
            ]
            for pattern in patterns:
                if os.path.exists(pattern):
                    size = self._get_dir_size(pattern)
                    items.append(ResidualItem(
                        path=pattern,
                        item_type="用户数据",
                        size=size,
                        description=f"用户数据目录: {pattern}"
                    ))

        if os.path.exists(data_dir):
            try:
                for entry in os.listdir(data_dir):
                    entry_lower = entry.lower()
                    for variant in name_variants:
                        if variant.lower() in entry_lower and len(variant) >= 3:
                            full_path = os.path.join(data_dir, entry)
                            if os.path.exists(full_path):
                                size = self._get_dir_size(full_path)
                                items.append(ResidualItem(
                                    path=full_path,
                                    item_type="用户数据",
                                    size=size,
                                    description=f"用户数据目录: {full_path}"
                                ))
                            break
            except Exception:
                pass

        return items

    def _scan_user_config(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        config_base = os.path.join(home, ".config")

        for name in name_variants:
            config_paths = [
                os.path.join(config_base, name),
            ]
            for p in config_paths:
                if os.path.exists(p):
                    size = self._get_dir_size(p)
                    items.append(ResidualItem(
                        path=p,
                        item_type="用户配置",
                        size=size,
                        description=f"用户配置目录: {p}"
                    ))

            config_file_patterns = [
                os.path.join(home, f".{name}rc"),
                os.path.join(home, f".{name}.conf"),
                os.path.join(home, f".{name}.json"),
                os.path.join(home, f".{name}.yaml"),
                os.path.join(home, f".{name}.yml"),
            ]
            for p in config_file_patterns:
                if os.path.exists(p):
                    size = os.path.getsize(p)
                    items.append(ResidualItem(
                        path=p,
                        item_type="用户配置文件",
                        size=size,
                        description=f"用户配置文件: {p}"
                    ))

        if os.path.exists(config_base):
            try:
                for entry in os.listdir(config_base):
                    entry_lower = entry.lower()
                    for variant in name_variants:
                        if variant.lower() in entry_lower and len(variant) >= 3:
                            full_path = os.path.join(config_base, entry)
                            if os.path.exists(full_path):
                                size = self._get_dir_size(full_path)
                                items.append(ResidualItem(
                                    path=full_path,
                                    item_type="用户配置",
                                    size=size,
                                    description=f"用户配置目录: {full_path}"
                                ))
                            break
            except Exception:
                pass

        return items

    def _scan_user_cache(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        cache_base = os.path.join(home, ".cache")

        for name in name_variants:
            cache_paths = [
                os.path.join(cache_base, name),
            ]
            for p in cache_paths:
                if os.path.exists(p):
                    size = self._get_dir_size(p)
                    items.append(ResidualItem(
                        path=p,
                        item_type="用户缓存",
                        size=size,
                        description=f"用户缓存目录: {p}"
                    ))

        if os.path.exists(cache_base):
            try:
                for entry in os.listdir(cache_base):
                    entry_lower = entry.lower()
                    for variant in name_variants:
                        if variant.lower() in entry_lower and len(variant) >= 3:
                            full_path = os.path.join(cache_base, entry)
                            if os.path.exists(full_path):
                                size = self._get_dir_size(full_path)
                                items.append(ResidualItem(
                                    path=full_path,
                                    item_type="用户缓存",
                                    size=size,
                                    description=f"用户缓存目录: {full_path}"
                                ))
                            break
            except Exception:
                pass

        return items

    def _scan_desktop_files(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        desktop_dirs = [
            "/usr/share/applications",
            os.path.join(home, ".local", "share", "applications"),
            os.path.join(home, "桌面"),
            os.path.join(home, "Desktop"),
        ]

        for search_dir in desktop_dirs:
            if not os.path.exists(search_dir):
                continue
            try:
                for fname in os.listdir(search_dir):
                    if not fname.endswith(".desktop"):
                        continue
                    fpath = os.path.join(search_dir, fname)
                    fname_lower = fname.lower()

                    matched = False
                    for variant in name_variants:
                        if variant.lower() in fname_lower and len(variant) >= 3:
                            matched = True
                            break

                    if not matched:
                        try:
                            matched = self._desktop_file_matches_package(fpath, package_name)
                        except Exception:
                            pass

                    if matched:
                        size = self._get_path_size(fpath)
                        items.append(ResidualItem(
                            path=fpath,
                            item_type="桌面快捷方式",
                            size=size,
                            description=f"应用快捷方式: {fpath}"
                        ))
            except Exception:
                continue

        return items

    def _desktop_file_matches_package(self, desktop_path: str, package_name: str) -> bool:
        try:
            with open(desktop_path, "r", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("Exec="):
                        exec_cmd = line[5:].strip().split()[0] if len(line) > 5 else ""
                        exec_base = os.path.basename(exec_cmd)
                        if exec_base.lower() == package_name.lower():
                            return True
                    elif line.startswith("Icon="):
                        icon_name = line[5:].strip()
                        if icon_name.lower() == package_name.lower():
                            return True
        except Exception:
            pass
        return False

    def _scan_icon_files(self, package_name: str, name_variants: List[str],
                         app_icon_name: str = "") -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        icon_search_dirs = [
            "/usr/share/pixmaps",
            "/usr/share/icons/hicolor",
            os.path.join(home, ".local", "share", "icons"),
            os.path.join(home, ".icons"),
        ]

        search_names = list(name_variants)
        if app_icon_name and app_icon_name not in search_names:
            search_names.append(app_icon_name)

        for icon_dir in icon_search_dirs:
            if not os.path.exists(icon_dir):
                continue
            try:
                for root, dirs, files in os.walk(icon_dir):
                    for fname in files:
                        fname_lower = fname.lower()
                        for variant in search_names:
                            if variant.lower() in fname_lower and len(variant) >= 3:
                                fpath = os.path.join(root, fname)
                                if os.path.exists(fpath):
                                    size = os.path.getsize(fpath)
                                    items.append(ResidualItem(
                                        path=fpath,
                                        item_type="应用图标",
                                        size=size,
                                        description=f"应用图标文件: {fpath}"
                                    ))
                                break
            except Exception:
                continue

        return items

    def _scan_bin_files(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        bin_dirs = [
            "/usr/bin",
            "/usr/local/bin",
            os.path.expanduser("~/.local/bin"),
        ]

        for bin_dir in bin_dirs:
            if not os.path.exists(bin_dir):
                continue
            try:
                for entry in os.listdir(bin_dir):
                    entry_lower = entry.lower()
                    for variant in name_variants:
                        if entry_lower == variant.lower():
                            full_path = os.path.join(bin_dir, entry)
                            if os.path.exists(full_path):
                                size = self._get_path_size(full_path)
                                items.append(ResidualItem(
                                    path=full_path,
                                    item_type="可执行文件",
                                    size=size,
                                    description=f"可执行文件残留: {full_path}"
                                ))
                            break
            except Exception:
                continue

        return items

    def _scan_dpkg_config(self, package_name: str) -> List[ResidualItem]:
        items = []
        try:
            result = subprocess.run(
                ["dpkg", "-L", package_name],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                conffiles_path = f"/etc/{package_name}"
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("/etc/") and os.path.exists(line):
                        size = self._get_path_size(line)
                        items.append(ResidualItem(
                            path=line,
                            item_type="包配置残留",
                            size=size,
                            description=f"包管理器配置残留: {line}"
                        ))
        except Exception:
            pass

        dpkg_conffile = f"/var/lib/dpkg/info/{package_name}.conffiles"
        if os.path.exists(dpkg_conffile):
            try:
                with open(dpkg_conffile, "r") as f:
                    for line in f:
                        conf_path = line.strip()
                        if conf_path and os.path.exists(conf_path):
                            size = self._get_path_size(conf_path)
                            items.append(ResidualItem(
                                path=conf_path,
                                item_type="包配置残留",
                                size=size,
                                description=f"dpkg 配置残留: {conf_path}"
                            ))
            except Exception:
                pass

        return items

    def _scan_system_cache(self, package_name: str) -> List[ResidualItem]:
        items = []
        try:
            result = subprocess.run(
                ["apt-get", "-s", "autoremove", "--purge"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0 and package_name in result.stdout:
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("Remv "):
                        parts = line.split()
                        if len(parts) >= 2:
                            dep_pkg = parts[1]
                            items.append(ResidualItem(
                                path=f"[孤立依赖] {dep_pkg}",
                                item_type="孤立依赖包",
                                size=0,
                                description=f"可自动移除的孤立依赖: {dep_pkg}"
                            ))
        except Exception:
            pass

        return items

    def _scan_orphan_deps(self) -> List[ResidualItem]:
        return []

    def _scan_flatpak_user_data(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")

        flatpak_data_dirs = [
            os.path.join(home, ".local", "share", package_name),
            os.path.join(home, ".var", "app", package_name),
        ]

        flatpak_data_base = os.path.join(home, ".local", "share")
        if os.path.exists(flatpak_data_base):
            try:
                for entry in os.listdir(flatpak_data_base):
                    for variant in name_variants:
                        if variant.lower() in entry.lower() and len(variant) >= 3:
                            full_path = os.path.join(flatpak_data_base, entry)
                            if os.path.exists(full_path):
                                size = self._get_dir_size(full_path)
                                items.append(ResidualItem(
                                    path=full_path,
                                    item_type="Flatpak 用户数据",
                                    size=size,
                                    description=f"Flatpak 应用数据: {full_path}"
                                ))
                            break
            except Exception:
                pass

        flatpak_var_base = os.path.join(home, ".var", "app")
        if os.path.exists(flatpak_var_base):
            try:
                for entry in os.listdir(flatpak_var_base):
                    for variant in name_variants:
                        if variant.lower() in entry.lower() and len(variant) >= 3:
                            full_path = os.path.join(flatpak_var_base, entry)
                            if os.path.exists(full_path):
                                size = self._get_dir_size(full_path)
                                items.append(ResidualItem(
                                    path=full_path,
                                    item_type="Flatpak 应用数据",
                                    size=size,
                                    description=f"Flatpak .var 数据: {full_path}"
                                ))
                            break
            except Exception:
                pass

        return items

    def _scan_flatpak_desktop(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        desktop_dirs = [
            "/var/lib/flatpak/exports/share/applications",
            os.path.join(home, ".local", "share", "flatpak", "exports", "share", "applications"),
            os.path.join(home, ".local", "share", "applications"),
            os.path.join(home, "桌面"),
            os.path.join(home, "Desktop"),
        ]

        for search_dir in desktop_dirs:
            if not os.path.exists(search_dir):
                continue
            try:
                for fname in os.listdir(search_dir):
                    if not fname.endswith(".desktop"):
                        continue
                    fname_lower = fname.lower()
                    for variant in name_variants:
                        if variant.lower() in fname_lower and len(variant) >= 3:
                            fpath = os.path.join(search_dir, fname)
                            if os.path.exists(fpath):
                                size = self._get_path_size(fpath)
                                items.append(ResidualItem(
                                    path=fpath,
                                    item_type="Flatpak 快捷方式",
                                    size=size,
                                    description=f"Flatpak 桌面快捷方式: {fpath}"
                                ))
                            break
            except Exception:
                continue

        return items

    def _scan_flatpak_cache(self, package_name: str, name_variants: List[str]) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        cache_base = os.path.join(home, ".cache")

        for name in name_variants:
            cache_path = os.path.join(cache_base, name)
            if os.path.exists(cache_path):
                size = self._get_dir_size(cache_path)
                items.append(ResidualItem(
                    path=cache_path,
                    item_type="Flatpak 缓存",
                    size=size,
                    description=f"Flatpak 缓存: {cache_path}"
                ))

        if os.path.exists(cache_base):
            try:
                for entry in os.listdir(cache_base):
                    entry_lower = entry.lower()
                    for variant in name_variants:
                        if variant.lower() in entry_lower and len(variant) >= 3:
                            full_path = os.path.join(cache_base, entry)
                            if os.path.exists(full_path):
                                size = self._get_dir_size(full_path)
                                items.append(ResidualItem(
                                    path=full_path,
                                    item_type="Flatpak 缓存",
                                    size=size,
                                    description=f"Flatpak 缓存: {full_path}"
                                ))
                            break
            except Exception:
                pass

        return items

    @staticmethod
    def _get_dir_size(path: str) -> int:
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total += os.path.getsize(fp)
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return total

    @staticmethod
    def _get_path_size(path: str) -> int:
        if os.path.isfile(path):
            try:
                return os.path.getsize(path)
            except (OSError, PermissionError):
                return 0
        elif os.path.isdir(path):
            return ResidualCleaner._get_dir_size(path)
        return 0
