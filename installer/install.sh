#!/bin/bash
set -e

APP_NAME="Clean Uninstaller"
INSTALL_DIR="/opt/clean-uninstaller"
DESKTOP_FILE="/usr/share/applications/clean-uninstaller.desktop"
BIN_LINK="/usr/local/bin/clean-uninstaller"

echo "========================================"
echo "  ${APP_NAME} - 安装程序"
echo "========================================"
echo ""

if [ "$(id -u)" -ne 0 ]; then
    echo "需要管理员权限，正在请求权限提升..."
    exec pkexec "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "${SCRIPT_DIR}/src" ]; then
    echo "错误: 找不到源代码目录，请确认安装包完整性"
    exit 1
fi

echo "正在安装 ${APP_NAME}..."
echo ""

echo "[1/5] 创建安装目录..."
rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

echo "[2/5] 复制文件..."
cp -r "${SCRIPT_DIR}/src" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/resources" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/clean-uninstaller" "${INSTALL_DIR}/"

echo "[3/5] 设置权限..."
chmod +x "${INSTALL_DIR}/clean-uninstaller"
chmod +x "${INSTALL_DIR}/src/main.py"
find "${INSTALL_DIR}" -type d -exec chmod 755 {} \;
find "${INSTALL_DIR}" -type f -exec chmod 644 {} \;
chmod 755 "${INSTALL_DIR}/clean-uninstaller"
chmod 755 "${INSTALL_DIR}/src/main.py"

echo "[4/5] 创建桌面快捷方式..."
cp "${INSTALL_DIR}/resources/clean-uninstaller.desktop" "${DESKTOP_FILE}"
chmod 644 "${DESKTOP_FILE}"
update-desktop-database /usr/share/applications/ 2>/dev/null || true

ln -sf "${INSTALL_DIR}/clean-uninstaller" "${BIN_LINK}" 2>/dev/null || true

echo "[5/5] 验证安装..."
if [ -f "${INSTALL_DIR}/clean-uninstaller" ] && [ -f "${DESKTOP_FILE}" ]; then
    echo ""
    echo "========================================"
    echo "  ✓ ${APP_NAME} 安装成功！"
    echo "========================================"
    echo ""
    echo "  安装位置: ${INSTALL_DIR}"
    echo "  桌面入口: ${DESKTOP_FILE}"
    echo "  命令行:   clean-uninstaller"
    echo ""
    echo "  您可以通过以下方式启动："
    echo "  - 应用程序菜单中搜索「干净卸载」"
    echo "  - 终端中运行 clean-uninstaller"
    echo ""
else
    echo "安装可能存在问题，请检查文件是否存在。"
    exit 1
fi

exit 0
