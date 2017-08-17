Name:     q3c94
Version:	1.5.0
Release:	1%{?dist}
Summary:	pg_sphere for postgresql94-server
License:	LGPL
URL: https://github.com/cvalenzu/dachs-port
Group: Applications
BuildRoot: %{_topdir}/BUILDROOT/%{name}-%{version}
Source0:	%{name}-%{version}.tar.gz
BuildRequires: postgresql94-server postgresql94-devel
Requires: postgresql94-server

%description
Q3C PostgreSQL 9.4 extension for spatial indexing on a sphere

%prep
%setup -q

%build
make PG_CONFIG=/usr/pgsql-9.4/bin/pg_config
make PG_CONFIG=/usr/pgsql-9.4/bin/pg_config install

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/usr/pgsql-9.4/lib
mkdir -p %{buildroot}/usr/pgsql-9.4/share/extension
mkdir -p %{buildroot}/usr/pgsql-9.4/share/extension
mkdir -p %{buildroot}/usr/pgsql-9.4/doc/extension
cp /usr/pgsql-9.4/lib/q3c.so %{buildroot}/usr/pgsql-9.4/lib/q3c.so
cp /usr/pgsql-9.4/share/extension/q3c.control  %{buildroot}/usr/pgsql-9.4/share/extension/q3c.control
cp /usr/pgsql-9.4/share/extension/q3c--1.5.0.sql %{buildroot}/usr/pgsql-9.4/share/extension/q3c--1.5.0.sql
cp /usr/pgsql-9.4/doc/extension/README.md  %{buildroot}/usr/pgsql-9.4/doc/extension/README.md

%clean

%post

%files
/usr/pgsql-9.4/lib/q3c.so
/usr/pgsql-9.4/share/extension/q3c.control
/usr/pgsql-9.4/share/extension/q3c--1.5.0.sql
/usr/pgsql-9.4/doc/extension/README.md
