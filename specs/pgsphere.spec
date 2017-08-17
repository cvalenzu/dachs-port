Name:     pg_sphere94
Version:	1.1.5
Release:	1%{?dist}
Summary:	pg_sphere for postgresql94-server
License:	LGPL
URL: https://github.com/cvalenzu/dachs-port
Group: Applications
BuildRoot: %{_topdir}/BUILDROOT/%{name}-%{version}
Source0:	%{name}-%{version}.tar.gz
BuildRequires: postgresql94 postgresql94-devel
Requires: postgresql94

%description
Postgresql GIS implementation for Postgresql 9.4

%prep
%setup -q

%build
make USE_PGXS=1 PG_CONFIG=/usr/pgsql-9.4/bin/pg_config
make USE_PGXS=1 PG_CONFIG=/usr/pgsql-9.4/bin/pg_config install

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/usr/pgsql-9.4/lib
mkdir -p %{buildroot}/usr/pgsql-9.4/share/extension
mkdir -p %{buildroot}/usr/pgsql-9.4/share/extension
mkdir -p %{buildroot}/usr/pgsql-9.4/doc/extension
cp /usr/pgsql-9.4/lib/pg_sphere.so %{buildroot}/usr/pgsql-9.4/lib/pg_sphere.so
cp /usr/pgsql-9.4/share/extension/pg_sphere.control  %{buildroot}/usr/pgsql-9.4/share/extension/pg_sphere.control
cp /usr/pgsql-9.4/share/extension/pg_sphere--1.0.sql %{buildroot}/usr/pgsql-9.4/share/extension/pg_sphere--1.0.sql
cp /usr/pgsql-9.4/doc/extension/README.pg_sphere  %{buildroot}/usr/pgsql-9.4/doc/extension/README.pg_sphere
cp /usr/pgsql-9.4/doc/extension/COPYRIGHT.pg_sphere  %{buildroot}/usr/pgsql-9.4/doc/extension/COPYRIGHT.pg_sphere

%clean

%post

%files
/usr/pgsql-9.4/lib/pg_sphere.so
/usr/pgsql-9.4/share/extension/pg_sphere.control
/usr/pgsql-9.4/share/extension/pg_sphere--1.0.sql
/usr/pgsql-9.4/doc/extension/README.pg_sphere
/usr/pgsql-9.4/doc/extension/COPYRIGHT.pg_sphere
