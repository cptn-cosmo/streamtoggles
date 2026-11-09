# Maintainer: Cosmo <cosmo@example.com>
pkgname=streamtoggles
pkgver=1.0.0
pkgrel=1
pkgdesc="Macro pad and toggle controller for Linux desktop streaming setups"
arch=('any')
url="https://github.com/cptn-cosmo/streamtoggles"
license=('MIT')
depends=(
  'python'
  'python-pyqt6'
  'qt6-base'
  'qt6-svg'
)
makedepends=(
  'python-build'
  'python-installer'
  'python-setuptools'
  'python-wheel'
)
optdepends=(
  'xdg-desktop-portal: Global shortcuts support across Wayland, KDE Plasma, and GNOME'
  'xdg-desktop-portal-kde: KDE Plasma desktop portal implementation'
  'xdg-desktop-portal-wlr: wlroots/sway desktop portal implementation'
)
checkdepends=(
  'python'
)

source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
  cd "$srcdir/$pkgname-$pkgver"
  python -m build --wheel --no-isolation
}

check() {
  cd "$srcdir/$pkgname-$pkgver"
  QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
}

package() {
  cd "$srcdir/$pkgname-$pkgver"

  # Install Python package and executable wrapper into /usr/bin
  python -m installer --destdir="$pkgdir" dist/*.whl

  # Desktop launcher entry
  install -Dm644 data/com.github.streamtoggles.StreamToggles.desktop \
    "$pkgdir/usr/share/applications/com.github.streamtoggles.StreamToggles.desktop"

  # AppStream metainfo
  install -Dm644 data/com.github.streamtoggles.StreamToggles.metainfo.xml \
    "$pkgdir/usr/share/metainfo/com.github.streamtoggles.StreamToggles.metainfo.xml"

  # Scalable vector application icon
  install -Dm644 data/icons/com.github.streamtoggles.StreamToggles.svg \
    "$pkgdir/usr/share/icons/hicolor/scalable/apps/com.github.streamtoggles.StreamToggles.svg"

  # Symbolic icon
  if [ -f data/icons/com.github.streamtoggles.StreamToggles-symbolic.svg ]; then
    install -Dm644 data/icons/com.github.streamtoggles.StreamToggles-symbolic.svg \
      "$pkgdir/usr/share/icons/hicolor/symbolic/apps/com.github.streamtoggles.StreamToggles-symbolic.svg"
  fi

  # Rasterized PNG icons (hicolor resolutions)
  for size in 16 24 32 48 64 128 256 512; do
    local icon_path="data/icons/${size}x${size}/com.github.streamtoggles.StreamToggles.png"
    if [ -f "$icon_path" ]; then
      install -Dm644 "$icon_path" \
        "$pkgdir/usr/share/icons/hicolor/${size}x${size}/apps/com.github.streamtoggles.StreamToggles.png"
    fi
  done

  # MIT License file
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
