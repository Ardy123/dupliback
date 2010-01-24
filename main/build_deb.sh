set -x
VERSION="`python src/settings.py`"
VERSION="${VERSION}_r`svnversion .`"
echo $VERSION
rm  debs/*
# make necessary directories
mkdir debian
mkdir debian/DEBIAN
mkdir debian/usr/
mkdir debian/usr/share
mkdir debian/usr/share/dupliback
mkdir debian/usr/share/dupliback/glade
mkdir debian/usr/share/applications
# copy files over
cp src/*.pyc debian/usr/share/dupliback
cp src/flyback.py debian/usr/share/dupliback
cp src/glade/*.glade debian/usr/share/dupliback/glade/
cp packaging/control debian/DEBIAN
cp packaging/dupliback.desktop debian/usr/share/applications/
# build package
dpkg-deb --build debian
mv debian.deb debs/dupli.back-$VERSION.deb

