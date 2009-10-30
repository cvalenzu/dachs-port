"""
Description and definition of tables.
"""

import itertools
import re
import traceback

from gavo import base
from gavo import stc
from gavo import utils
from gavo.base import structure
from gavo.rscdef import column
from gavo.rscdef import common
from gavo.rscdef import macros
from gavo.rscdef import mixins
from gavo.rscdef import rmkfuncs
from gavo.rscdef import rowtriggers
from gavo.rscdef import scripting


MS = base.makeStruct

class IgnoreThisRow(Exception):
	"""is raised by TableDef.validateRow if a row should be ignored.
	This exception must be caught upstream.
	"""


class DBIndex(base.Structure):
	"""A description of an index in the database.

	The corresponding index will be created after the table is imported.
	"""
	name_ = "index"

	_name = base.UnicodeAttribute("name", default=base.Undefined,
		description="Name of the index (defaults to something computed from"
			" columns)", copyable=True)
	_columns = base.StringListAttribute("columns", description=
		"Table columns taking part in the index (must be given even if there"
		" is an expression building the index and mention all columns taking"
		" part in the index generated by it", copyable=True)
	_cluster = base.BooleanAttribute("cluster", default=False,
		description="Cluster the table according to this index?",
		copyable=True)
	_code = base.DataContent(copyable=True, description=
		"Raw SQL specifying an expression the table should be"
		" indexed for.  If not given, the expression will be generated from"
		" columns (which is what you usually want).")

	def completeElement(self):
		self._completeElementNext(DBIndex)
		if not self.columns:
			raise base.StructureError("Index without columns is verboten.")
		if self.name is base.Undefined:
			self.name = "%s_%s"%(self.parent.id, re.sub("[^\w]+", "_",
				"_".join(self.columns)))
		if not self.content_:
			self.content_ = "%s"%",".join(self.columns)


class ColumnTupleAttribute(base.StringListAttribute):
	"""is a tuple of column names.

	In a validate method, it checks that the names actually are in parent's
	fields.
	"""
	def iterParentMethods(self):
		"""adds a getPrimaryIn method to the parent class.

		This function will return the value of the primary key in a row
		passed.  The whole thing is a bit dense in that I want to compile
		that method to avoid having to loop every time it is called.  This
		compilation is done in a descriptor -- ah well, probably it's a waste
		of time anyway.
		"""
		def makeGetPrimaryFunction(instance):
			funcSrc = ('def getPrimaryIn(row):\n'
				'	return (%s)')%(" ".join(['row["%s"],'%name
					for name in getattr(instance, self.name_)]))
			return utils.compileFunction(funcSrc, "getPrimaryIn")

		def getPrimaryIn(self, row):
			try:
				return self.__getPrimaryIn(row)
			except AttributeError:
				self.__getPrimaryIn = makeGetPrimaryFunction(self)
				return self.__getPrimaryIn(row)
		yield "getPrimaryIn", getPrimaryIn

	def validate(self, parent):
		for colName in getattr(parent, self.name_):
			try:
				parent.getColumnByName(colName)
			except base.NotFoundError:
				raise base.LiteralParseError("Column tuple component %s is"
					" not in parent table"%colName, self.name_, colName)


