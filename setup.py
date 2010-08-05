import os
import sys

#import ez_setup
#ez_setup.use_setuptools()

from setuptools import setup, find_packages, Extension

install_requires = []
# Theoretically, we could define dependencies here, more or less like this:
# install_requires = ["pyfits", "numpy", "pyparsing", "psycopg2"]
# -- but we don't, since in practice it seems it's more trouble than it's
# worth.

setup(name="gavodachs",
	description="ZAH GAVO data center complete package",
	url="http://www.g-vo.org",
	license="GPL",
	author="Markus Demleitner",
	author_email="gavo@ari.uni-heidelberg.de",
	packages=find_packages(),
	py_modules=["ez_setup"],
	# Really, I think we should be zip_safe, but there's a weird output requriring investigation
	zip_safe=False,
	include_package_data = True,
	install_requires=install_requires,
	entry_points={
		'console_scripts': [
			'gavo = gavo.user.cli:main',
		]
	},
	version="0.5")
