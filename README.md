# GAVO Dachs Centos 7 Port
[GAVO's Data Center Helper Suite](http://soft.g-vo.org/dachs) port for Centos 7, creating RPM for latest DACHS version, [pg_sphere](https://github.com/akorotkov/pgsphere) and [Q3C](https://github.com/segasai/q3c)

# To Build RPMS
Required Packages
* Postgresql94
* Postgresql94-devel

To install dependencies in Centos 7

```bash
#Installing postgresql
rpm -ivh http://download.postgresql.org/pub/repos/yum/9.4/redhat/rhel-7-x86_64/pgdg-centos94-9.4-3.noarch.rpm
yum install postgresql94 postgresql94-devel -y
/usr/pgsql-9.4/bin/postgresql94-setup initdb
systemctl enable postgresql-9.4.service
systemctl start postgresql-9.4.service
```

After installing required packages build the RPM

```bash
cd specs
make
cd RPMS
```
