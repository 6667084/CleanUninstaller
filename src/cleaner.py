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

    def scan_residuals(self, package_name: str, source: str = "apt") -> List[ResidualItem]:
        self._cancelled = False
        items = []

        if source == "apt":
            items.extend(self._scan_config_files(package_name))
            items.extend(self._scan_cache_files(package_name))
            items.extend(self._scan_user_data(package_name))
            items.extend(self._scan_user_config(package_name))
            items.extend(self._scan_user_cache(package_name))
            items.extend(self._scan_system_cache(package_name))
            items.extend(self._scan_orphan_deps())
        elif source == "flatpak":
            items.extend(self._scan_flatpak_user_data(package_name))

        items = [item for item in items if item.exists]
        return items

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

    def _scan_config_files(self, package_name: str) -> List[ResidualItem]:
        items = []
        config_dirs = [
            f"/etc/{package_name}",
            f"/etc/{package_name}.d",
            f"/usr/local/etc/{package_name}",
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

    def _scan_cache_files(self, package_name: str) -> List[ResidualItem]:
        items = []
        cache_patterns = [
            f"/var/cache/{package_name}",
            f"/var/cache/apt/archives/{package_name}*",
            f"/var/lib/{package_name}",
            f"/var/log/{package_name}*",
            f"/tmp/{package_name}*",
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

    def _scan_user_data(self, package_name: str) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        data_patterns = [
            os.path.join(home, ".local", "share", package_name),
            os.path.join(home, f".{package_name}"),
        ]
        short_name = package_name.split("-")[0] if "-" in package_name else package_name
        data_patterns.append(os.path.join(home, f".{short_name}"))

        for pattern in data_patterns:
            if os.path.exists(pattern):
                size = self._get_dir_size(pattern)
                items.append(ResidualItem(
                    path=pattern,
                    item_type="用户数据",
                    size=size,
                    description=f"用户数据目录: {pattern}"
                ))

        return items

    def _scan_user_config(self, package_name: str) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        config_base = os.path.join(home, ".config")

        config_paths = [
            os.path.join(config_base, package_name),
        ]
        short_name = package_name.split("-")[0] if "-" in package_name else package_name
        config_paths.append(os.path.join(config_base, short_name))

        config_file_patterns = [
            os.path.join(home, f".{package_name}rc"),
            os.path.join(home, f".{short_name}rc"),
            os.path.join(home, f".{package_name}.conf"),
            os.path.join(home, f".{short_name}.conf"),
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

        for p in config_file_patterns:
            if os.path.exists(p):
                size = os.path.getsize(p)
                items.append(ResidualItem(
                    path=p,
                    item_type="用户配置文件",
                    size=size,
                    description=f"用户配置文件: {p}"
                ))

        return items

    def _scan_user_cache(self, package_name: str) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        cache_base = os.path.join(home, ".cache")

        cache_paths = [
            os.path.join(cache_base, package_name),
        ]
        short_name = package_name.split("-")[0] if "-" in package_name else package_name
        cache_paths.append(os.path.join(cache_base, short_name))

        for p in cache_paths:
            if os.path.exists(p):
                size = self._get_dir_size(p)
                items.append(ResidualItem(
                    path=p,
                    item_type="用户缓存",
                    size=size,
                    description=f"用户缓存目录: {p}"
                ))

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

    def _scan_flatpak_user_data(self, package_name: str) -> List[ResidualItem]:
        items = []
        home = os.path.expanduser("~")
        flatpak_data = os.path.join(home, ".local", "share", "flatpak")

        clean_name = package_name.replace(".", "_").replace("/", "_")
        patterns = [
            os.path.join(flatpak_data, clean_name),
        ]

        for p in patterns:
            if os.path.exists(p):
                size = self._get_dir_size(p)
                items.append(ResidualItem(
                    path=p,
                    item_type="Flatpak 用户数据",
                    size=size,
                    description=f"Flatpak 应用数据: {p}"
                ))

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
