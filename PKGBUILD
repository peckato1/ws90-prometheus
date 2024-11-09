_pkgname=ws90-prometheus
pkgname="${_pkgname}-git"
pkgver="1"
pkgrel='1'
pkgdesc="Prometheus scraping and monitoring for WS90 weather station"
arch=('any')
url='https://github.com/peckato1/ws90-prometheus'
license=('MIT')
depends=('python' 'systemd' 'python-systemd' 'rtl_433')
source=('git+https://github.com/peckato1/ws90-prometheus.git')
sha256sums=('SKIP')

pkgver() {
  cd "${_pkgname}"
  git describe --long --abbrev=7 | sed 's/\([^-]*-g\)/r\1/;s/-/./g'
}

package() {
  cd "${srcdir}"
  install -Dm755 "${_pkgname}/ws90-prometheus.py" "${pkgdir}/usr/bin/ws90-prometheus"
  install -Dm644 "${_pkgname}/ws90-prometheus.service" "${pkgdir}/usr/lib/systemd/system/ws90-prometheus.service"
}
