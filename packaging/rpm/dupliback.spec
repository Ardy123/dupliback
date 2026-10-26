# Built by build_rpm.sh, which stages the application files in the rpmbuild
# SOURCES directory and defines pkg_version from dupliback/src/settings.py.
%global __brp_python_bytecompile %{nil}
%global _python_bytecompile_extra 0

Name:           dupli.back
Version:        %{pkg_version}
Release:        1
Summary:        dupli.back Backup software
License:        GPL-2.0-only
URL:            https://github.com/Ardy123/dupliback
Packager:       QVXLabs LLC <afalls@qvxlabs.com>
BuildArch:      noarch
Requires:       python3, python3-gobject, python3-dbus, gtk3, gdk-pixbuf2
Requires:       duplicity
# Gtk-3.0's typelib needs xlib-2.0, which Fedora's gtk3 does not pull in
Requires:       gobject-introspection
# commands the app runs, by path since the owning package varies by release
Requires:       /usr/bin/udevadm, /usr/bin/mount, /usr/bin/xdg-open
# rebuilding pruned moments that hold other users' files needs root
Recommends:     /usr/bin/pkexec

%description
dupli.back Backup software for Linux, originally based on 'flyback', which was
based on Apple's 'Time Machine'. Dupli.back is a full featured backup
application built on top of the duplicity command line backup tool. It supports
password encrypted backups and backing up to local and removable disks.

%prep
cp -p %{_sourcedir}/COPYING .

%install
mkdir -p %{buildroot}/usr/share/dupliback/glade
mkdir -p %{buildroot}/usr/share/dupliback/images
mkdir -p %{buildroot}/usr/share/applications
cp -p %{_sourcedir}/src/*.py %{buildroot}/usr/share/dupliback/
cp -p %{_sourcedir}/src/glade/*.glade %{buildroot}/usr/share/dupliback/glade/
cp -p %{_sourcedir}/src/images/* %{buildroot}/usr/share/dupliback/images/
cp -p %{_sourcedir}/dupliback.desktop %{buildroot}/usr/share/applications/

%files
%license COPYING
%attr(0755, root, root) /usr/share/dupliback/dupliback.py
/usr/share/dupliback
/usr/share/applications/dupliback.desktop
