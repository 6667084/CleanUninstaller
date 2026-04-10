#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

VERSION="1.1.1"
PKG_NAME="clean-uninstaller"
DEB_NAME="${PKG_NAME}-v${VERSION}-Linux-x86_64.deb"

BUILD_DIR=$(mktemp -d)
trap "rm -rf ${BUILD_DIR}" EXIT

echo "========================================"
echo "  构建 ${DEB_NAME}"
echo "========================================"
echo ""

echo "[1/5] 创建 DEBIAN 控制文件..."
mkdir -p "${BUILD_DIR}/DEBIAN"
cp packaging/DEBIAN/control "${BUILD_DIR}/DEBIAN/control"
cp packaging/DEBIAN/postinst "${BUILD_DIR}/DEBIAN/postinst"
cp packaging/DEBIAN/prerm "${BUILD_DIR}/DEBIAN/prerm"
cp packaging/DEBIAN/postrm "${BUILD_DIR}/DEBIAN/postrm"
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"
chmod 755 "${BUILD_DIR}/DEBIAN/prerm"
chmod 755 "${BUILD_DIR}/DEBIAN/postrm"
chmod 644 "${BUILD_DIR}/DEBIAN/control"

echo "[2/5] 安装文件到 /opt/clean-uninstaller..."
mkdir -p "${BUILD_DIR}/opt/clean-uninstaller"
cp -r src "${BUILD_DIR}/opt/clean-uninstaller/"
cp -r resources "${BUILD_DIR}/opt/clean-uninstaller/"
cp clean-uninstaller "${BUILD_DIR}/opt/clean-uninstaller/"
chmod 755 "${BUILD_DIR}/opt/clean-uninstaller/clean-uninstaller"
chmod 755 "${BUILD_DIR}/opt/clean-uninstaller/src/main.py"
find "${BUILD_DIR}/opt/clean-uninstaller" -type d -exec chmod 755 {} \;
find "${BUILD_DIR}/opt/clean-uninstaller" -type f -exec chmod 644 {} \;
chmod 755 "${BUILD_DIR}/opt/clean-uninstaller/clean-uninstaller"
chmod 755 "${BUILD_DIR}/opt/clean-uninstaller/src/main.py"

echo "[3/5] 安装桌面入口..."
mkdir -p "${BUILD_DIR}/usr/share/applications"
cp resources/clean-uninstaller.desktop "${BUILD_DIR}/usr/share/applications/"
chmod 644 "${BUILD_DIR}/usr/share/applications/clean-uninstaller.desktop"

mkdir -p "${BUILD_DIR}/usr/local/bin"
ln -sf /opt/clean-uninstaller/clean-uninstaller "${BUILD_DIR}/usr/local/bin/clean-uninstaller"

echo "[4/5] 构建 .deb 包..."
dpkg-deb --build "${BUILD_DIR}" "${DEB_NAME}"

echo "[5/5] 完成！"
echo ""
echo "========================================"
echo "  ✓ 安装包构建成功"
echo "========================================"
echo ""
echo "  文件: ${DEB_NAME}"
echo "  大小: $(du -h "${DEB_NAME}" | cut -f1)"
echo ""
echo "  安装方法:"
echo "    sudo dpkg -i ${DEB_NAME}"
echo "    sudo apt-get install -f"
echo ""
echo "  卸载方法:"
echo "    sudo dpkg -r clean-uninstaller"
echo ""
