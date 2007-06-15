import sys
import ez_setup
ez_setup.use_setuptools()

from setuptools import setup, find_packages

install_requires = ["pyfits", "pyPgSQL", "VOTable", "numarray", "elementtree"],
if "develop" in sys.argv:
	# No stinkin' wrapper scripts, please
	install_requires = []

setup(name="gavo",
	description="ZAH Gavo support modules",
	url="http://www.g-vo.org",
	license="GPL",
	author="Markus Demleitner",
	author_email="msdemlei@ari.uni-heidelberg.de",
	packages=find_packages(),
	py_modules=["ez_setup"],
	install_requires=install_requires,
	dependency_links=["http://ara.ari.uni-heidelberg.de/soft/python",
		"http://sourceforge.net/project/showfiles.php?group_id=16528",
		"http://sourceforge.net/project/showfiles.php?group_id=1369",
		"http://www.stsci.edu/resources/software_hardware/pyfits/Download"],
	entry_points={
		'console_scripts': [
			'gavoimp = gavo.parsing.commandline:main',
			'gavomkrd = gavo.parsing.bootstrapfits:main',
		]
	},
	version="0.2")