class ForeignKey(base.Structure):
	"""A description of a foreign key relation between this table and another
	one.
	"""
	name_ = "foreignKey"

	_table = base.UnicodeAttribute("table", default=base.Undefined,
		description="Fully qualified SQL name of the table holding the"
		" key.", copyable=True)
	_source = base.UnicodeAttribute("source", default=base.Undefined,
		description="Comma-separated list of local columns corresponding"
			" to the foreign key.  No sanity checks are performed here.")
	_dest = base.UnicodeAttribute("dest", default=base.NotGiven,
		description="Comma-separated list of columns in the target table"
			" belonging to its key.  No checks for their existence, uniqueness,"
			" etc. are done here.  If not given, defaults to source.")

	def getDescription(self):
		return "%s -> %s:%s"%(",".join(self.source), self.table, 
			".".join(self.dest))

	def _parseList(self, raw):
		return [s.strip() for s in raw.split(",") if s.strip()]

	def onElementComplete(self):
		self.source = self._parseList(self.source)
		if self.dest is base.NotGiven:
			self.dest = self.source
		else:
			self.dest = self._parseList(self.dest)
		self._onElementCompleteNext(ForeignKey)
	
	def create(self, querier):
		if not querier.foreignKeyExists(self.parent.getQName(), self.table,
				self.source, self.dest):
			return querier.query("ALTER TABLE %s ADD FOREIGN KEY (%s)"
				" REFERENCES %s (%s)"
				" DEFERRABLE INITIALLY DEFERRED"%(self.parent.getQName(),
					",".join(self.source), self.table, ",".join(self.dest)))

	def delete(self, querier):
		try:
			constraintName = querier.getForeignKeyName(self.parent.getQName(), 
				self.table, self.source, self.dest)
		except base.DBError:  # key does not exist.
			return
		querier.query("ALTER TABLE %s DROP CONSTRAINT %s"%(self.parent.getQName(), 
			constraintName))


class STCDef(base.Structure):
	"""A definition of a space-time coordinate system using STC-S.
	"""
# Programmatically, you have 
# * compiled -- an AST of the entire specification
# * iterColTypes -- iterates over column name/utype pairs, for the 
#	  embedding table only; all others must not touch it

	name_ = "stc"

	_source = base.DataContent(copyable=True, description="An STC-S string"
		" with column references (using quote syntax) instead of values")

	def completeElement(self):
		self._onElementCompleteNext(STCDef)
		self.compiled = stc.parseQSTCS(self.content_)
		_, self._origFields = stc.getUtypes(self.compiled)
	
	def iterColTypes(self):
		return self._origFields.iteritems()


