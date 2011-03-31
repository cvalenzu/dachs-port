"""
Turning values in our tables into strings (e.g., in VOTables or HTML).

A value mapper is a function used for serialization of (python) values
to strings, e.g., for HTML or VOTables.

They are produced by factories that in turn are registered in 
ValueMapperFactoryRegistries.  These can be queried for mappers using
VColDesc instances; these are basically dictionaries giving certain
observable properties of a column (min, max, a sample value), values
from Column, and computed stuff like the VOTable type.

See ValueMapperFactoryRegistry.

The module also defines a defaultMFRegistry.  It should be suitable
for serializing to VOTables and similar data machine-oriented data 
formats.
"""

import datetime
import re
import urllib
import urlparse
import weakref

from gavo import adql
from gavo import stc
from gavo import utils
from gavo.base import typesystems


naN = float("NaN")


class ValueMapperFactoryRegistry(object):
	"""is an object clients can ask for functions fixing up values
	for encoding.

	A mapper factory is just a function that takes a VColDesc instance.
	It must return either None (for "I don't know how to make a function for this
	combination these column properties") or a callable that takes a value
	of the given type and returns a mapped value.

	To add a mapper, call registerFactory.  To find a mapper for a
	set of column properties, call getMapper -- column properties should
	be an instance of VColDesc, but for now a dictionary with the
	right keys should mostly do.

	Mapper factories are tried in the reverse order of registration,
	and the first that returns non-None wins, i.e., you should
	register more general factories first.  If no registred mapper declares
	itself responsible, getMapper returns an identity function.  If
	you want to catch such a situation, you can use somthing like
	res = vmfr.getMapper(...); if res is utils.identity ...
	"""
	def __init__(self, factories=None):
		if factories is None:
			self.factories = []
		else:
			self.factories = factories[:]

	def getFactories(self):
		"""returns the list of factories.

		This is *not* a copy.  It may be manipulated to remove or add
		factories.
		"""
		return self.factories

	def registerFactory(self, factory):
		self.factories.insert(0, factory)

	def getMapper(self, colDesc):
		"""returns a mapper for values with the python value instance, 
		according to colDesc.

		This method may change colDesc.

		We do a linear search here, so you shouldn't call this function too
		frequently.
		"""
		for factory in self.factories:
			mapper = factory(colDesc)
			if mapper:
				colDesc["winningFactory"] = factory
				break
		else:
			mapper = utils.identity
		return mapper


defaultMFRegistry = ValueMapperFactoryRegistry()
_registerDefaultMF = defaultMFRegistry.registerFactory


def _booleanMapperFactory(colDesc):
	if colDesc["dbtype"]=="boolean":
		def coder(val):
			if val:
				return "1"
			else:
				return "0"
		return coder
_registerDefaultMF(_booleanMapperFactory)


def _floatMapperFactory(colDesc):
	if colDesc["dbtype"]=="real" or colDesc["dbtype"].startswith("double"):
		def coder(val):
			if val is None:
				return naN
			return val
		return coder
_registerDefaultMF(_floatMapperFactory)


def datetimeMapperFactory(colDesc):
	import time

	def dtToMJdn(val):
		"""returns the modified julian date number for the dateTime instance val.
		"""
		return stc.dateTimeToJdn(val)-2400000.5

# This is too gruesome.  We want some other way of handling this...
# Simplify this, and kick out all the mess we don't want.
	if (
			(colDesc["sample"] is None and colDesc["dbtype"]=="timestamp")
			or (colDesc.get("xtype")=="adql:TIMESTAMP")
			or isinstance(colDesc["sample"], (datetime.date, datetime.datetime))):
		unit = colDesc["unit"]
		if (
				unit=="Y:M:D" 
				or unit=="Y-M-D" 
				or colDesc.get("xtype")=="adql:TIMESTAMP"):
			fun = lambda val: (val and val.isoformat()) or None
			destType = ("char", "*")
		elif colDesc["ucd"] and "MJD" in colDesc["ucd"]:  # like VOX:Image_MJDateObs
			colDesc["unit"] = "d"
			fun = lambda val: (val and dtToMJdn(val))
			destType = ("double", '1')
		elif unit=="yr" or unit=="a":
			fun = lambda val: (val and stc.dateTimeToJYear(val))
			destType = ("double", '1')
		elif unit=="d":
			fun = lambda val: (val and stc.dateTimeToJdn(val))
			destType = ("double", '1')
		elif unit=="s":
			fun = lambda val: (val and time.mktime(val.timetuple()))
			destType = ("double", '1')
		elif unit=="iso":
			fun = lambda val: (val and val.isoformat())
			destType = ("char", "*")
		else:   # Fishy, but not our fault
			fun = lambda val: (val and stc.dateTimeToJdn(val))
			destType = ("double", '1')
		colDesc["datatype"], colDesc["arraysize"] = destType
		return fun
