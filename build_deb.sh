#!/usr/bin/bash

SRC_DIR="dupliback/src"
source "$(dirname "$0")/packaging/version.sh"

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
    # make necessary directories
    mkdir -p debian/DEBIAN
    mkdir -p debian/usr/share/dupliback/glade
    mkdir -p debian/usr/share/dupliback/images
    mkdir -p debian/usr/share/applications
    # copy files over
    cp ${SRC_DIR}/*.py debian/usr/share/dupliback/
    write_build_version debian/usr/share/dupliback
    cp ${SRC_DIR}/glade/*.glade debian/usr/share/dupliback/glade/
    cp ${SRC_DIR}/images/* debian/usr/share/dupliback/images/
    cp packaging/deb/control debian/DEBIAN/
    # the version comes from settings.py only
    sed -i "s/@VERSION@/${PKG_VERSION}/" debian/DEBIAN/control
    cp packaging/dupliback.desktop debian/usr/share/applications/
    # build package
    dpkg-deb --root-owner-group --build debian
    mv debian.deb dupli.back-$VERSION.deb
    set +e
}

while [ -n "$1" ]; do
    case "$1" in
	-b|--build)
	    build_package
	    ;;
	-r|--release)
	    # build the release version, without the commit suffix
	    export DUPLIBACK_RELEASE=1
	    ;;
	-c|--clean)
	    clean_package
	    ;;
	-d|--debug)
	    set -x
	    ;;
	-h|--help)
	    echo "Arguments:"
	    echo "   -b|--build - builds the package"
	    echo "   -r|--release - builds a release (version without commit), use before -b"
	    echo "   -c|--clean - cleans the package"
	    echo "   -d|--debug - enables verbose output"
	    echo "   -h|--help  - this message"
	    break
	    ;;
	*)
	    echo "Option $1 not recognized"
	    break
	    ;;
    esac
    shift
done