class TableDef(base.Structure, base.MetaMixin, common.RolesMixin,
		scripting.ScriptingMixin, macros.StandardMacroMixin):
	"""A definition of a table, both on-disk and internal.

	Some attributes are ignored for the in-memory tables, (roles or adql)
	"""
	name_ = "table"

	# We don't want to force people to come up with an id for all their
	# internal tables but want to avoid writing default-named tables to
	# the db.  Thus, the default is not a valid sql identifier.
	_id = base.IdAttribute("id", default=base.NotGiven, description=
		"Name of the table (must be SQL-legal for onDisk tables)")
	_rd = common.RDAttribute()
	_cols =  common.ColumnListAttribute("columns",
		childFactory=column.Column, description="Columns making up this table.",
		copyable=True)
	_onDisk = base.BooleanAttribute("onDisk", False, description=
		"Table in the database rather than in memory?")  # this must not be copyable
		  # since queries might copy the tds and havoc would result if the queries
		  # were to end up on disk.
	_temporary = base.BooleanAttribute("temporary", False, description=
		"If this is an onDisk table, make it temporary?  This is mostly"
		" useful for custom cores and such.", copyable=True)
	_adql = base.BooleanAttribute("adql", False, description=
		"Should this table be available for ADQL queries?")
	_forceUnique = base.BooleanAttribute("forceUnique", False, description=
		"Enforce dupe policy for primary key (see dupePolicy)?")
	_dupePolicy = base.EnumeratedUnicodeAttribute("dupePolicy",
		"check", ["check", "drop", "overwrite"], description=
		"Handle duplicate rows with identical primary keys manually by"
		" raising an error if existing and new rows are not identical (check),"
		" dropping the new one (drop), or overwriting the old one (overwrite)?")
	_primary = ColumnTupleAttribute("primary", default=(),
		description="Comma separated names of columns making up the primary key.")
	_indices = base.StructListAttribute("indices", childFactory=DBIndex,
		description="Indices defined on this table", copyable=True)
	_foreignKeys = base.StructListAttribute("foreignKeys", 
		childFactory=ForeignKey, description="Foreign keys used in this"
		" table", copyable=True)
	_system = base.BooleanAttribute("system", default=False,
		description="Is this a system table?  If it is, it will not be"
			" dropped on normal imports, and accesses to it will not be logged.")
	_ignoreOn = base.StructAttribute("ignoreOn", default=None, copyable=True,
		description="Conditions for excluding records from being written to the"
			" DB.  Note that they are only evaluated if validation is enabled"
			" in the parse options, e.g. via gavoimp (where validation is the"
			" default).",
		childFactory=rowtriggers.IgnoreOn)
	# don't copy stc -- columns just keep the reference to the original
	# stc on copy, and nothing should rely on column stc actually being
	# defined in the parent tableDefs.
	_stcs = base.StructListAttribute("stc", description="STC-S definitions"
		" of coordinate systems.", childFactory=STCDef)
	_ref = base.RefAttribute()
	_mixins = mixins.MixinAttribute(copyable=True)
	_original = base.OriginalAttribute()
	_namePath = common.NamePathAttribute()

	validWaypoints = set(["preIndex", "preIndexSQL", "viewCreation", 
		"afterDrop"])
	fixupFunction = None

	def __iter__(self):
		return iter(self.columns)

	def __contains__(self, name):
		try:
			self.columns.getColumnByName(name)
		except base.NotFoundError:
			return False
		return True

	def _resolveSTC(self):
		"""adds STC related attributes to this tables' columns.
		"""
		for stcDef in self.stc:
			for name, type in stcDef.iterColTypes():
				destCol = self.getColumnByName(name)
				if destCol.stc is not None: 
					raise base.LiteralParseError(
						"Column %s is referenced twice from STC"%name, None, name)
				destCol.stc = stcDef.compiled.astroSystem
				destCol.stcUtype = type

	def completeElement(self):
		# allow iterables to be passed in for columns and convert them
		# to a ColumnList here
		if not isinstance(self.columns, common.ColumnList):
			self.columns = common.ColumnList(self.columns)
		if self.id is base.NotGiven:
			self.id = hex(id(self))[2:]
		self._resolveSTC()
		self._completeElementNext(TableDef)

	def _defineFixupFunction(self):
		"""defines a function to fix up records from column's fixup attributes.

		This will leave a fixupFunction attribute which will be None if
		no fixups are defined.
		"""
		fixups = []
		for col in self:
			if col.fixup is not None:
				fixups.append((col.name, col.fixup))
		if fixups:
			assignments = []
			for key, expr in fixups:
				expr = expr.replace("___", "row['%s']"%key)
				assignments.append("  row['%s'] = %s"%(key, expr))
			self.fixupFunction = rmkfuncs.makeProc("fixup",
				"def fixup(row):\n%s\n  return row"%("\n".join(assignments)),
				"", None)

	def onElementComplete(self):
		if self.adql:
			self.readRoles = self.readRoles | base.getConfig("db", "adqlRoles")
		self.dictKeys = [c.name for c in self]
		self.indexedColumns = set()
		for index in self.indices:
			for col in index.columns:
				if "\\" in col:
					try:
						self.indexedColumns.add(self.expand(col))
					except base.Error:  # cannot expand yet, ignore
						pass
				else:
					self.indexedColumns.add(col)
		if self.primary:
			self.indexedColumns |= set(self.primary)
		self._defineFixupFunction()
		self._onElementCompleteNext(TableDef)

	def hackMixinsAfterMakeStruct(self):
		"""tries to apply mixins not fed.

		This is a hack for when you makeStructed a table but still want
		mixins that need to be fed.  It will only work if
		the mixins no not need a parse context.
		"""
		for mixinName in self.mixins:
			self._mixins._processEarly(self, mixinName)

	def macro_curtable(self):
		"""returns the qualified name of the current table.
		"""
		return self.getQName()

	def macro_tablename(self):
		"""returns the unqualified name of the current table.
		"""
		return self.id

	def macro_nameForUCD(self, ucd):
		"""returns the (unique!) name of the field having ucd in this table.

		If there is no or more than one field with the ucd in this table,
		we raise an exception.
		"""
		return self.getColumnByUCD(ucd).name

	def macro_nameForUCDs(self, ucds):
		"""returns the (unique!) name of the field having one
		of ucds in this table.

		Ucds is a selection of ucds separated by vertical bars
		(|).  The rules for when this raises errors are so crazy
		you don't want to think about them.  This really is
		only intended for cases where "old" and "new" standards
		are to be supported, like with pos.eq.*;meta.main and
		POS_EQ_*_MAIN.

		If there is no or more than one field with the ucd in
		this table, we raise an exception.
		"""
		return self.getColumnByUCDs(*(s.strip() for s in ucds.split("|"))).name

	def getQName(self):
		if self.temporary:
			return self.id
		else:
			if self.rd is None:
				raise base.Error("TableDefs without resource descriptor"
					" have no qualified names")
			return "%s.%s"%(self.rd.schema, self.id)

	def validateRow(self, row):
		"""checks that row is complete and complies with all known constraints on
		the columns

		The function raises a ValidationError with an appropriate message
		and the relevant field if not.
		"""
		for column in self:
			if column.name not in row:
				raise base.ValidationError("Column %s missing"%column.name,
					column.name, row)
			try:
				column.validateValue(row[column.name])
			except base.ValidationError, ex:
				ex.row = row
				raise
		if self.ignoreOn:
			if self.ignoreOn(row):
				raise IgnoreThisRow(row)

	def getFieldIndex(self, fieldName):
		"""returns the index of the field named fieldName.
		"""
		return self.columns.getFieldIndex(fieldName)

	def getColumnByName(self, name):
		"""delegates to common.ColumnList.
		"""
		try:
			return self.columns.getColumnByName(name)
		except base.NotFoundError, msg:
			msg.table = "table %s"%self.id
			raise

	def getColumnsByUCD(self, ucd):
		"""delegates to common.ColumnList.
		"""
		return self.columns.getColumnsByUCD(ucd)

	def getColumnByUCD(self, ucd):
		"""delegates to common.ColumnList.
		"""
		return self.columns.getColumnByUCD(ucd)

	def getColumnByUCDs(self, *ucds):
		"""delegates to common.ColumnList.
		"""
		return self.columns.getColumnByUCDs(*ucds)
	
	def getColumnsByUCDs(self, *ucds):
		res = []
		for ucd in ucds:
			res.extend(self.columns.getColumnsByUCD(ucd))
		return res

	def getProductColumns(self):
		"""returns the names of the columns containing products.

		They are identified by the presence of a type=product display hint.
		"""
		res = []
		for col in self:
			if col.displayHint.get("type")=="product":
				res.append(col.name)
		return res

	def makeRowFromTuple(self, dbTuple):
		"""returns a row (dict) from a row as returned from the database.
		"""
		preRes = dict(itertools.izip(self.dictKeys, dbTuple))
		if self.fixupFunction:
			return self.fixupFunction(preRes)
		return preRes

	def getDefaults(self):
		"""returns a mapping from column names to defaults to be used when
		making a row for this table.
		"""
		defaults = {}
		for col in self:
			if col.values:
				defaults[col.name] = col.values.default
			elif not col.required:
				defaults[col.name] = None
		return defaults
				
	def processMixinsLate(self):
		for mixinName in self.mixins:
			mixins.getMixin(mixinName).processLate(self)

	def getSTCSystems(self, idManager):
		"""returns systems utype dictionaries for the STCs embedded in this table.
		
		idManager must be an object mixing in IdManagerMixin.  This is used
		here to check wheter a given STC has been included already.  The id
		returned is discarded.  We can do this since the autogenerated
		id should be unique to begin with.

		The function returns a sequence of (id, dict) pairs.
		"""
		# Do not use our stc attribute -- the columns may come from different
		# tables and carry stc from there.
		stcObjects = set(col.stc for col in self)
		if None in stcObjects: 
			stcObjects.remove(None)
		return [pair for pair in
				((idManager.makeIdFor(stc), stc) for stc in stcObjects)
			if pair[0] is not None]  # Weed out stcs already included

	@staticmethod
	def disambiguateColumns(columns):
		"""returns a sequence of columns without duplicate names.
		"""
		newColumns, seenNames = [], set()
		for c in columns:
			while c.name in seenNames:
				c.name = c.name+"_"
			newColumns.append(c)
			seenNames.add(c.name)
		return newColumns

	@classmethod
	def fromColumns(cls, columns, **kwargs):
		"""returns a TableDef from a sequence of columns.

		You can give additional constructor arguments.  makeStruct is used
		to build the instance, the mixin hack is applied.

		Columns with identical names will be disambiguated.
		"""
		res = MS(cls, 
			columns=common.ColumnList(cls.disambiguateColumns(columns)),
			**kwargs)
		res.hackMixinsAfterMakeStruct()
		return res
		

