import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable


@dataclass
class AppInfo:
    name: str
    package_name: str
    version: str
    description: str
    size: str
    install_date: str = ""
    category: str = ""
    source: str = ""
    icon_name: str = ""
    dependencies: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    auto_removable: bool = False

    @property
    def display_name(self) -> str:
        return self.name if self.name else self.package_name

    @property
    def display_size(self) -> str:
        if self.size:
            return self.size
        return ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "package_name": self.package_name,
            "version": self.version,
            "description": self.description,
            "size": self.size,
            "install_date": self.install_date,
            "category": self.category,
            "source": self.source,
            "icon_name": self.icon_name,
        }


class AppScanner:
    def __init__(self):
        self._apps: List[AppInfo] = []
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def get_installed_apps(self, progress_callback: Optional[Callable] = None) -> List[AppInfo]:
        self._cancelled = False
        self._apps = []

        if progress_callback:
            progress_callback(0.0, "正在扫描 APT/DPKG 已安装软件...")

        apt_apps = self._scan_apt_packages(progress_callback)
        self._apps.extend(apt_apps)

        if self._cancelled:
            return self._apps

        if progress_callback:
            progress_callback(0.7, "正在扫描 Flatpak 已安装软件...")

        flatpak_apps = self._scan_flatpak_packages(progress_callback)
        self._apps.extend(flatpak_apps)

        if progress_callback:
            progress_callback(1.0, "扫描完成")

        self._apps.sort(key=lambda x: x.display_name.lower())
        return self._apps

    def _scan_apt_packages(self, progress_callback=None) -> List[AppInfo]:
        apps = []
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\t${Installed-Size}\t${Description}\t${Section}\t${Priority}\n"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                return apps

            lines = result.stdout.strip().split("\n")
            total = len(lines)

            desktop_files = self._get_desktop_file_map()
            desktop_pkgs = self._get_desktop_package_map()

            manually_installed = self._get_manually_installed_set()

            for i, line in enumerate(lines):
                if self._cancelled:
                    break

                if progress_callback and i % 200 == 0:
                    progress_callback(0.0 + (i / total) * 0.6, f"正在解析软件包 ({i}/{total})...")

                parts = line.split("\t")
                if len(parts) < 4:
                    continue

                pkg_name = parts[0].strip()
                version = parts[1].strip()
                status = parts[2].strip()
                installed_size_kb = parts[3].strip()

                if "install ok installed" not in status:
                    continue

                description = parts[4].strip() if len(parts) > 4 else ""
                section = parts[5].strip() if len(parts) > 5 else ""
                priority = parts[6].strip() if len(parts) > 6 else ""

                if self._is_system_package(pkg_name):
                    continue

                has_desktop = pkg_name in desktop_pkgs or pkg_name in desktop_files
                is_manual = pkg_name in manually_installed
                is_user_section = section in ("web", "editors", "graphics", "video", "audio", "games", "office", "science", "math", "doc", "mail", "news", "misc", "utils", "net", "comm", "electronics", "embedded", "hamradio", "interpreters", "tex", "text", "vcs", "x11")

                if not has_desktop and not is_manual and not is_user_section:
                    continue

                size_str = self._format_size(installed_size_kb)

                display_name = pkg_name
                icon_name = ""
                if pkg_name in desktop_files:
                    df = desktop_files[pkg_name]
                    display_name = df.get("name", pkg_name)
                    icon_name = df.get("icon", "")

                install_date = self._get_install_date(pkg_name)

                app = AppInfo(
                    name=display_name,
                    package_name=pkg_name,
                    version=version,
                    description=description.split("\n")[0] if description else "",
                    size=size_str,
                    install_date=install_date,
                    category=section,
                    source="apt",
                    icon_name=icon_name,
                )
                apps.append(app)

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception) as e:
            print(f"APT 扫描错误: {e}")

        return apps

    def _get_manually_installed_set(self) -> set:
        manual = set()
        try:
            result = subprocess.run(
                ["apt-mark", "showmanual"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line:
                        manual.add(line)
        except Exception:
            pass
        return manual

    def _get_desktop_package_map(self) -> set:
        pkgs = set()
        try:
            result = subprocess.run(
                ["dpkg", "-S", ".desktop"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if ":" in line and "/usr/share/applications/" in line:
                        pkg = line.split(":")[0].strip()
                        if "," in pkg:
                            for p in pkg.split(","):
                                pkgs.add(p.strip())
                        else:
                            pkgs.add(pkg)
        except Exception:
            pass
        return pkgs

    def _scan_flatpak_packages(self, progress_callback=None) -> List[AppInfo]:
        apps = []
        try:
            result = subprocess.run(
                ["flatpak", "list", "--app", "--columns=name,application,version,branch,size,installation"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                return apps

            lines = result.stdout.strip().split("\n")
            for line in lines:
                if self._cancelled:
                    break

                parts = line.split("\t")
                if len(parts) < 4:
                    continue

                app = AppInfo(
                    name=parts[0].strip(),
                    package_name=parts[1].strip() if len(parts) > 1 else parts[0].strip(),
                    version=parts[2].strip() if len(parts) > 2 else "",
                    description="Flatpak 应用",
                    size=parts[4].strip() if len(parts) > 4 else "",
                    category="",
                    source="flatpak",
                    icon_name="",
                )
                apps.append(app)

        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception):
            pass

        return apps

    def _get_desktop_file_map(self) -> dict:
        desktop_map = {}
        search_dirs = [
            "/usr/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            "/var/lib/flatpak/exports/share/applications",
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
        ]

        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue
            try:
                for fname in os.listdir(search_dir):
                    if not fname.endswith(".desktop"):
                        continue
                    fpath = os.path.join(search_dir, fname)
                    try:
                        info = self._parse_desktop_file(fpath)
                        if info and info.get("exec_pkg"):
                            desktop_map[info["exec_pkg"]] = {
                                "name": info.get("name", ""),
                                "icon": info.get("icon", ""),
                            }
                    except Exception:
                        continue
            except Exception:
                continue

        return desktop_map

    def _parse_desktop_file(self, filepath: str) -> Optional[dict]:
        info = {}
        in_desktop_entry = False
        try:
            with open(filepath, "r", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line == "[Desktop Entry]":
                        in_desktop_entry = True
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        in_desktop_entry = False
                        continue
                    if not in_desktop_entry or "=" not in line:
                        continue

                    key, _, value = line.partition("=")
                    key = key.strip()

                    if key == "Name":
                        info["name"] = value.strip()
                    elif key == "Icon":
                        info["icon"] = value.strip()
                    elif key == "Exec":
                        exec_cmd = value.strip().split()[0] if value.strip() else ""
                        exec_name = os.path.basename(exec_cmd)
                        info["exec_pkg"] = exec_name

                    if "name" in info and "icon" in info and "exec_pkg" in info:
                        break
        except Exception:
            return None

        return info if info.get("name") else None

    SYSTEM_PREFIXES = [
        "lib", "gcc-", "g++-", "cpp-", "linux-", "grub", "systemd", "dbus",
        "coreutils", "bash", "dash", "zsh", "ksh", "tzdata", "base-",
        "python3", "perl", "perl-", "dpkg", "apt", "snap", "gnupg", "gpg",
        "lsb-", "hostname", "login", "passwd", "shadow", "sudo", "policykit",
        "udev", "init", "sysvinit", "upstart", "initramfs", "os-prober",
        "ca-certificates", "debconf", "fonts-", "xserver-", "xorg",
        "mesa-", "drm", "netplan", "networkd", "apparmor", "snapd",
        "fwupd", "udisks", "upower", "accountsservice", "bolt", "colord",
        "geoclue", "gstreamer", "gvfs", "json-", "libaccounts", "libsignon",
        "mobile-broadband", "modemmanager", "networkmanager", "packagekit",
        "pulseaudio", "rfkill", "secureboot", "speech-dispatcher", "spice-",
        "telepathy-", "tracker-", "uchardet", "usb-creator", "whoopsie",
        "iso-codes", "libsecret", "libsoup", "webkit", "openssh", "openssl",
        "gnutls", "p11-kit", "libpam", "acl", "adduser", "adwaita",
        "alsa-", "amd64-microcode", "anacron", "apport", "apt-", "at-spi",
        "base-files", "base-passwd", "bind9-", "binutils", "bsd-", "btrfs-",
        "busybox", "cloud-", "cm-super", "console-", "core-", "cpio",
        "crda", "cron", "cryptsetup", "cups-", "dash", "dconf-",
        "default-", "dictionaries-", "diffutils", "dirmngr", "discover-",
        "distro-info", "dmidecode", "dmsetup", "dns-root-data", "dosfstools",
        "dpkg-", "e2fsprogs", "efibootmgr", "exfatprogs", "fdisk",
        "file-", "findutils", "folks", "font-", "foomatic", "fuse",
        "gcr-", "gdk-pixbuf-", "gettext-", "ghostscript", "glib", "gnome-",
        "gpg-", "grep", "groff-", "gsettings-", "gtk-", "hardening-",
        "hicolor-", "hostname", "hplip-", "humanity-", "hwdata", "iio-",
        "im-config", "info-", "init-", "intltool", "ip-", "ipp-",
        "irqbalance", "iscan-", "kbd", "keyboard-", "kmod", "krb5-",
        "lcms-", "less", "lib", "lm-sensors", "locale-", "logind",
        "lvm2", "lz4", "m17n-", "make-", "manpages-", "mawk", "memtest",
        "mutter", "nano", "ncurses-", "net-", "nftables", "ntfs",
        "nvidia-", "openjdk-", "openprinting", "os-prober", "p11-",
        "pam-", "parted", "patch", "pciutils", "pcr-", "pinentry-",
        "pkg-config", "plymouth", "polkit-", "poppler", "ppp", "procps",
        "publicsuffix", "py3clean", "python3-", "readline-",
        "resolvconf", "rlwrap", "rsyslog", "run-one", "samba-",
        "seahorse-", "sed", "sensible-", "sgml-", "shared-mime-",
        "shim-", "simple-scan", "snap-", "software-properties-",
        "sound-", "ssh-", "ssl-", "switch-", "sys-", "systemd-",
        "tar", "tex-", "thunderbird-", "time-", "tmux", "tp-smapi-",
        "traceroute", "tree", "ubuntu-", "ucf", "udev", "uidmap",
        "unzip", "update-", "upstart-", "usb-", "util-linux",
        "uuid-", "vim-", "vte-", "wget", "whiptail", "wireless-",
        "wpasupplicant", "x11-", "xauth", "xdg-", "xfsprogs", "xkb-",
        "xml-", "xorg-", "xrandr", "xsltproc", "yad", "yelp-",
        "zenity", "zip", "zlib", "zstd", "gpg", "gpgconf", "gpgsm",
        "dirmngr", "gnupg-", "gpg-agent", "gpg-wks-", "gpgv",
    ]

    SYSTEM_EXACT = {
        "acl", "adduser", "apport", "apt", "apt-utils", "base-files",
        "base-passwd", "bash", "bc", "bind9-host", "binutils",
        "bsdutils", "bzip2", "ca-certificates", "cmdline", "coreutils",
        "cpio", "cron", "curl", "dash", "dbus", "debconf", "diffutils",
        "dirmngr", "dmsetup", "dpkg", "e2fsprogs", "fdisk", "file",
        "findutils", "gcc-12-base", "gcc-13-base", "gcc-14-base",
        "gpg", "gpgv", "grep", "groff-base", "gzip", "hostname",
        "init", "iproute2", "iptables", "iputils-ping", "isc-dhcp-",
        "kmod", "less", "locales", "login", "logsave", "lsb-release",
        "mawk", "mount", "nano", "ncurses-base", "ncurses-bin",
        "netbase", "nftables", "openresolv", "openssh-client",
        "openssl", "passwd", "patch", "pciutils", "perl",
        "perl-base", "plymouth", "policykit-1", "procps", "psmisc",
        "readline-common", "resolvconf", "rsyslog", "sed",
        "sensible-utils", "snapd", "sudo", "systemd", "sysvinit-utils",
        "tar", "tzdata", "ubuntu-keyring", "ucf", "udev",
        "util-linux", "vim-common", "vim-tiny", "wget", "whiptail",
        "xauth", "zlib1g", "zstd", "7zip", "apg", "app-install-data",
        "appstream", "aspell", "aspell-en", "attr", "avahi-autoipd",
        "avahi-daemon", "avahi-utils", "blueman", "bluetooth",
        "bluez", "bluez-cups", "bluez-obexd", "brasero-common",
        "brltty", "bsdextrautils", "bubblewrap", "crda", "cryptsetup",
        "cups", "cups-browsed", "cups-bsd", "cups-client",
        "cups-common", "cups-core-drivers", "cups-daemon",
        "cups-filters", "cups-ipp-utils", "cups-ppdc",
        "cups-server-common", "dconf-cli", "dconf-gsettings-backend",
        "dconf-service", "dcraw", "dictionaries-common", "diffutils",
        "distro-info", "distro-info-data", "dmidecode", "dosfstools",
        "dpkg-dev", "emacsen-common", "evolution-data-server",
        "evolution-data-server-common", "exfatprogs", "fdisk",
        "foomatic-db", "foomatic-db-engine", "foomatic-filters",
        "fuse3", "gcr", "gcr4", "gdb", "gdisk", "ghostscript",
        "ghostscript-x", "gpgconf", "gpgsm", "gsettings-desktop-schemas",
        "gvfs", "gvfs-backends", "gvfs-common", "gvfs-daemons",
        "gvfs-libs", "hplip", "hplip-data", "humanity-icon-theme",
        "hunspell-en-us", "hwdata", "iio-sensor-proxy", "im-config",
        "irqbalance", "kbd", "keyboard-configuration", "krb5-locales",
        "laptop-detect", "lcms2", "liba", "lm-sensors",
        "localepurge", "lsof", "lvm2", "man-db", "manpages",
        "media-player-info", "mesa-utils", "mobile-broadband-provider-info",
        "modemmanager", "mousetweaks", "mtools", "mutter",
        "nala", "net-tools", "netpbm", "ntfs-3g", "ntpsec",
        "obex-data-server", "p11-kit", "p7zip-full", "parted",
        "patch", "pinentry-curses", "pinentry-gnome3", "pkg-config",
        "poppler-data", "poppler-utils", "ppp", "pppconfig",
        "pptp-linux", "printer-driver-", "pulseaudio",
        "pulseaudio-module-bluetooth", "pulseaudio-utils",
        "python3-apport", "python3-apt", "python3-blinker",
        "python3-cffi", "python3-chardet", "python3-click",
        "python3-colorama", "python3-cryptography", "python3-dbus",
        "python3-debian", "python3-distro", "python3-gi",
        "python3-jwt", "python3-keyring", "python3-launchpadlib",
        "python3-lazr", "python3-netaddr", "python3-oauthlib",
        "python3-pil", "python3-problem-report", "python3-pyaes",
        "python3-secretstorage", "python3-setuptools",
        "python3-simplejson", "python3-six", "python3-softwareproperties",
        "python3-systemd", "python3-urllib3", "python3-xdg",
        "rpcbind", "rsync", "rygel", "sane-utils", "sbsigntool",
        "screen", "secureboot-db", "sgml-base", "shared-mime-info",
        "smbclient", "snap", "software-properties-common",
        "software-properties-gtk", "sound-theme-freedesktop",
        "speech-dispatcher", "spice-vdagent", "ssh", "ssh-askpass",
        "ssl-cert", "strace", "sudo", "switcheroo-control",
        "sysfsutils", "system-config-printer",
        "system-config-printer-common", "system-config-printer-udev",
        "task-english", "task-print-server", "telnet",
        "thunderbird", "time", "tmux", "tracker", "ttf-",
        "ubuntu-advantage-tools", "ubuntu-minimal", "ubuntu-release-upgrader",
        "ubuntu-release-upgrader-core", "ubuntu-release-upgrader-gtk",
        "ubuntu-standard", "ucf", "udisks2", "unzip", "update-inetd",
        "update-manager", "update-manager-core", "update-notifier",
        "update-notifier-common", "upower", "usb-modeswitch",
        "usb-modeswitch-data", "usb.ids", "util-linux", "uuid",
        "vim", "vim-common", "vim-tiny", "vino", "vpnc",
        "wamerican", "wget", "whoopsie", "wireless-tools",
        "wpasupplicant", "x11-common", "x11-utils", "x11-xkb-utils",
        "x11-xserver-utils", "xdg-desktop-portal",
        "xdg-desktop-portal-gnome", "xdg-desktop-portal-gtk",
        "xdg-user-dirs", "xdg-user-dirs-gtk", "xdg-utils",
        "xinput", "xserver-common", "xserver-xorg", "xsltproc",
        "yad", "yelp", "zenity", "zip",
    }

    def _is_system_package(self, pkg_name: str) -> bool:
        if pkg_name in self.SYSTEM_EXACT:
            return True
        for prefix in self.SYSTEM_PREFIXES:
            if pkg_name.startswith(prefix):
                return True
        return False

    def _get_install_date(self, pkg_name: str) -> str:
        try:
            log_path = "/var/log/dpkg.log"
            if not os.path.exists(log_path):
                return ""
            result = subprocess.run(
                ["grep", f"status installed {pkg_name}", log_path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                last_line = result.stdout.strip().split("\n")[-1]
                date_part = last_line.split()[0] if last_line else ""
                if date_part and len(date_part) >= 10:
                    return date_part[:10]
        except Exception:
            pass
        return ""

    @staticmethod
    def _format_size(size_kb_str: str) -> str:
        try:
            size_kb = float(size_kb_str)
            if size_kb < 1:
                return ""
            elif size_kb < 1024:
                return f"{size_kb:.0f} KB"
            elif size_kb < 1024 * 1024:
                return f"{size_kb / 1024:.1f} MB"
            else:
                return f"{size_kb / (1024 * 1024):.2f} GB"
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def get_package_files(package_name: str) -> List[str]:
        try:
            result = subprocess.run(
                ["dpkg", "-L", package_name],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return [f for f in result.stdout.strip().split("\n") if f and os.path.exists(f)]
        except Exception:
            pass
        return []

    @staticmethod
    def get_package_dependencies(package_name: str) -> List[str]:
        try:
            result = subprocess.run(
                ["apt-cache", "depends", "--installed", package_name],
                capture_output=True, text=True, timeout=30
            )
            deps = []
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("Depends:"):
                        dep = line.replace("Depends:", "").strip()
                        if dep:
                            deps.append(dep)
            return deps
        except Exception:
            return []

    @staticmethod
    def get_auto_removable_deps(package_name: str) -> List[str]:
        try:
            result = subprocess.run(
                ["apt-get", "-s", "autoremove", "--purge", package_name],
                capture_output=True, text=True, timeout=30
            )
            pkgs = []
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("Remv "):
                        parts = line.split()
                        if len(parts) >= 2:
                            pkgs.append(parts[1])
            return pkgs
        except Exception:
            return []
