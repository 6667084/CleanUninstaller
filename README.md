# 🗑️ Clean Uninstaller (干净卸载)

一款适用于 Linux 的应用程序彻底卸载工具，专为 Linux Mint / Ubuntu / Debian 设计。

![License](https://img.shields.io/badge/license-GPL--3.0-blue)
![Platform](https://img.shields.io/badge/platform-Linux-green)
![Python](https://img.shields.io/badge/Python-3.8+-yellow)

## ✨ 功能特性

- 🔍 **智能扫描** - 自动扫描 APT/DPKG 和 Flatpak 已安装应用，智能过滤系统包
- 🗑️ **彻底卸载** - 完整卸载应用程序，支持 purge 模式清除配置
- 🧹 **残留清理** - 自动清理配置文件、缓存、用户数据、日志、孤立依赖
- ✅ **确认机制** - 卸载前确认对话框，防止误操作
- 📊 **清理报告** - 详细的卸载和清理结果报告
- 🔎 **搜索过滤** - 按名称/包名搜索，按来源/大小分类
- 🎨 **现代界面** - 基于 GTK3 的原生 Linux 桌面界面

## 📦 安装

### 方式一：.deb 安装包（推荐）

```bash
sudo dpkg -i clean-uninstaller-v1.1.1-Linux-x86_64.deb
sudo apt-get install -f
```

### 方式二：从源码运行

```bash
git clone https://github.com/6667084/CleanUninstaller.git
cd CleanUninstaller
python3 src/main.py
```

## 🚀 使用

- **应用菜单**: 搜索「干净卸载」或「Clean Uninstaller」
- **命令行**: 运行 `clean-uninstaller`

## 🏗️ 构建 .deb 安装包

```bash
bash build_deb.sh
```

## 🖼️ 界面预览

- 左侧分类筛选面板（全部软件 / APT 软件包 / Flatpak 应用 / 大型软件）
- 右侧软件列表（名称、包名、版本、大小、来源）
- 卸载确认对话框（可选删除配置、清理残留）
- 实时进度和日志显示
- 卸载完成后显示清理报告

## 🔧 系统要求

- Linux Mint 22+ / Ubuntu 24.04+ / Debian 12+
- Python 3.8+
- GTK3 + PyGObject (python3-gi)
- PolicyKit (pkexec)
- APT / DPKG
- Flatpak (可选)

## 📄 许可证

GPL-3.0 License
