"""
Definition of data.

Data descriptors describe what to do with data. They contain 
a grammar, information on where to obtain source data from, and "makes",
a specification of the tables to be generated and how they are made
from the grammar output.
"""

import fnmatch
import glob
import os

from gavo import base
from gavo import utils
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
				pass
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

	def __iter__(self):
		return self.iterSources()

	def completeElement(self):
		if self.ignoredSources is base.Undefined:
			self.ignoredSources = base.makeStruct(IgnoreSpec)
		self._completeElementNext(SourceSpec)

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
		for pattern in self.patterns:
			dirPart, baseName = os.path.split(pattern)
			if self.parent.rd:
				dirParts = [os.path.join(self.parent.rd.resdir, dirPart)]
			else:
				dirParts = [dirPart]
			if self.recurse:
				dirParts = dirParts+self._expandDirParts(dirParts)
			for dir in dirParts:
				for name in glob.glob(os.path.join(dir, baseName)):
					fullName = os.path.abspath(name)
					if not self.ignoredSources.isIgnored(fullName):
						yield fullName
	
	def __nonzero__(self):
		return (not not self.patterns) or (not not self.items)


class GrammarAttribute(base.StructAttribute):
	"""is an attribute containing some kind of grammar.

	This is a bit funky in that it's polymorphous.  We look up the
	class that's actually going to be created in the parent's class
	registry.

	This really only works on DataDescriptors.
	"""
	def __init__(self, name, description, **kwargs):
		base.AttributeDef.__init__(self, name, 
			default=None, description=description, **kwargs)

	def create(self, structure, ctx, name):
		return getGrammar(name)(structure)

	def makeUserDoc(self):
		return ("Polymorphous grammar attribute.  May contain any of the grammars"
			" mentioned in `Grammars available`_.")


class Make(base.Structure, scripting.ScriptingMixin):
	"""A build recipe for tables belonging to a data descriptor.

	All makes belonging to a DD will be processed in the order in which they
	appear in the file.
	"""
# Allow embedding maps, idmaps, defaults for auto-rowmaker?
	name_ = "make"

	_table = base.ReferenceAttribute("table", 
		description="Reference to the table to be embedded",
		default=base.Undefined, copyable=True)
	_rowmaker = base.ReferenceAttribute("rowmaker", forceType=rmkdef.RowmakerDef,
		description="Rowmaker for this table", default=base.NotGiven,
		copyable=True)
	_role = base.UnicodeAttribute("role", default=None,
		description="The role of the embedded table within the data set",
		copyable=True)

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
	
	def enableScripts(self, table):
		"""enables script running for table.
		"""
		table._runScripts = self.getRunner()


class DataDescriptor(base.Structure, base.MetaMixin):
	"""A description of how to process data from a given set of sources.

	Data descriptors bring together a grammar, a source specification and
	"makes", each giving a table and a rowmaker to feed the table from the
	grammar output.

	They are the "executable" parts of a resource descriptor.  Their ids
	are used as arguments to gavoimp for partial imports.
	"""
	name_ = "data"

	_rowmakers = base.StructListAttribute("rowmakers",
		childFactory=rmkdef.RowmakerDef, 
		description="Embedded build rules (usually rowmakers are defined toplevel)",
		copyable=True)
	_tables = base.StructListAttribute("tables",
		childFactory=tabledef.TableDef, 
		description="Embedded table definitions (usually, tables are defined"
			" toplevel)", copyable=True)
	# polymorphous through getDynamicAttribute
	_grammar = GrammarAttribute("grammar", description="Grammar used"
		" to parse this data set.", copyable=True)
	_sources = base.StructAttribute("sources", default=None, 
		childFactory=SourceSpec,
		description="Specification of sources that should be fed to the grammar.",
		copyable=True)
	_dependents = base.ListOfAtomsAttribute("dependents",
		itemAttD=base.UnicodeAttribute("recreateAfter"),
		description="List of data IDs to recreate when this resource is"
			" remade; use # syntax to reference in other RDs.")
	_auto = base.BooleanAttribute("auto", default=True, description=
		"Import this data set without explicit mention on the command line?")
	_updating = base.BooleanAttribute("updating", default=False,
		description="Keep existing tables on import?  You usually want this"
			" False unless you have some kind of sources management,"
			" e.g., via a sources ignore specification.", copyable=True)
	_makes = base.StructListAttribute("makes", childFactory=Make,
		copyable=True, description="Specification of a target table and the"
			" rowmaker to feed them.")
	_properties = base.PropertyAttribute()
	_rd = common.RDAttribute()
	_original = base.OriginalAttribute()
	_ref = base.RefAttribute()

	def onElementComplete(self):
		self._onElementCompleteNext(DataDescriptor)
		for t in self.tables:
			t.setMetaParent(self)

	def getDynamicAttribute(self, name):
		try:
			grammarClass = getGrammar(name)
		except KeyError:  # no such grammar, let Structure raise its error
			return
		self.managedAttrs[name] = self._grammar
		return self._grammar

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


_grammarRegistry = {}

def registerGrammar(grammarClass):
	elName = grammarClass.name_
	_grammarRegistry[elName] = grammarClass


def getGrammar(grammarName):
	return _grammarRegistry[grammarName]
