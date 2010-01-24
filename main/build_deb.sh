set -x
VERSION="`python src/settings.py`"
VERSION="${VERSION}_r`svnversion .`"
echo $VERSION
rm  debs/*
cp  src/*.pyc debian/usr/share/dupliback
cp  src/flyback.py debian/usr/share/dupliback
dpkg-deb --build debian
mv debian.deb debs/dupli.back-$VERSION.deb

