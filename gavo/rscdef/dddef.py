"""
Definition of data.

Data descriptors describe what to do with data. They contain 
a grammar, information on where to obtain source data from, and "makes",
a specification of the tables to be generated and how they are made
from the grammar output.
"""

import datetime
import fnmatch
import glob
import os

from gavo import base
from gavo import utils
from gavo.rscdef import builtingrammars
from gavo.rscdef import common
from gavo.rscdef import rmkdef
from gavo.rscdef import scripting
from gavo.rscdef import tabledef


class IgnoreSpec(base.Structure):
	"""A specification of sources to ignore.

	Sources mentioned here are compared against the inputsDir-relative path
	of sources generated by sources (cf. `Element sources`_).  If there is
	a match, the corresponding source will not be processed.

	You can get ignored files from various sources.  If you give more
	than one source, the set of ignored files is the union of the the 
	individual sets.
	"""
	name_ = "ignoreSources"

	_fromdb = base.UnicodeAttribute("fromdb", default=None,
		description="A DB query to obtain a set of sources to ignore; the"
			" select clause must select exactly one column containing the"
			" source key.")
	_fromfile = common.ResdirRelativeAttribute("fromfile", default=None,
		description="A name of a file containing blacklisted source"
			" paths, one per line.  Empty lines and lines beginning with a hash"
			" are ignored.")
	_patterns = base.ListOfAtomsAttribute("patterns", description=
		"Shell patterns to ignore.  Slashes are treated like any other"
		" character, i.e., patterns do not know about paths.",
		itemAttD=base.UnicodeAttribute("pattern", description="Shell pattern"
			" for source file(s), relative to resource directory."),
		copyable=True)
	_rd = common.RDAttribute()

	def prepare(self, connection=None):
		"""sets attributes to speed up isIgnored()
		"""
		self.inputsDir = base.getConfig("inputsDir")
		self.ignoredSet = set()
		if self.fromdb:
			try:
				self.ignoredSet |= set(r[0] 
					for r in base.SimpleQuerier(connection=connection
						).query(self.fromdb))
			except base.DBError: # table probably doesn't exist yet.
				if base.DEBUG:
					base.ui.logError()
		if self.fromfile:
			for ln in open(self.fromfile):
				ln = ln.strip()
				if ln and not ln.startswith("#"):
					self.ignoredSet.add(ln)

	def isIgnored(self, path):
		"""returns true if path, made inputsdir-relative, should be ignored.
		"""
		try:
			path = utils.getRelativePath(path, self.inputsDir)
		except ValueError: # not in inputs, use full path.
			pass
		if path in self.ignoredSet:
			return True
		for pat in self.patterns:
			if fnmatch.fnmatch(path, pat):
				return True
		return False


