# Sourced by build_deb.sh and build_rpm.sh, which define clean_package and
# build_package and then call parse_args "$@".

SRC_DIR="dupliback/src"

# Sets the version being built:
#   VERSION      0.5.0 for a release (DUPLIBACK_RELEASE set), else
#                0.5.0-<short commit>
#   PKG_VERSION  VERSION with '~' for '-', so dpkg and rpm sort an
#                unreleased build before its release
set_versions() {
    VERSION="$(python3 ${SRC_DIR}/settings.py)"
    PKG_VERSION="${VERSION//-/\~}"
}

# records the exact version in the package, which has no git checkout to ask
write_build_version() {
    echo "PROGRAM_VERSION = '${VERSION}'" > "$1/build_version.py"
}

# copies the application (modules, build_version.py, glade/, images/) into $1;
# any further arguments are cp options for the modules
stage_app() {
    local dest="$1"
    shift
    mkdir -p "$dest/glade" "$dest/images"
    cp "$@" ${SRC_DIR}/*.py "$dest/"
    write_build_version "$dest"
    cp ${SRC_DIR}/glade/*.glade "$dest/glade/"
    cp ${SRC_DIR}/images/* "$dest/images/"
}

parse_args() {
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
                echo "   -r|--release - builds a release (no commit in the" \
                     "version), use before -b"
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
}
