#!/usr/bin/bash

source "$(dirname "$0")/packaging/build_common.sh"

clean_package() {
    echo "Cleaning Package & Build related Files"
    rm -rf debian/
    rm -f dupli.back-*.deb
}

build_package() {
    set -e
    set_versions
    echo "Build Package (Ver:" $VERSION ")"
    # start from an empty tree so files from older builds are not packaged
    rm -rf debian/
    mkdir -p debian/DEBIAN debian/usr/share/applications
    stage_app debian/usr/share/dupliback
    cp packaging/deb/control debian/DEBIAN/
    # the version comes from settings.py only
    sed -i "s/@VERSION@/${PKG_VERSION}/" debian/DEBIAN/control
    cp packaging/dupliback.desktop debian/usr/share/applications/
    # build package
    dpkg-deb --root-owner-group --build debian
    mv debian.deb dupli.back-$VERSION.deb
    set +e
}

parse_args "$@"