_registerDefaultMF(datetimeMapperFactory)


_pgTypes = set(["spoint", "spoly", "scircle"])

def _pgSphereMapperFactory(colDesc):
	"""A factory for functions turning pgsphere types to STC-S-like stuff.
	"""
	if not (
			colDesc["dbtype"] in _pgTypes
			or colDesc["xtype"]=="adql:POINT"):
		return
	def mapper(val):
		if val is None:
			return None
		elif isinstance(val, basestring):  # allow preformatted stuff
			return val
		else:
#	XXX TODO: add something on the system to colDesc and use it here
			return val.asSTCS("ICRS")
	colDesc["datatype"], colDesc["arraysize"] = "char", "*"
	return mapper
_registerDefaultMF(_pgSphereMapperFactory)


def _boxMapperFactory(colDesc):
	"""A factory for Boxes.
	"""
	if colDesc["dbtype"]!="box":
		return
	def mapper(val):
		if val is None:
			return ""
		else:
			return "Box ICRS %s %s %s %s"%(val[0]+val[1])
	colDesc["datatype"], colDesc["arraysize"] = "char", "*"
	return mapper
_registerDefaultMF(_boxMapperFactory)


def _castMapperFactory(colDesc):
	"""is a factory that picks up castFunctions set up by user casts.
	"""
	if "castFunction" in colDesc:
		return colDesc["castFunction"]
_registerDefaultMF(_castMapperFactory)


_tagPat = re.compile("<[^>]*>")
def _htmlScrubMapperFactory(colDesc):
	if colDesc["displayHint"].get("type")!="keephtml":
		return
	def coder(data):
		if data:
			return _tagPat.replace("", data)
		return ""
	return coder
_registerDefaultMF(_htmlScrubMapperFactory)


def getMapperRegistry():
	"""returns a copy of the default value mapper registry.
	"""
	return ValueMapperFactoryRegistry(
		defaultMFRegistry.getFactories())


class _CmpType(type):
	"""is a metaclass for *classes* that always compare in one way.
	"""
# Ok, that's just posing.  It's fun anyway.
	def __cmp__(cls, other):
		return cls.cmpRes


class _Comparer(object):
	__metaclass__ = _CmpType
	def __init__(self, *args, **kwargs):
		raise Error("%s classes can't be instanciated."%self.__class__.__name__)


class _Infimum(_Comparer):
	"""is a *class* smaller than anything.

	This will only work as the first operand.

	>>> _Infimum<-2333
	True
	>>> _Infimum<""
	True
	>>> _Infimum<None
	True
	>>> _Infimum<_Infimum
	True
	"""
	cmpRes = -1


class _Supremum(_Comparer):
	"""is a *class* larger than anything.

	This will only work as the first operand.

	>>> _Supremum>1e300
	True
	>>> _Supremum>""
	True
	>>> _Supremum>None
	True
	>>> _Supremum>_Supremum
	True
	"""
	cmpRes = 1



