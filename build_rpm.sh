#!/usr/bin/bash

source "$(dirname "$0")/packaging/build_common.sh"

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
    stage_app rpmbuild/SOURCES/src -p
    cp packaging/dupliback.desktop COPYING rpmbuild/SOURCES/
    # build package
    rpmbuild --define "_topdir $PWD/rpmbuild" \
        --define "pkg_version ${PKG_VERSION}" \
        --define "duplicity_version ${DUPLICITY_VERSION}" \
        -bb packaging/rpm/dupliback.spec
    mv rpmbuild/RPMS/noarch/dupli.back-${PKG_VERSION}-1.noarch.rpm \
        dupli.back-${VERSION}.noarch.rpm
    set +e
}

parse_args "$@"