class FieldRef(base.Structure):
	"""A reference to a column in a table definition using the table's
	id and the column name.
	"""
	name_ = "fieldRef"
	_srcTable = base.ReferenceAttribute("table", forceType=TableDef,
		description="Reference to the table the field comes from.",
		default=base.Undefined)
	_srcCol = base.UnicodeAttribute("column", default=base.Undefined,
		description="Column name within the referenced table.")

	def onElementComplete(self):
		self._onElementCompleteNext(FieldRef)
		if not self.column in self.table:
			raise base.StructureError("No field '%s' in table %s"%(
				self.column, self.table.getQName()))

	def getColumn(self):
		return self.table.getColumnByName(self.column)

	def getQName(self):
		return "%s.%s"%(self.table.getQName(), self.column)


class SimpleView(base.Structure, base.MetaMixin):
	"""A simple way to define a view over some tables.

	To define a view in this way, you add fieldRef elements, giving
	table ids and column names.  The view will be a natural join of
	all tables involved.

	For more complex views, use a normal table with a viewCreation script.

	These elements can be referred to like normal tables (internally, they
	are replaced by TableDefs when they are complete).
	"""
	name_ = "simpleView"

	_rd = common.RDAttribute()
	# force an id on those
	_id = base.IdAttribute("id", default=base.Undefined, description=
		"Name of the view (must be SQL-legal)")
	_cols = base.StructListAttribute("colRefs", childFactory=FieldRef,
		description="References to the fields making up the natural join"
		" of the simple view.")

	def onElementComplete(self):
		self._onElementCompleteNext(SimpleView)
		raise base.Replace(self.getTableDef(), newName="tables")

	def _getDDL(self):
		tableNames = set(c.table.getQName() for c in self.colRefs)
		columnNames = [c.getQName() for c in self.colRefs]
		return "CREATE VIEW %s.%s AS (SELECT %s FROM %s)"%(
			self.rd.schema,
			self.id,
			",".join(columnNames),
			" NATURAL JOIN ".join(tableNames))

	def getTableDef(self):
		"""returns a TableDef for the view.
		"""
		return MS(TableDef, parent_=self.parent, id=self.id, 
			onDisk=True, columns=[c.getColumn() for c in self.colRefs],
			scripts=[MS(scripting.Script, type="viewCreation", name="create view",
			content_=self._getDDL())])


def makeTDForColumns(name, cols, **moreKWs):
	"""returns a TableDef object named names and having the columns cols.

	cols is some sequence of Column objects.  You can give arbitrary
	table attributes in keyword arguments.
	"""
	kws = {"id": name, "columns": common.ColumnList(cols)}
	kws.update(moreKWs)
	return base.makeStruct(TableDef, **kws)