class SourceSpec(base.Structure):
	"""A Specification of a data descriptor's inputs.
	"""
	name_ = "sources"

	_patterns = base.ListOfAtomsAttribute("patterns", description=
		"Paths to the source files.  You can use shell patterns here.",
		itemAttD=base.UnicodeAttribute("pattern", description="Shell pattern"
			" for source file(s), relative to resource directory."),
		copyable=True)
	_items = base.ListOfAtomsAttribute("items", description=
		"String literals to pass to grammars.  In contrast to patterns,"
		" they are not interpreted as file names but passed to the"
		" grammar verbatim.  Normal grammars do not like this. It is"
		" mainly intended for use with custom or null grammars.",
		itemAttD=base.UnicodeAttribute("item", 
			description="Grammar-specific string"), copyable=True)
	_recurse = base.BooleanAttribute("recurse", default=False,
		description="Search for pattern(s) recursively in their directory"
			" part(s)?", copyable=True)
	_ignore = base.StructAttribute("ignoredSources", childFactory=
		IgnoreSpec, description="Specification of sources that should not"
			" be processed although they match patterns.  Typically used"
			" in update-type data descriptors.", copyable=True)
	_file = base.DataContent(copyable=True, description="A single"
		" file name (this is for convenience)")

	def __iter__(self):
		return self.iterSources()

	def completeElement(self, ctx):
		if self.ignoredSources is base.Undefined:
			self.ignoredSources = base.makeStruct(IgnoreSpec)
		self._completeElementNext(SourceSpec, ctx)

	def _expandDirParts(self, dirParts, ignoreDotDirs=True):
		"""expands a list of directories into a list of them and all their
		descendants.

		It follows symbolic links but doesn't do any bookkeeping, so bad
		things will happen if the directory graph contains cycles.
		"""
		res = []
		for root in dirParts:
			for root, dirs, files in os.walk(root):
				if ignoreDotDirs:
					if os.path.basename(root).startswith("."):
						continue
					dirs = [dir for dir in dirs if not dir.startswith(".")]
				dirs = (os.path.join(root, dir) for dir in dirs)
				res.extend(dir for dir in dirs if os.path.isdir(dir))
				for child in files:
					if os.path.islink(os.path.join(root, child)):
						res.expand(self._expandDirParts(os.path.join(root, child)))
		return res

	def iterSources(self, connection=None):
		self.ignoredSources.prepare(connection)
		for item in self.items:
			if not self.ignoredSources.isIgnored(item):
				yield item

		baseDir = ""
		if self.parent.rd:
			baseDir = self.parent.rd.resdir

		for pattern in self.patterns:
			dirPart, baseName = os.path.split(pattern)
			if self.parent.rd:
				dirParts = [os.path.join(baseDir, dirPart)]
			else:
				dirParts = [dirPart]
			if self.recurse:
				dirParts = dirParts+self._expandDirParts(dirParts)
			for dir in dirParts:
				for name in glob.glob(os.path.join(dir, baseName)):
					fullName = os.path.abspath(name)
					if not self.ignoredSources.isIgnored(fullName):
						yield fullName
		if self.content_:
			yield os.path.abspath(os.path.join(baseDir, self.content_))
	
	def __nonzero__(self):
		return (not not self.patterns) or (not not self.items
			) or (not not self.content_)


class Make(base.Structure, scripting.ScriptingMixin):
	"""A build recipe for tables belonging to a data descriptor.

	All makes belonging to a DD will be processed in the order in which they
	appear in the file.
	"""
	name_ = "make"

	_table = base.ReferenceAttribute("table", 
		description="Reference to the table to be embedded",
		default=base.Undefined, 
		copyable=True,
		forceType=tabledef.TableDef)

	_rowmaker = base.ReferenceAttribute("rowmaker", 
		default=base.NotGiven,
		forceType=rmkdef.RowmakerDef,
		description="The rowmaker (i.e., mapping rules from grammar keys to"
		" table columns) for the table being made.", 
		copyable=True)

	_parmaker = base.ReferenceAttribute("parmaker", 
		default=base.NotGiven,
		forceType=rmkdef.ParmakerDef,
		description="The parmaker (i.e., mapping rules from grammar parameters"
		" to table parameters) for the table being made.  You will usually"
		" not give a parmaker.",
		copyable=True)

	_role = base.UnicodeAttribute("role", 
		default=None,
		description="The role of the embedded table within the data set",
		copyable=True)
	
	_rowSource = base.EnumeratedUnicodeAttribute("rowSource",
		default="rows",
		validValues=["rows", "parameters"],
		description="Source for the raw rows processed by this rowmaker.",
		copyable=True,
		strip=True)

	def __repr__(self):
		return "Make(table=%r, rowmaker=%r)"%(
			self.table and self.table.id, self.rowmaker and self.rowmaker.id)

	def onParentComplete(self):
		if self.rowmaker is base.NotGiven:
			if (self.parent and self.parent.grammar and 
					self.parent.grammar.yieldsTyped):
				self.rowmaker = rmkdef.RowmakerDef.makeTransparentFromTable(self.table)
			else:
				self.rowmaker = rmkdef.RowmakerDef.makeIdentityFromTable(self.table)

	def getExpander(self):
		"""used by the scripts of expanding their source.

		We always return the expander of the table being made.
		"""
		return self.table.getExpander()
	
	def create(self, connection, parseOptions, tableFactory):
		"""returns a new empty instance of the table this is making.
		"""
		newTable = tableFactory(self.table,
			parseOptions=parseOptions, connection=connection, role=self.role)
		newTable._runScripts = self.getRunner()
		return newTable
	
	def runParmakerFor(self, grammarParameters, destTable):
		"""feeds grammarParameter to destTable.
		"""
		if self.parmaker is base.NotGiven:
			return
		parmakerFunc = self.parmaker.compileForTableDef(destTable.tableDef)
		destTable.setParams(parmakerFunc(grammarParameters, destTable),
			raiseOnBadKeys=False)


