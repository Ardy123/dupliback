#!/usr/bin/bash

SRC_DIR="dupliback/src"
source "$(dirname "$0")/packaging/version.sh"

clean_package() {
    echo "Cleaning Package & Build related Files"
    rm -rf rpmbuild/
    rm -f dupli.back-*.rpm
}

build_package() {
    set -e
    set_versions
    echo "Build Package (Ver:" $VERSION ")"
    # stage the application files where the spec file expects them
    rm -rf rpmbuild/
    mkdir -p rpmbuild/SOURCES/src/glade rpmbuild/SOURCES/src/images
    cp -p ${SRC_DIR}/*.py rpmbuild/SOURCES/src/
    write_build_version rpmbuild/SOURCES/src
    cp ${SRC_DIR}/glade/*.glade rpmbuild/SOURCES/src/glade/
    cp ${SRC_DIR}/images/* rpmbuild/SOURCES/src/images/
    cp packaging/dupliback.desktop COPYING rpmbuild/SOURCES/
    # build package
    rpmbuild --define "_topdir $PWD/rpmbuild" --define "pkg_version ${PKG_VERSION}" \
        -bb packaging/rpm/dupliback.spec
    mv rpmbuild/RPMS/noarch/dupli.back-${PKG_VERSION}-1.noarch.rpm dupli.back-${VERSION}.noarch.rpm
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
