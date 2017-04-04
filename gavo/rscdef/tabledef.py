"""
Description and definition of tables.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import itertools
import re

from gavo import adql
from gavo import base
from gavo import dm
from gavo import stc
from gavo import utils
from gavo.rscdef import column
from gavo.rscdef import common
from gavo.rscdef import group
from gavo.rscdef import mixins
from gavo.rscdef import rmkfuncs


MS = base.makeStruct


class DBIndex(base.Structure):
	"""A description of an index in the database.

	In real databases, indices may be fairly complex things; still, the
	most common usage here will be to just index a single column::

		<index columns="my_col"/>
	
	To index over functions, use  the character content; parentheses are added
	by DaCHS, so don't have them in the content.  An explicit specification
	of the index expression is also necessary to allow RE pattern matches using
	indices in character columns (outside of the C locale).  That would be::

		<index columns="uri">uri text_pattern_ops</index>

	(you still want to give columns so the metadata engine is aware of the 
	index).  See section "Operator Classes and Operator Families" in
	the Postgres documentation for details.
	"""
	name_ = "index"

	_name = base.UnicodeAttribute("name", default=base.Undefined,
		description="Name of the index.  Defaults to something computed from"
			" columns; the name of the parent table will be prepended in the DB."
			"  The default will *not* work if you have multiple indices on one"
			" set of columns.", 
			copyable=True)
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
	_method = base.UnicodeAttribute("method", default=None,
		description="The indexing method, like an index type.  In the 8.x,"
			" series of postgres, you need to set method=GIST for indices"
			" over pgsphere columns; otherwise, you should not need to"
			" worry about this.", copyable=True)

	def completeElement(self, ctx):
		if self.content_ and getattr(ctx, "restricted", False):
			raise base.RestrictedElement("index", hint="Free-form SQL on indices"
				" is not allowed in restricted mode")
		self._completeElementNext(DBIndex, ctx)
		if not self.columns:
			raise base.StructureError("Index without columns is verboten.")
		if self.name is base.Undefined:
			self.name = "%s"%(re.sub("[^\w]+", "_", "_".join(self.columns)))
		if not self.content_:
			self.content_ = "%s"%",".join(self.columns)

	def iterCode(self):
		destTableName = self.parent.getQName()
		usingClause = ""
		if self.method is not None:
			usingClause = " USING %s"%self.method
		yield self.parent.expand("CREATE INDEX %s ON %s%s (%s)"%(
			self.dbname, destTableName, usingClause, self.content_))
		if self.cluster:
			yield self.parent.expand(
				"CLUSTER %s ON %s"%(self.dbname, destTableName))

	def create(self, querier):
		"""creates the index on the parent table if necessary.
		
		querier is an object mixing in the DBMethodsMixin, usually the
		DBTable object the index should be created on.
		"""
		if not querier.hasIndex(self.parent.getQName(), self.dbname):
			if not self.parent.system:
				base.ui.notifyIndexCreation(
					self.parent.expand(self.dbname))
			for statement in self.iterCode():
				querier.query(statement)

	def drop(self, querier):
		"""drops the index if it exists.

		querier is an object mixing in the DBMethodsMixin, usually the
		DBTable object the index possibly exists on.
		"""
		iName = self.parent.expand(self.dbname)
		if querier.hasIndex(self.parent.getQName(), iName):
			querier.query("DROP INDEX %s.%s"%(self.parent.rd.schema, iName))

	@property
	def dbname(self):
		return "%s_%s"%(self.parent.id, self.name)


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
				raise base.ui.logOldExc(base.LiteralParseError(self.name_, colName, 
					hint="Column tuple component %s is not in parent table"%colName))


class ForeignKey(base.Structure):
	"""A description of a foreign key relation between this table and another
	one.
	"""
	name_ = "foreignKey"

	_inTable = base.ReferenceAttribute("inTable", default=base.Undefined,
		description="Reference to the table the foreign key points to.",
		copyable=True)
	_source = base.UnicodeAttribute("source", default=base.Undefined,
		description="Comma-separated list of local columns corresponding"
			" to the foreign key.  No sanity checks are performed here.",
		copyable=True)
	_dest = base.UnicodeAttribute("dest", default=base.NotGiven,
		description="Comma-separated list of columns in the target table"
			" belonging to its key.  No checks for their existence, uniqueness,"
			" etc. are done here.  If not given, defaults to source.")
	_metaOnly = base.BooleanAttribute("metaOnly", default=False,
		description="Do not tell the database to actually create the foreign"
			" key, just declare it in the metadata.  This is for when you want"
			" to document a relationship but don't want the DB to actually"
			" enforce this.  This is typically a wise thing to do when you have, say"
			" a gigarecord of flux/density pairs and only several thousand metadata"
			" records -- you may want to update the latter without having"
			" to tear down the former.")

	def getDescription(self):
		return "%s:%s -> %s:%s"%(self.parent.getQName(), ",".join(self.source), 
			self.destTableName, ".".join(self.dest))

	def _parseList(self, raw):
		if isinstance(raw, list):
			# we're being copied
			return raw
		return [s.strip() for s in raw.split(",") if s.strip()]

	def onElementComplete(self):
		self.destTableName = self.inTable.getQName()
		self.isADQLKey = self.inTable.adql and self.inTable.adql!='hidden'

		self.source = self._parseList(self.source)
		if self.dest is base.NotGiven:
			self.dest = self.source
		else:
			self.dest = self._parseList(self.dest)
		self._onElementCompleteNext(ForeignKey)
	
	def create(self, querier):
		if self.metaOnly:
			return

		if not querier.foreignKeyExists(self.parent.getQName(), 
				self.destTableName,
				self.source, 
				self.dest):
			return querier.query("ALTER TABLE %s ADD FOREIGN KEY (%s)"
				" REFERENCES %s (%s)"
				" ON DELETE CASCADE"
				" DEFERRABLE INITIALLY DEFERRED"%(
					self.parent.getQName(),
					",".join(self.source), 
					self.destTableName, 
					",".join(self.dest)))

	def delete(self, querier):
		if self.metaOnly:
			return

		try:
			constraintName = querier.getForeignKeyName(self.parent.getQName(), 
				self.destTableName, self.source, self.dest)
		except (ValueError, base.DBError):  # key does not exist.
			return
		querier.query("ALTER TABLE %s DROP CONSTRAINT %s"%(self.parent.getQName(), 
			constraintName))

	def getAnnotation(self, roleName, container, instance):
		"""returns a dm annotation for this foreign key.
		"""
		return dm.ForeignKeyAnnotation(roleName, self, instance)


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

	def completeElement(self, ctx):
		self._completeElementNext(STCDef, ctx)
		try:
			self.compiled = stc.parseQSTCS(self.content_)
		except stc.STCSParseError, msg:
			raise base.ui.logOldExc(base.StructureError(
				"Bad stc definition: %s"%str(msg)))
		self.compiled.stripUnits()
		self._origFields = dict((value.dest, utype) 
			for utype, value in stc.getUtypes(self.compiled)
			if isinstance(value, stc.ColRef))
	
	def iterColTypes(self):
		return self._origFields.iteritems()


class ADQLVisibilityAttribute(base.BooleanAttribute):
	"""An attribute that has values True/False and hidden.
	"""
	typeDesc_ = "boolean or 'hidden'"

	def feedObject(self, instance, value):
		if value=='hidden':
			instance._readProfiles.feed(None, instance, "defaults,untrustedquery")
			value = False
		base.BooleanAttribute.feedObject(self, instance, value)
		
	def parse(self, value):
		if value.lower()=="hidden":
			return "hidden"
		return base.BooleanAttribute.parse(self, value)

	def unparse(self, value):
		if value=="hidden":
			return value
		return base.BooleanAttribute.unparse(self, value)


class PublishableDataMixin(object):
	"""A mixin with a few classes and attributes for data that can be
	published to the VO registry.

	In particular, this contains the publish element (registration attribute).
	"""
	_registration = base.StructAttribute("registration",
		default=None,
		childFactory=common.Registration,
		copyable=False,
		description="A registration (to the VO registry) of this table"
			" or data collection.")
	
	def getPublicationsForSet(self, setNames):
		"""returns a sequence of publication elements for the data, suitable
		for OAI responses for the sets setNames.

		Essentially: if registration is None, or its sets don't match
		setNames, return an emtpy sequence.
		
		If the registration mentions services, we turn their publications
		into auxiliary publications and yield them

		Otherwise, if we're published for ADQL, return the TAP service
		as an auxiliary publication.
		"""
		if (self.registration is None 
				or not self.registration.sets & setNames):
			return

		services = self.registration.services
		if not services:
			services = [base.resolveCrossId("//tap#run")]

		for service in services:
			for pub in service.getPublicationsForSet(setNames):
				yield pub.change(parent_=self, auxiliary=True)


class TableDef(base.Structure, base.ComputedMetaMixin, common.PrivilegesMixin,
		common.IVOMetaMixin, base.StandardMacroMixin, PublishableDataMixin):
	"""A definition of a table, both on-disk and internal.

	Some attributes are ignored for in-memory tables, e.g., roles or adql.

	Properties for tables:

	* supportsModel -- a short name of a data model supported through this 
	  table (for TAPRegExt dataModel); you can give multiple names separated
	  by commas.
	* supportsModelURI -- a URI of a data model supported through this table.
	  You can give multiple URIs separated by blanks.
	
	If you give multiple data model names or URIs, the sequences of names and 
	URIs must be identical (in particular, each name needs a URI).
	"""
	name_ = "table"

	resType = "table"

	# We don't want to force people to come up with an id for all their
	# internal tables but want to avoid writing default-named tables to
	# the db.  Thus, the default is not a valid sql identifier.
	_id = base.IdAttribute("id", 
		default=base.NotGiven, 
		description="Name of the table (must be SQL-legal for onDisk tables)")

	_cols =  common.ColumnListAttribute("columns",
		childFactory=column.Column, 
		description="Columns making up this table.",
		copyable=True)

	_params = common.ColumnListAttribute("params",
		childFactory=column.Param, 
		description='Param ("global columns") for this table.', 
		copyable=True)

	_viewStatement = base.UnicodeAttribute("viewStatement", 
		default=None,
		description="A single SQL statement to create a view.  Setting this"
		" makes this table a view.  The statement will typically be something"
		" like CREATE VIEW \\\\curtable AS (SELECT \\\\colNames FROM...).", 
		copyable=True)

		# onDisk must not be copyable since queries might copy the tds and havoc
		# would result if the queries were to end up on disk.
	_onDisk = base.BooleanAttribute("onDisk", 
		default=False, 
		description="Table in the database rather than in memory?")  

	_temporary = base.BooleanAttribute("temporary", 
		default=False, 
		description="If this is an onDisk table, make it temporary?"
			"  This is mostly useful for custom cores and such.", 
		copyable=True)

	_adql = ADQLVisibilityAttribute("adql", 
		default=False, 
		description="Should this table be available for ADQL queries?  In"
		" addition to True/False, this can also be 'hidden' for tables"
		" readable from the TAP machinery but not published in the"
		" metadata; this is useful for, e.g., tables contributing to a"
		" published view.  Warning: adql=hidden is incompatible with setting"
		" readProfiles manually.")

	_system = base.BooleanAttribute("system", 
		default=False,
		description="Is this a system table?  If it is, it will not be"
		" dropped on normal imports, and accesses to it will not be logged.")

	_forceUnique = base.BooleanAttribute("forceUnique", 
		default=False, 
		description="Enforce dupe policy for primary key (see dupePolicy)?")

	_dupePolicy = base.EnumeratedUnicodeAttribute("dupePolicy",
		default="check", 
		validValues=["check", "drop", "overwrite", "dropOld"], 
		description= "Handle duplicate rows with identical primary keys manually"
		" by raising an error if existing and new rows are not identical (check),"
		" dropping the new one (drop), updating the old one (overwrite), or"
		" dropping the old one and inserting the new one (dropOld)?")

	_primary = ColumnTupleAttribute("primary", 
		default=(),
		description="Comma separated names of columns making up the primary key.",
		copyable=True)

	_indices = base.StructListAttribute("indices", 
		childFactory=DBIndex,
		description="Indices defined on this table", 
		copyable=True)

	_foreignKeys = base.StructListAttribute("foreignKeys", 
		childFactory=ForeignKey, 
		description="Foreign keys used in this table", 
		copyable=False)

	_groups = base.StructListAttribute("groups",
		childFactory=group.Group,
		description="Groups for columns and params of this table",
		copyable=True)

	# this actually induces an attribute annotations with the DM
	# annotation instances
	_annotations = dm.DataModelRolesAttribute()

	_properties = base.PropertyAttribute()

	# don't copy stc -- columns just keep the reference to the original
	# stc on copy, and nothing should rely on column stc actually being
	# defined in the parent tableDefs.
	_stcs = base.StructListAttribute("stc", description="STC-S definitions"
		" of coordinate systems.", childFactory=STCDef)

	_rd = common.RDAttribute()
	_mixins = mixins.MixinAttribute()
	_original = base.OriginalAttribute()
	_namePath = common.NamePathAttribute()

	fixupFunction = None

	metaModel = ("title(1), creationDate(1), description(1),"
		"subject, referenceURL(1)")

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
		return res
	
	def __iter__(self):
		return iter(self.columns)

	def __contains__(self, name):
		try:
			self.columns.getColumnByName(name)
		except base.NotFoundError:
			return False
		return True
	
	def __repr__(self):
		try:
			return "<Table definition of %s>"%self.getQName()
		except base.Error:
			return "<Non-RD table %s>"%self.id

	def completeElement(self, ctx):
		# we want a meta parent as soon as possible, and we always let it
		# be our struct parent
		if (not self.getMetaParent() 
				and self.parent 
				and hasattr(self.parent, "_getMeta")):
			self.setMetaParent(self.parent)

		# Make room for DM annotations (these are currently filled by
		# gavo.dm.dmrd.DataModelRoles, but we might reconsider this)
		self.annotations = []

		if self.viewStatement and getattr(ctx, "restricted", False):
			raise base.RestrictedElement("table", hint="tables with"
				" view creation statements are not allowed in restricted mode")

		if self.registration and self.id is base.NotGiven:
			raise base.StructureError("Published tables need an assigned id.")
		if not self.id:
			self._id.feed(ctx, self, utils.intToFunnyWord(id(self)))

		# allow iterables to be passed in for columns and convert them
		# to a ColumnList here
		if not isinstance(self.columns, common.ColumnList):
			self.columns = common.ColumnList(self.columns)
		self._resolveSTC()
		self._completeElementNext(TableDef, ctx)
		self.columns.withinId = self.params.tableName = "table "+self.id

	def validate(self):
		if self.id.upper() in adql.allReservedWords:
			raise base.StructureError("Reserved word %s is not allowed as a table"
				" name"%self.id)
		self._validateNext(TableDef)

	def onElementComplete(self):
		if self.adql:
			self.readProfiles = (self.readProfiles | 
				base.getConfig("db", "adqlProfiles"))
		self.dictKeys = [c.key for c in self]

		self.indexedColumns = set()
		for index in self.indices:
			for col in index.columns:
				if "\\" in col:
					try:
						self.indexedColumns.add(self.expand(col))
					except (base.Error, ValueError):  # cannot expand yet, ignore
						pass
				else:
					self.indexedColumns.add(col)
		if self.primary:
			self.indexedColumns |= set(self.primary)

		self._defineFixupFunction()

		self._onElementCompleteNext(TableDef)

		if self.registration:
			self.registration.register()

		# if there's no DM annotation yet, there's still a chance that our
		# columns and params brought some with them.  Try that.
		if not self.annotations:
			self.updateAnnotationFromChildren()

	def getElementForName(self, name):
		"""returns the first of column and param having name name.

		The function raises a NotFoundError if neiter column nor param with
		name exists.
		"""
		try:
			try:
				return self.columns.getColumnByName(name)
			except base.NotFoundError:
				return self.params.getColumnByName(name)
		except base.NotFoundError, ex:
			ex.within = "table %s"%self.id
			raise

	def _resolveSTC(self):
		"""adds STC related attributes to this tables' columns.
		"""
		for stcDef in self.stc:
			for name, type in stcDef.iterColTypes():
				destCol = self.getColumnByName(name)
				if destCol.stc is not None: 
#	don't warn -- this kind of annotation is done for the future,
# when we can handle it properly.
					continue
#					base.ui.notifyWarning("Column %s is referenced twice from STC"
#						" in table %s is referenced twice in STC groups.  This"
#						" is currently not supported, the second reference is"
#						" ignored."%(name, self.getQName()))
				destCol.stc = stcDef.compiled
				destCol.stcUtype = type

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
			source = self.expand(
				"def fixup(row):\n%s\n  return row"%("\n".join(assignments)))
			self.fixupFunction = rmkfuncs.makeProc("fixup", source,
				"", None)

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
		for col in self:
			if col.key not in row:
				raise base.ValidationError("Column %s missing"%col.name,
					col.name, row, hint="The table %s has a column named '%s',"
					" but the input row %s does not give it.  This typically means"
					" bad input or a rowmaker failing on some corner case."%(
						self.id, col.name, row))
			try:
				col.validateValue(row[col.name])
			except base.ValidationError, ex:
				ex.row = row
				raise

	def getFieldIndex(self, fieldName):
		"""returns the index of the field named fieldName.
		"""
		return self.columns.getFieldIndex(fieldName)

	def getParamByName(self, name):
		return self.params.getColumnByName(name)

	def getColumnByName(self, name):
		return self.columns.getColumnByName(name)

	def getColumnById(self, id):
		return self.columns.getColumnById(id)

	def getColumnsByUCD(self, ucd):
		return self.columns.getColumnsByUCD(ucd)

	def getColumnByUCD(self, ucd):
		return self.columns.getColumnByUCD(ucd)

	def getColumnByUCDs(self, *ucds):
		return self.columns.getColumnByUCDs(*ucds)
	
	def getColumnsByUCDs(self, *ucds):
		res = []
		for ucd in ucds:
			res.extend(self.columns.getColumnsByUCD(ucd))
		return res

	def getByUtype(self, utype):
		"""returns the column or param with utype.

		This is supposed to be unique, but the function will just return
		the first matching item it finds.
		"""
		try:
			return self.params.getColumnByUtype(utype)
		except base.NotFoundError:
			return self.columns.getColumnByUtype(utype)

	def getByUtypes(self, *utypes):
		"""returns the first param or column matching the first utype
		matching anything.
		"""
		for utype in utypes:
			try:
				return self.getByUtype(utype)
			except base.NotFoundError:
				pass
		raise base.NotFoundError(", ".join(utypes), 
			what="param or column with utype in", 
			within="table %s"%self.id)

	def getByName(self, name):
		"""returns the column or param with name.

		There is nothing keeping you from having both a column and a param with
		the same name.  If that happens, you will only see the column.  But
		don't do it.
		"""
		try:
			return self.columns.getColumnByName(name)
		except base.NotFoundError:
			return self.params.getColumnByName(name)

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
				
	def getSTCDefs(self):
		"""returns a set of all STC specs referenced in this table as ASTs.
		"""
		# Do not use our stc attribute -- the columns may come from different
		# tables and carry stc from there.
		stcObjects = utils.uniqueItems(col.stc for col in self)
		if None in stcObjects: 
			stcObjects.remove(None)
		return stcObjects

	def getNote(self, noteTag):
		"""returns the table note meta value for noteTag.

		This will raise a NotFoundError if we don't have such a note.

		You will not usually use this to retrieve meta items since columns
		have the meta values in their note attributes.  Columns, of course,
		use this to get their note attribute value.
		"""
		mi = self.getMeta("note") or []
		for mv in mi:
			if mv.tag==noteTag:
				return mv
		else:
			raise base.NotFoundError(noteTag, what="note tag", 
				within="table %s"%self.id)

	def getURL(self, rendName, absolute=True):
		"""returns the URL DaCHS will show the table info page for this table
		under.

		Of course the URL is only valid for imported tables.
		"""
		basePath = "%stableinfo/%s"%(
			base.getConfig("web", "nevowRoot"),
			self.getQName())
		if absolute:
			basePath = base.getConfig("web", "serverURL")+basePath
		return basePath

	def getDDL(self):
		"""returns an SQL statement that creates the table.
		"""
		preTable = ""
		if self.temporary:
			preTable = "TEMP "
		statement = "CREATE %sTABLE %s (%s)"%(
			preTable,
			self.getQName(),
			", ".join(column.getDDL() for column in self))
		return statement

	def getSimpleQuery(self, 
			selectClause=None, 
			fragments="",
			postfix=""):
		"""returns a query against this table.

		selectClause is a list of column names (in which case the names
		are validated against the real column names and you can use
		user input) or a literal string (in which case you must not provide
		user input or have a SQL injection hole).

		fragments (the WHERE CLAUSE) and postfix are taken as literal strings (so
		they must not contain user input).

		This is purely a string operation, so you'll have your normal
		value references in fragments and postfix, and should maintain
		the parameter dictionaries as usual.

		All parts are optional, defaulting to pulling the entire table.
		"""
		parts = ["SELECT"]

		if selectClause is None:
			parts.append("*")
		elif isinstance(selectClause, list):
			parts.append(", ".join(
				self.getColumnByName(colName).name for colName in selectClause))
		else:
			parts.append(selectClause)
	
		parts.append("FROM %s"%self.getQName())

		if fragments:
			parts.append("WHERE %s"%fragments)

		if postfix:
			parts.append(postfix)

		return " ".join(parts)

	@property
	def caseFixer(self):
		return dict((col.name.lower(), col.name) for col in self)

	def doSimpleQuery(self, 
			selectClause=None, 
			fragments="", 
			params=None,
			postfix=""):
		"""runs a query generated via getSimpleQuery and returns a list
		of rowdicts.

		This uses a table connection and queryToDicts; the keys in the 
		dictionaries will have the right case for this table's columns, though.

		params is a dictionary of fillers for fragments and postfix.
		"""
		with base.getTableConn() as conn:
			return list(
				conn.queryToDicts(
					self.getSimpleQuery(
						selectClause,
						fragments,
						postfix),
					params,
					caseFixer=self.caseFixer))

	def macro_colNames(self):
		"""returns an SQL-ready list of column names of this table.
		"""
		return ", ".join(c.name for c in self.columns)

	def macro_curtable(self):
		"""returns the qualified name of the current table.
		"""
		return self.getQName()
	
	def macro_qName(self):
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
		we raise a ValueError.
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

	def macro_getParam(self, parName, default=""):
		"""returns the string representation of the parameter parName.

		This is the parameter as given in the table definition.  Any changes
		to an instance are not reflected here.

		If the parameter named does not exist, an empty string is returned.
		NULLs/Nones are rendered as NULL; this is mainly a convenience
		for obscore-like applications and should not be exploited otherwise,
		since it's ugly and might change at some point.

		If a default is given, it will be returned for both NULL and non-existing
		params.
		"""
		try:
			param = self.params.getColumnByName(parName)
		except base.NotFoundError:
			return default
		if param.content_ is base.NotGiven or param.value is None:
			return default or "NULL"
		else:
			return param.content_

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

	def _meta_howtociteLink(self):
		"""returns a link to a how-to-cite page for this service as an URL
		meta.
		"""
		if self.onDisk:  
			# we assume we're sufficiently long-lived to merit a tableinfo if
			# we're on disk
			return base.META_CLASSES_FOR_KEYS["_related"](
				self.getURL(None, True),
				title="Advice on citing this resource")

	def _meta_referenceURL(self):
		"""returns a link to the table-info page.
		"""
		return base.META_CLASSES_FOR_KEYS["_related"](
			self.getURL(None, True),
			title="Table information")


class FieldRef(base.Structure):
	"""A reference to a table column for building simple views.
	"""
	name_ = "columnRef"
	docName_ = "columnRef (view)"
	aliases = ["fieldRef"]

	_srcTable = base.ReferenceAttribute("table", 
		default=base.Undefined,
		description="Reference to the table the field comes from.",
		forceType=TableDef)

	_srcCol = base.UnicodeAttribute("key", 
		default=base.Undefined,
		description="Column name within the referenced table.",
		aliases=["column"])

	def onElementComplete(self):
		self._onElementCompleteNext(FieldRef)
		if not self.key in self.table:
			raise base.StructureError("No field '%s' in table %s"%(
				self.key, self.table.getQName()))

	def getColumn(self):
		return self.table.getColumnByName(self.key)

	def getQName(self):
		name = "%s.%s"%(self.table.getQName(), self.key)
		if "\\" in name:
			name = self.expand(name)
		return name


class SimpleView(base.Structure, base.MetaMixin):
	"""A simple way to define a view over some tables.

	To define a view in this way, you add fieldRef elements, giving
	table ids and column names.  The view will be a natural join of
	all tables involved.

	For more complex views, use a normal table with a viewStatement.

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
			viewStatement=self._getDDL())


def makeTDForColumns(name, cols, **moreKWs):
	"""returns a TableDef object named names and having the columns cols.

	cols is some sequence of Column objects.  You can give arbitrary
	table attributes in keyword arguments.
	"""
	kws = {"id": name, "columns": common.ColumnList(cols)}
	kws.update(moreKWs)
	return base.makeStruct(TableDef, **kws)