class Registration(base.Structure):
	"""A request for registration of a data collection.

	This is much like publish for services, but there's only one of
	those per data, and thus there's no register-local metadata.
	Data registrations may refer to published services that make their
	data available.
	"""
	name_ = "register"

	_defaultSets = frozenset(["ivo_managed"])

	_sets = base.StringSetAttribute("sets",
		description="A comma-separated list of sets this data will be"
			" published in.  To publish data to the VO registry, just"
			" say ivo_managed here.  Other sets probably don't make much"
			" sense right now.  ivo_managed also is the default.")

	_servedThrough = base.ReferenceListAttribute("services",
		description="A DC-internal reference to a service that lets users"
			" query that within the data collection.")

	def completeElement(self, ctx):
		self._completeElementNext(Registration, ctx)
		if not self.sets:
			self.sets = self._defaultSets

	def register(self):
		"""adds servedBy and serviceFrom metadata to data, service pairs
		in this registration.
		"""
		for srv in self.services:
			srv.declareServes(self.parent)


class IVOMetaMixin(object):
	"""A mixin for resources aspiring to have IVO ids.

	All those need to have an RDAttribute.  Also, for some data this accesses
	the servicelist database, so it should really be in registry, where
	that stuff is defined.  Ah well.
	"""
	def _meta_referenceURL(self):
		return base.makeMetaItem(self.getURL("info"),
			type="link", title="Service info")

	def _meta_identifier(self):
		if "identifier" in self.meta_:
			return self.meta_["identifier"]
		return "ivo://%s/%s/%s"%(base.getConfig("ivoa", "authority"),
				self.rd.sourceId, self.id)

	def __getFromDB(self, metaKey):
		try:  # try to used cached data
			if self.__dbRecord is None:
				raise base.NoMetaKey(metaKey, carrier=self)
			return self.__dbRecord[metaKey]
		except AttributeError:
			# fetch data from DB
			pass
		# We're not going through servicelist since we don't want to depend
		# on the registry subpackage.
		curs = base.caches.getTableConn(None).cursor()
		curs.execute("SELECT dateUpdated, recTimestamp, setName"
			" FROM dc.resources_join WHERE sourceRD=%(rdId)s AND resId=%(id)s",
			{"rdId": self.rd.sourceId, "id": self.id})
		res = list(curs)
		if res:
			row = res[0]
			self.__dbRecord = {
				"sets": base.makeMetaItem(list(set(row[2] for row in res)), 
					name="sets"),
				"recTimestamp": base.makeMetaItem(res[0][1].strftime(
					utils.isoTimestampFmt), name="recTimestamp"),
			}
		else:
			self.__dbRecord = {
				'sets': ['unpublished'],
				'recTimestamp': base.makeMetaItem(
					datetime.datetime.utcnow().strftime(
					utils.isoTimestampFmt), name="recTimestamp"),
				}
		return self.__getFromDB(metaKey)
	
	def _meta_dateUpdated(self):
		return self.rd.getMeta("dateUpdated")

	def _meta_datetimeUpdated(self):
		return self.rd.getMeta("datetimeUpdated")
	
	def _meta_recTimestamp(self):
		return self.__getFromDB("recTimestamp")

	def _meta_sets(self):
		return self.__getFromDB("sets")

	def _meta_status(self):
		return "active"


