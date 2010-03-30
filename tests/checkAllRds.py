"""
Import all localizable RDs to make sure they still parse.

Since walking the inputs dir may be time consuming, I cache the found
rds in a hare-brained scheme by writing them into the program source.

Call the program with an argument to make it refresh that cache.
"""

import re
import sys
import warnings

warnings.simplefilter("ignore", category=UserWarning)

from gavo import base
from gavo import api
from gavo import registry

cachedIDs = [u'liverpool/res/rawframes', u'taptest/q', u'lightmeter/q', u'danish/red', u'obscode/q', u'potsdam/q', u'registryrss/q', u'lensdemo/view', u'mcextinct/q', u'2mass/res/2mass', u'ppmxl/q', u'apfs/times', u'apfs/res/apfs_new', u'dexter/ui', u'ucac3/q', u'ucds/ui', u'ppmx/res/ppmx', u'usnob/res/usnob', u'usnob/res/plates', u'usnob/res/redux', u'poslenscands/cands', u'mpc/q', u'brownDwarfs/bd', u'cars/q', u'rave/q', u'__tests/adqlvalidation/val', u'dmubin/q', u'hipparcos/q', u'logs/logs', u'ohmaser/q', u'fk6/res/fk6', u'rauchspectra/theospectra', u'cns/res/cns', u'cross/q', u'inflight/res/lc1', u'roughtest/q', u'apo/res/apo', u'genupload/do', u'maidanak/res/rawframes', u'veronqsos/q', u'lswscans/res/positions', '__system__/adql', '__system__/procs', '__system__/scs', '__system__/siap', '__system__/tests', '__system__/users', '__system__/dc_tables', '__system__/products', '__system__/services', '__system__/uws', '__system__/tap']

def patchMySource(newIDs):
	f = open("checkAllRds.py")
	src = f.read()
	f.close()
	src = re.sub(r"\ncachedIDs = \[.*", r"\ncachedIDs = %s"%repr(newIDs),
		src)
	f = open("checkAllRds.py", "w")
	f.write(src)
	f.close()

builtinIDs = ["__system__/adql", "__system__/procs",
	"__system__/scs", "__system__/siap", "__system__/tests",
	"__system__/users", "__system__/dc_tables", "__system__/products",
	"__system__/services", "__system__/uws", "__system__/tap"]

base.setDBProfile("trustedquery")
if len(sys.argv)>1:
	newIDs = []
	for rdPath in registry.findAllRDs():
		newIDs.append(api.getRD(rdPath).sourceId)
	patchMySource(newIDs+builtinIDs)
else:
	for id in cachedIDs:
		print "%s,"%id,
		sys.stdout.flush()
		api.getRD(id)
