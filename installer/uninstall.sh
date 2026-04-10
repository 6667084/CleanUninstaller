#!/bin/bash
set -e

APP_NAME="Clean Uninstaller"
INSTALL_DIR="/opt/clean-uninstaller"
DESKTOP_FILE="/usr/share/applications/clean-uninstaller.desktop"
BIN_LINK="/usr/local/bin/clean-uninstaller"

echo "========================================"
echo "  ${APP_NAME} - 卸载程序"
echo "========================================"
echo ""

if [ "$(id -u)" -ne 0 ]; then
    echo "需要管理员权限，正在请求权限提升..."
    exec pkexec "$0" "$@"
fi

echo "正在卸载 ${APP_NAME}..."
echo ""

read -p "确认要卸载 ${APP_NAME} 吗？(y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消卸载。"
    exit 0
fi

echo "[1/4] 移除桌面快捷方式..."
rm -f "${DESKTOP_FILE}"
update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo "[2/4] 移除命令行链接..."
rm -f "${BIN_LINK}"

echo "[3/4] 删除安装目录..."
rm -rf "${INSTALL_DIR}"

echo "[4/4] 清理完成..."

if [ ! -d "${INSTALL_DIR}" ]; then
    echo ""
    echo "========================================"
    echo "  ✓ ${APP_NAME} 已成功卸载！"
    echo "========================================"
    echo ""
else
    echo "卸载可能不完整，请手动检查 ${INSTALL_DIR}"
    exit 1
fi

exit 0