class DataDescriptor(base.Structure, base.ComputedMetaMixin,
		IVOMetaMixin):
	"""A description of how to process data from a given set of sources.

	Data descriptors bring together a grammar, a source specification and
	"makes", each giving a table and a rowmaker to feed the table from the
	grammar output.

	They are the "executable" parts of a resource descriptor.  Their ids
	are used as arguments to gavoimp for partial imports.
	"""
	name_ = "data"

	resType = "data"

	_rowmakers = base.StructListAttribute("rowmakers",
		childFactory=rmkdef.RowmakerDef, 
		description="Embedded build rules (usually rowmakers are defined toplevel)",
		copyable=True)

	_tables = base.StructListAttribute("tables",
		childFactory=tabledef.TableDef, 
		description="Embedded table definitions (usually, tables are defined"
			" toplevel)", 
		copyable=True)

	_grammar = base.MultiStructAttribute("grammar", 
		default=None,
		childFactory=builtingrammars.getGrammar,
		childNames=builtingrammars.GRAMMAR_REGISTRY.keys(),
		description="Grammar used to parse this data set.", 
		copyable=True)
	
	_sources = base.StructAttribute("sources", 
		default=None, 
		childFactory=SourceSpec,
		description="Specification of sources that should be fed to the grammar.",
		copyable=True)

	_dependents = base.ListOfAtomsAttribute("dependents",
		itemAttD=base.UnicodeAttribute("recreateAfter"),
		description="List of data IDs to recreate when this resource is"
			" remade; use # syntax to reference in other RDs.")

	_auto = base.BooleanAttribute("auto", 
		default=True, 
		description="Import this data set if not explicitly"
			" mentioned on the command line?")

	_updating = base.BooleanAttribute("updating", 
		default=False,
		description="Keep existing tables on import?  You usually want this"
			" False unless you have some kind of sources management,"
			" e.g., via a sources ignore specification.", 
		copyable=True)

	_makes = base.StructListAttribute("makes", 
		childFactory=Make,
		copyable=True, 
		description="Specification of a target table and the rowmaker"
			" to feed them.")

	_registration = base.StructAttribute("registration",
		default=None,
		childFactory=Registration,
		copyable=False,
		description="A registration (to the VO registry) of this data collection.")

	_properties = base.PropertyAttribute()

	_rd = common.RDAttribute()

	_original = base.OriginalAttribute()

	metaModel = ("title(1), creationDate(1), description(1),"
		"subject, referenceURL(1)")

	def validate(self):
		self._validateNext(DataDescriptor)
		if self.registration and self.id is None:
			raise base.StructureError("Published data needs an assigned id.")

	def onElementComplete(self):
		self._onElementCompleteNext(DataDescriptor)
		for t in self.tables:
			t.setMetaParent(self)
		if self.registration:
			self.registration.register()

	# since we want DDs to be dynamically created, they must find their
	# meta parent (RD) themselves.  We do this while the DD is being adopted.
	def _getParent(self):
		return self.__parent
	
	def _setParent(self, value):
		self.__parent = value
		if value is not None:
			self.setMetaParent(value)
	
	parent = property(_getParent, _setParent)

	def iterSources(self, connection=None):
		if self.sources:
			return self.sources.iterSources(connection)
		else:
			return iter([])

	def __iter__(self):
		for m in self.makes:
			yield m.table

	def getTableDefById(self, id):
		for m in self.makes:
			if m.table.id==id:
				return m.table
		raise base.StructureError("No table name %s will be built"%id)

	def getTableDefWithRole(self, role):
		for m in self.makes:
			if m.role==role:
				return m.table
		raise base.StructureError("No table def with role '%s'"%role)

	def getPrimary(self):
		"""returns the "primary" table definition in the data descriptor.

		"primary" means the only table in a one-table dd, the table with the
		role "primary" if there are more.  If no matching table is found, a
		StructureError is raised.
		"""
		if len(self.makes)==1:
			return self.makes[0].table
		else:
			try:
				return self.getTableDefWithRole("primary")
			except base.StructureError: # raise more telling message
				pass
		raise base.StructureError("Ambiguous request for primary table")

	def copyShallowly(self):
		"""returns a shallow copy of self.

		Sources are not copied.
		"""
		return DataDescriptor(self.parent, rowmakers=self.rowmakers[:],
			tables=self.tables[:], grammar=self.grammar, makes=self.makes[:])
	
	def getURL(self, rendName, absolute=True):
		basePath = "%s%s/rdinfo"%(base.getConfig("web", "nevowRoot"),
			self.rd.sourceId)
		if absolute:
			basePath = base.getConfig("web", "serverURL")+basePath
		return basePath

