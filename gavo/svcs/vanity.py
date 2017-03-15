"""
Parsing and maintaining URL shortcuts.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

import os

from gavo import base
from gavo import utils


class VanityLineError(base.Error):
	"""parse error in vanity file.
	"""
	def __init__(self, msg, lineNo, src):
		base.Error.__init__(msg)
		self.msg, self.lineNo, self.src = msg, lineNo, src

	def __str__(self):
		return "Mapping file %s, line %d: %s"%(
			repr(self.src), self.msg, self.lineNo)


BUILTIN_VANITY = """
	__system__/products/p/get getproduct
	__system__/products/p/dlasync datalinkuws
	__system__/services/registry/pubreg.xml oai.xml
	__system__/services/overview/external odoc
	__system__/dc_tables/show/tablenote tablenote
	__system__/dc_tables/show/tableinfo tableinfo
	__system__/services/overview/admin seffe
	__system__/services/overview/rdinfo browse
	__system__/tap/run/tap tap
	__system__/adql/query/form adql !redirect
"""


class _VanityMap(object):
	"""a map of short resource paths to longer resource paths.

	This is only used as singleton through getVanityMap.
	
	There are two mappings: shortToLong, going from vanityName to 
	(fullPath,flags), and longToShort, mapping fullPath -> vanityName.

	flags, in both cases, is a frozenset of flags.  The only one defined
	at this point is "!redirect".
	"""
	knownVanityOptions = set(["!redirect"])

	def __init__(self):
		self.shortToLong = {}
		self.longToShort = {}
	
	def _parseVanityLines(self, src):
		lineNo = 0
		for ln in src:
			lineNo += 1
			ln = ln.strip()
			if not ln or ln.startswith("#"):
				continue

			parts = ln.split()
			if not 1<len(parts)<4:
				raise VanityLineError("Wrong number of words in '%s'"%ln, lineNo, src)

			options = []
			if len(parts)>2:
				options.append(parts.pop())
				if options[-1] not in self.knownVanityOptions:
					raise VanityLineError("Bad option '%s'"%options[-1], lineNo, src)
			dest, src = parts
			yield src, dest, frozenset(options)

	def _buildDicts(self, triples):
		"""builds the child mappings from triples as yielded by _parseVanityLines.
		"""
		for short, long, flags in triples:
			self.shortToLong[short] = (long, flags)
			self.longToShort[long] = short
	
	def addFromString(self, s):
		"""adds vanity mappings from a string literal.
		"""
		self._buildDicts(
			self._parseVanityLines(s.split("\n")))
	
	def addFromFile(self, f):
		"""adds vanity mappings from an open file.
		"""
		self._buildDicts(
			self._parseVanityLines(f))


def _loadVanityMap():
	"""helps getVanityMap.
	"""
	vm = _VanityMap()
	vm.addFromString(BUILTIN_VANITY)

	fSrc = os.path.join(base.getConfig("configDir"), "vanitynames.txt")
	if os.path.exists(fSrc):
		with open(fSrc) as f:
			vm.addFromFile(f)

	return vm


def getVanityMap():
	"""returns "the" vanity map on this data center.

	It consists of built-in vanity (without which things like product
	delivery would actually break) and things read from etc/vanitynames.txt.

	The input file format is documented in the DaCHS tutorial (The Vanity Map).
	"""
	try:
		anchorRD = base.resolveCrossId("//services")
	except AttributeError:
		# We're somewhere where we don't already have rscdesc loaded.
		# Let's assume that means the VanityMap will not need to be reloaded
		# during the runtime, and it's ok if we anchor on the funcition.
		anchorRD = getVanityMap

	return utils.memoizeOn(
		anchorRD,
		_VanityMap,
		_loadVanityMap)
