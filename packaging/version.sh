# Sourced by build_deb.sh and build_rpm.sh to work out the version being built.
#   VERSION      application version: 0.5.0 for a release (DUPLIBACK_RELEASE set),
#                0.5.0-<short commit> otherwise
#   PKG_VERSION  the same for package metadata, with '~' instead of '-' so dpkg and
#                rpm sort an unreleased build before the release it leads up to
set_versions() {
    VERSION="$(python3 dupliback/src/settings.py)"
    PKG_VERSION="${VERSION//-/\~}"
}

# records the exact version in the package, which has no git checkout to ask
write_build_version() {
    echo "PROGRAM_VERSION = '${VERSION}'" > "$1/build_version.py"
}
