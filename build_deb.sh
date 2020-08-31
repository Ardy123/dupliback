#!/usr/bin/bash

VERSION="`python dupliback/settings.py`"
VERSION="${VERSION}_r`git rev-list --count HEAD`"

clean_package() {
    echo "Cleaning Package & Buid related Files"
    rm -rf debian/
    rm dupli.back-*
}

build_package() {
    echo "Build Package (Ver:" $VERSION ")"
    # make necessary directories
    mkdir -p debian/DEBIAN
    mkdir -p debian/usr/share/dupliback/glade
    mkdir -p debian/usr/share/dupliback/images
    mkdir -p debian/usr/share/applications
    # copy files over
    cp dupliback/*.py debian/usr/share/dupliback/
    cp dupliback/glade/*.glade debian/usr/share/dupliback/glade/
    cp dupliback/images/* debian/usr/share/dupliback/images/
    cp packaging/deb/control debian/DEBIAN/
    cp packaging/dupliback.desktop debian/usr/share/applications/
    # build package
    dpkg-deb --build debian
    mv debian.deb dupli.back-$VERSION.deb
}

while [ -n "$1" ]; do
    case "$1" in
	-b|--build)
	    build_package
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
