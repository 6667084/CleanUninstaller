import subprocess
import os
from typing import Optional, Callable
from .scanner import AppInfo
from .cleaner import ResidualCleaner, CleanResult


class UninstallResult:
    def __init__(self):
        self.success: bool = False
        self.package_removed: bool = False
        self.residual_result: Optional[CleanResult] = None
        self.errors: list = []
        self.log: list = []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "package_removed": self.package_removed,
            "residual_result": self.residual_result.to_dict() if self.residual_result else None,
            "errors": self.errors,
            "log": self.log,
        }


class Uninstaller:
    def __init__(self):
        self._cancelled = False
        self._process = None

    def cancel(self):
        self._cancelled = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass

    def uninstall_app(
        self,
        app: AppInfo,
        remove_config: bool = True,
        remove_residuals: bool = True,
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
    ) -> UninstallResult:
        self._cancelled = False
        result = UninstallResult()

        try:
            if progress_callback:
                progress_callback(0.0, f"正在准备卸载 {app.display_name}...")

            if log_callback:
                log_callback(f"开始卸载: {app.display_name} ({app.package_name})")

            if app.source == "apt":
                success = self._uninstall_apt(app, remove_config, progress_callback, log_callback, result)
            elif app.source == "flatpak":
                success = self._uninstall_flatpak(app, progress_callback, log_callback, result)
            else:
                result.errors.append(f"不支持的包来源: {app.source}")
                return result

            result.package_removed = success
            if not success:
                result.errors.append("软件包卸载失败")
                return result

            if log_callback:
                log_callback("软件包卸载成功")

            if self._cancelled:
                result.success = True
                return result

            if remove_residuals:
                if progress_callback:
                    progress_callback(0.6, "正在扫描残留文件...")

                cleaner = ResidualCleaner()
                residuals = cleaner.scan_residuals(app.package_name, app.source)

                if log_callback:
                    log_callback(f"发现 {len(residuals)} 个残留项目")

                if residuals:
                    if progress_callback:
                        progress_callback(0.7, f"正在清理 {len(residuals)} 个残留项目...")

                    clean_result = cleaner.clean_residuals(
                        residuals,
                        progress_callback=lambda p, m: progress_callback(0.7 + p * 0.25, m) if progress_callback else None
                    )
                    result.residual_result = clean_result

                    if log_callback:
                        log_callback(f"清理完成: {clean_result.cleaned_items}/{clean_result.total_items} 项")
                        if clean_result.errors:
                            for err in clean_result.errors:
                                log_callback(f"警告: {err}")
                else:
                    if log_callback:
                        log_callback("未发现残留文件")

            if progress_callback:
                progress_callback(1.0, "卸载完成")

            result.success = True

        except Exception as e:
            result.errors.append(f"卸载过程中发生错误: {str(e)}")
            result.success = False

        return result

    def _uninstall_apt(
        self,
        app: AppInfo,
        remove_config: bool,
        progress_callback,
        log_callback,
        result: UninstallResult,
    ) -> bool:
        try:
            cmd = ["pkexec", "apt-get", "purge", "-y", app.package_name]
            if not remove_config:
                cmd = ["pkexec", "apt-get", "remove", "-y", app.package_name]

            if log_callback:
                log_callback(f"执行: {' '.join(cmd)}")

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
            )

            output_lines = []
            while True:
                line = self._process.stdout.readline()
                if not line and self._process.poll() is not None:
                    break
                if line:
                    line = line.strip()
                    output_lines.append(line)
                    if log_callback:
                        log_callback(line)

                    if progress_callback:
                        if "Unpacking" in line or "Setting up" in line:
                            pass
                        elif "Removing" in line:
                            progress_callback(0.2, f"正在移除 {app.package_name}...")
                        elif "Purging" in line:
                            progress_callback(0.3, f"正在清除配置 {app.package_name}...")

            self._process.wait()
            result.log = output_lines

            if self._process.returncode == 0:
                if log_callback:
                    log_callback("APT 卸载成功，正在清理自动安装的依赖...")

                try:
                    autoremove_result = subprocess.run(
                        ["pkexec", "apt-get", "autoremove", "-y", "--purge"],
                        capture_output=True, text=True, timeout=120,
                        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
                    )
                    if autoremove_result.returncode == 0 and log_callback:
                        if autoremove_result.stdout.strip():
                            log_callback("自动依赖清理完成")
                except Exception as e:
                    if log_callback:
                        log_callback(f"自动依赖清理失败: {e}")

                return True
            else:
                result.errors.append(f"APT 返回错误码: {self._process.returncode}")
                return False

        except Exception as e:
            result.errors.append(f"APT 卸载异常: {str(e)}")
            return False
        finally:
            self._process = None

    def _uninstall_flatpak(
        self,
        app: AppInfo,
        progress_callback,
        log_callback,
        result: UninstallResult,
    ) -> bool:
        try:
            cmd = ["flatpak", "uninstall", "-y", app.package_name]

            if log_callback:
                log_callback(f"执行: {' '.join(cmd)}")

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            output_lines = []
            while True:
                line = self._process.stdout.readline()
                if not line and self._process.poll() is not None:
                    break
                if line:
                    line = line.strip()
                    output_lines.append(line)
                    if log_callback:
                        log_callback(line)

                    if progress_callback:
                        if "Uninstalling" in line:
                            progress_callback(0.3, f"正在卸载 {app.display_name}...")

            self._process.wait()
            result.log = output_lines

            if self._process.returncode == 0:
                if log_callback:
                    log_callback("Flatpak 卸载成功")
                return True
            else:
                result.errors.append(f"Flatpak 返回错误码: {self._process.returncode}")
                return False

        except Exception as e:
            result.errors.append(f"Flatpak 卸载异常: {str(e)}")
            return False
        finally:
            self._process = None
