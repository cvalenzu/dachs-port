pg_version=1.1.5
q3c_version=1.5.0

all: clean prepare build_q3c build_pgsphere

prepare:
	mkdir SOURCES
	mkdir BUILD
	mkdir BUILDROOT
	mkdir RPMS
	mkdir SRPMS

build_pgsphere:
	echo "Building PG-SPHERE RPM"
	cp -r pgsphere pg_sphere94-${pg_version}
	tar -zcf SOURCES/pg_sphere94-${pg_version}.tar.gz pg_sphere94-${pg_version}
	rm -rf pg_sphere94-${pg_version}
	rpmbuild -ba pgsphere.spec --define "_topdir ${PWD}"

build_q3c:
	echo "Building Q3C RPM"
	cp -r q3c q3c94-${q3c_version}
	tar -zcf SOURCES/q3c94-${q3c_version}.tar.gz q3c94-${q3c_version}
	rm -rf q3c94-${q3c_version}
	rpmbuild -ba q3c.spec --define "_topdir ${PWD}"


clean:
	rm -rf SOURCES
	rm -rf BUILD
	rm -rf BUILDROOT
	rm -rf RPMS
	rm -rf SRPMS