class VColDesc(dict):
	"""A container for properties of columns in a table.

	Specifically, it gives maxima, minima and if null values occur, plus
	things like ADQL types.  These objects are central to the mapping
	of values and VOTable FIELD generation.

	We want separate objects here since some heavy type mapping may take
	place, and we do not want serious surgery on our (ideally immutable)
	Columns.

	One of the main functions of this class is that instances can/should
	be used to query ValueMapperFactoryRegistries for value mappers.

	As a special service to coerce internal tables to external standards,
	you can pass a votCast dictionary to VColDesc.  Give any key/value pairs
	in there to override what VColDesc guesses or infers.  This is used to 
	force the sometimes a bit funky SCS/SIAP types to standard values.

	The castMapperFactory enabled by default checks for the presence of
	a castFunction in a VColDesc.  If it is there, it will be used
	for mapping the values, so this is another thing you can have in votCast.
	
	The SerManager tries to obtain votCasts from a such-named
	attribute on the table passed in.
	"""
	_nullvalueRanges = {
		"char": (' ', '~'),
		"unsignedByte": (0, 255),
		"short": (-2**15, 2**15-1),
		"int": (-2**31, 2**31-1),
		"long": (-2**63, 2**63-1),
	}
	def __init__(self, column, votCast=None):
		self["min"], self["max"] = _Supremum, _Infimum
		# Safe default, overwritten if we have evidence in finish
		self["hasNulls"] = True  
		self.nullSeen = False
		# nullvalue is a string, None if not user-provided.
		self["nullvalue"] = column.values and column.values.nullLiteral 
		self["sample"] = None
		self["name"] = column.key
		self["dbtype"] = column.type
		self["xtype"] = column.xtype
		type, size = typesystems.sqltypeToVOTable(column.type)
		self["datatype"] = type
		self["arraysize"] = size
		self["displayHint"] = column.displayHint
		self["note"] = None # filled in by serManager, if at all
		for fieldName in ["ucd", "utype", "unit", "description"]:
			self[fieldName] = getattr(column, fieldName)
			if not self[fieldName]:
				self[fieldName] = None
		if votCast is not None:
			self.update(votCast)

	def feed(self, val):
		if val is None:
			self.nullSeen = True
		else:
			if self["min"]>val:
				self["min"] = val
			if self["max"]<val:
				self["max"] = val

	def finish(self, samplesAcquired):
		"""has to be called after feeding is done.
		"""
		if samplesAcquired:
			self.computeNullvalue()
			self["hasNulls"] = self.nullSeen

	def computeNullvalue(self):
		"""tries to come up with a null value for integral data.

		This is called by finish(), but you could call it yourself to find out
		if a nullvalue can be computed.
		"""
		if self["nullvalue"] is not None:
			return
		if self["datatype"] not in self._nullvalueRanges:
			return
		if not self.nullSeen:
			return

		if self["min"]>self._nullvalueRanges[self["datatype"]][0]:
			self["nullvalue"] = str(self._nullvalueRanges[self["datatype"]][0])
		elif self["max"]<self._nullvalueRanges[self["datatype"]][1]:
			self["nullvalue"] = str(self._nullvalueRanges[self["datatype"]][1])
		else:
			raise Error("Cannot compute nullvalue for column %s,"
				"range is %s..%s"%(self["name"], self["min"], self["max"]))


class SerManager(utils.IdManagerMixin):
	"""A wrapper for the serialisation of table data.

	SerManager instances keep information on what values certain columns can
	assume and how to map them to concrete values in VOTables, HTML or ASCII.
	
	They are constructed with a BaseTable instance.

	You can additionally give:

		- withRanges -- iterate over the whole table to figure out minima,
			maxima, and the appearance of null values (this is currently required
			for reliable null value determination in VOTables with integers).  Default
			is True.
		- acquireSamples -- look for (non-NULL) samples for all columns.
		  Default is True, and some mappers (in particular, datetime)
		  depend on it.  However, if you intend to stream query results,
		  do not use it.
		- idManager -- an object mixing in utils.IdManagerMixin.  This is important
			if the ids we are assigning here end up in a larger document.  In that
			case, pass in the id manager of that larger document.  Default is the
			SerManager itself
		- mfRegistry -- a map factory registry.  Default is the defaltMFRegistry.
	"""
	# Don't compute min, max, etc for these types
	_noValuesTypes = set(["boolean", "bit", "unicodeChar",
		"floatComplex", "doubleComplex"])
	# Filled out on demand
	_nameDict = None

	def __init__(self, table, withRanges=True, acquireSamples=True,
			idManager=None, mfRegistry=defaultMFRegistry):
		self.table = table
		if idManager is not None:
			self.cloneFrom(idManager)
		self.notes = {}  # notes referenced by our fields

		self._makeColDescs()
		if acquireSamples:
			self._acquireSamples()
			if withRanges:
				self._findRanges()
		for cd in self:
			cd.finish(withRanges)
		self._makeMappers(mfRegistry)
	
	def __iter__(self):
		return iter(self.colDescs)

	def _makeColDescs(self):
		self.colDescs = []
		for column in self.table.tableDef:
			self.colDescs.append(
				VColDesc(column, self.table.votCasts.get(column.name)))
			colId = self.makeIdFor(column, column.key)
			# Do not generate an id if the field is already defined somewhere else.
			# (if that happens, STC definitions could be in trouble, so try
			# to avoid it, all right?)
			if colId is not None:
				self.colDescs[-1]["ID"] = colId
			# if column refers to a note, remember the note
			if column.note:
				try:
					self.notes[column.note.tag] = column.note
					self.colDescs[-1]["note"] = column.note
				except (ValueError, utils.NotFoundError): 
					pass # don't worry about missing notes

	def _findRanges(self):
		"""obtains minima, maxima, and the existence of null values for
		our columns.

		This obviously takes a long time of large tables.
		"""
		colIndex = dict((c["name"], c) for c in self)
		valDesiredCols = [c["name"] for c in self
			if c["datatype"] not in self._noValuesTypes and
				c["arraysize"]=="1" and not "castFunction" in c]
		for row in self.table:
			for key in valDesiredCols:
				colIndex[key].feed(row[key])

	def _acquireSamples(self):
		"""obtains samples for the the various columns.

		To do that, it iterates through the table until it has samples for
		all items.  Thus, this may be slow.
		"""
		colIndex = dict((c["name"], c) for c in self)
		noSampleCols = set(colIndex)
		for row in self.table:
			newSampleCols = set()
			for col in noSampleCols:
				if row[col] is not None:
					newSampleCols.add(col)
					colIndex[col]["sample"] = row[col]
			noSampleCols.difference_update(newSampleCols)
			if not noSampleCols:
				break

	def _makeMappers(self, mfRegistry):
		"""returns a sequence of functions mapping our columns.

		As a side effect, column properties may change (in particular,
		datatypes).
		"""
		self.mappers = tuple(mfRegistry.getMapper(cp) for cp in self)

	def makeMapperFunction(self):
		"""returns a function that returns a dictionary of mapped values
		for a row dictionary.
		"""
		buildNS = dict(("map%d"%index, mapper) 
			for index, mapper in enumerate(self.mappers))
		colLabels = [str(c["name"]) for c in self]

		funDef = ["def buildRec(rowDict):"]
		for index, label in enumerate(colLabels):
			if self.mappers[index] is not utils.identity:
				funDef.append("\trowDict[%r] = map%d(rowDict[%r])"%(
					label, index, label))
		funDef.append("\treturn rowDict")

		exec "\n".join(funDef) in buildNS
		return buildNS["buildRec"]

	def _iterWithMaps(self, buildRec):
		colLabels = [f.name for f in self.table.tableDef]
		if not colLabels:
			yield ()
			return
		for row in self.table:
			yield buildRec(row)

	def getColDescByName(self, name):
		if self._nameDict is None:
			self._nameDict = dict((cd["name"], cd) for cd in self)
		return self._nameDict[name]

	def makeTupleMaker(self):
		"""returns a function that returns a tuple of mapped values
		for a row dictionary.
		"""
		buildNS = dict(("map%d"%index, mapper) 
			for index, mapper in enumerate(self.mappers))

		funDef = ["def buildRec(rowDict):", "\treturn ("]
		for index, cd in enumerate(self):
			if self.mappers[index] is utils.identity:
				funDef.append("\t\trowDict[%r],"%cd["name"])
			else:
				funDef.append("\t\tmap%d(rowDict[%r]),"%(index, cd["name"]))
		funDef.append("\t)")

		exec "\n".join(funDef) in buildNS
		return buildNS["buildRec"]

	def getMappedValues(self):
		"""iterates over the table's rows as dicts with mapped values.
		"""
		return self._iterWithMaps(self.makeMapperFunction())

	def getMappedTuples(self):
		"""iterates over the table's rows as tuples with mapped values.
		"""
		return self._iterWithMaps(self.makeTupleMaker())


def needsQuoting(identifier, forRowmaker=False):
	"""returns True if identifier needs quoting in an SQL statement.
	>>> needsQuoting("RA(J2000)")
	True
	>>> needsQuoting("ABS")
	True
	>>> needsQuoting("r")
	False
	"""
	if utils.identifierPattern.match(identifier) is None:
		return True
	if identifier.lower() in getNameBlacklist(forRowmaker):
		return True
	return False


@utils.memoized
def getNameBlacklist(forRowmaker=False):
	"""returns a set of names not suitable for table column names.

	This comprises SQL reserved words in lower case and, if forRowmaker
	is true, also some names damaging row makers (e.g. python reserved
	words).
	"""
	res = set(k.lower() for k in adql.allReservedWords)
	if forRowmaker:
		import keyword
		from gavo.rscdef import rmkfuncs
		res = (res 
			| set(["result_", "rowdict_"])
			| set(k.lower() for k in keyword.kwlist)
			| set(k.lower() for k in dir(rmkfuncs)))
	return frozenset(res)


class VOTNameMaker(object):
	"""A class for generating db-unique names from VOTable fields.

	This is important to avoid all kinds of weird names the remaining
	infrastructure will not handle.  "Normal" TableDefs assume unquoted
	SQL identifiers as names, and want all names unique.

	Using this class ensures these expectations are met in a reproducible
	way (i.e., given the same table, the same names will be assigned).
	"""
	def __init__(self):
		self.knownNames, self.index = set(getNameBlacklist(True)), 0

	def makeName(self, field):
		preName = re.sub("[^\w]+", "x", (getattr(field, "name", None) 
			or getattr(field, "ID", None)
			or "field%02d"%self.index))
		if not re.match("[A-Za-z_]", preName):
			preName = "col_"+preName
		while preName.lower() in self.knownNames:
			preName = preName+"_"
		self.knownNames.add(preName.lower())
		self.index += 1
		return preName


def _test():
	import doctest, valuemappers
	doctest.testmod(valuemappers)


if __name__=="__main__":
	_test()

