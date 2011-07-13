"""
Generating VOTables from internal data representations.

This is glue code to the more generic GAVO votable library.  In particular,
it governs the application of base.SerManagers and their column descriptions
(which are what is passed around as colDescs in this module to come up with 
VOTable FIELDs and the corresponding values.

You should access this module through formats.votable.
"""

import functools
import itertools
from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import stc
from gavo import utils
from gavo import votable
from gavo.base import valuemappers
from gavo.formats import common
from gavo.votable import V
from gavo.votable import modelgroups


class Error(base.Error):
	pass


tableEncoders = {
	"td": V.TABLEDATA,
	"binary": V.BINARY,
}


class VOTableContext(utils.IdManagerMixin):
	"""encoding context.

	This class provides management for unique ID attributes, the value mapper
	registry, and possibly additional services for writing VOTables.

	VOTableContexts optionally take

		- a value mapper registry (by default, valuemappers.defaultMFRegistry)
		- the tablecoding (one of the keys of votable.tableEncoders).
		- version=(1,1) to order a 1.1-version VOTable
		- acquireSamples=False to suppress reading some rows to get
		  samples for each column
		- suppressNamespace=False to leave out a namespace declaration
		  (mostly convenient for debugging)
		- overflowElement (see votable.tablewriter.OverflowElement)
	"""
	def __init__(self, mfRegistry=valuemappers.defaultMFRegistry, 
			tablecoding='binary', version=None, acquireSamples=True,
			suppressNamespace=False, overflowElement=None):
		self.mfRegistry = mfRegistry
		self.tablecoding = tablecoding
		self.version = version or (1,2)
		self.acquireSamples = acquireSamples
		self.suppressNamespace = suppressNamespace
		self.overflowElement = overflowElement


def _addID(rdEl, votEl, idManager):
	"""adds an ID attribute to votEl if rdEl has an id managed by idManager.
	"""
	try:
		votEl.ID = idManager.getIdFor(rdEl)
	except base.NotFoundError: 
		# the param is not referenced and thus needs no ID
		pass



################# Turning simple metadata into VOTable elements.

def _iterInfoInfos(dataSet):
	"""returns a sequence of V.INFO items from the info meta of dataSet.
	"""
	for infoItem in dataSet.getMeta("info", default=[]):
		name, value, id = infoItem.infoName, infoItem.infoValue, infoItem.infoId
		yield V.INFO(name=name, value=value, ID=id)[infoItem.getContent()]


def _iterWarningInfos(dataSet):
	"""yields INFO items containing warnings from the tables in dataSet.
	"""
	for table in dataSet.tables.values():
		for warning in table.getMeta("_warning", propagate=False, default=[]):
			yield V.INFO(name="warning", value="In table %s: %s"%(
				table.tableDef.id, unicode(warning)))


def _iterResourceMeta(ctx, dataSet):
	"""adds resource metadata to the Resource parent.
	"""
	yield V.DESCRIPTION[base.getMetaText(dataSet, "description")]
	for el in  itertools.chain(
			_iterInfoInfos(dataSet), _iterWarningInfos(dataSet)):
		yield el


def _iterToplevelMeta(ctx, dataSet):
	"""yields meta elements for the entire VOTABLE from dataSet's RD.
	"""
	rd = dataSet.dd.rd
	if rd is None:
		return
	yield V.DESCRIPTION[base.getMetaText(rd, "description")]
	yield V.INFO(name="legal", value=base.getMetaText(rd, "copyright"))


################# Generating FIELD and PARAM elements.

def _makeValuesForColDesc(colDesc):
	"""returns a VALUES element for a column description.

	This just stringifies whatever is in colDesc's respective columns,
	so for anything fancy pass in byte strings to begin with.
	"""
	valEl = V.VALUES()
	if colDesc["min"] is not valuemappers._Supremum:
		valEl[V.MIN(value=str(colDesc["min"]))]
	if colDesc["max"] is not valuemappers._Infimum:
		valEl[V.MAX(value=str(colDesc["max"]))]
	if colDesc["nullvalue"] is not None:
		valEl(null=colDesc["nullvalue"])
	return valEl


# keys copied from colDescs to FIELDs in _getFieldFor
_voFieldCopyKeys = ["name", "ID", "datatype", "ucd", "utype", "xtype"]

def defineField(element, colDesc):
	"""adds attributes and children to element from colDesc.

	element can be a V.FIELD or a V.PARAM *instance* and is changed in place.

	This function returns None to remind people we're changing in place
	here.
	"""
	# bomb if you got an Element rather than an instance -- with an
	# Element, things would appear to work, but changes are lost when
	# this function ends.
	assert not isinstance(element, type)
	if colDesc["arraysize"]!='1':
		element(arraysize=colDesc["arraysize"])
	# (for char, keep arraysize='1' to keep topcat happy)
	if colDesc["datatype"]=='char' and colDesc["arraysize"]=='1':
		element(arraysize='1')
	if colDesc["unit"]:
		element(unit=colDesc["unit"])
	element(**dict((key, colDesc.get(key)) for key in _voFieldCopyKeys))[
		_makeValuesForColDesc(colDesc),
		V.DESCRIPTION[colDesc["description"]]]


def makeFieldFromColumn(colType, rscCol):
	"""returns a VOTable colType for a rscdef column-type thing.

	This function lets you make PARAM and FIELD elements (colType) from
	column or param instances.
	"""
	instance = colType()
	defineField(instance, valuemappers.VColDesc(rscCol))
	return instance


def _iterFields(serManager):
	"""iterates over V.FIELDs based on serManger's columns.
	"""
	for colDesc in serManager:
		el = V.FIELD()
		defineField(el, colDesc)
		yield el


# default null values for params for special types
_PARAM_NULLS = {
	"integer": "-1",
	"bigint": "-1",
	"smallint": "-1",
	"real": "NaN",
	"double precision": "NaN",
	"char": "X",}

def _defineNullInValues(votEl, nullLiteral):
	"""sets nullLiteral as null attribute in a VALUES child of votEl.

	If no VALUES child exists yet, we make one up.
	"""
	try:
		valuesEl = votEl.makeChildDict()["VALUES"]
		valuesEl[0](null=nullLiteral)
	except KeyError:
		votEl[V.VALUES(null=nullLiteral)]


def _makeVOTParam(ctx, param):
	"""returns VOTable stan for param.

	If param's value is NotGiven, it will count as a null value for
	VOTable purposes.  This is since params frequently are referred to,
	and we don't want the ref targets to vanish.
	"""
	# note that we're usually accessing the content, i.e., the string
	# serialization we got.  The only exception is when we're seeing
	# nulls or null-equivalents.
	if param.content_ is base.NotGiven or param.value is None:
		content = None
	else:
		content = param.content_

	el = V.PARAM()
	defineField(el, valuemappers.VColDesc(param))
	if content is None:
		# Null value generation -- tactics: If we have a nullLiteral, use it
		# otherwise use some type-dependent default
		if param.values.nullLiteral is None:
			nullLiteral = _PARAM_NULLS.get(param.type, "__NULL__")
			_defineNullInValues(el, nullLiteral)
		else:
			nullLiteral =param.values.nullLiteral
		el.value = nullLiteral
	else:
		el.value = content
	return el


def _iterTableParams(serManager):
	"""iterates over V.PARAMs based on the table's param elements.
	"""
	for param in serManager.table.iterParams():
		votEl = _makeVOTParam(serManager, param)
		if votEl is not None:
			_addID(param, votEl, serManager)
			yield votEl


def _iterParams(ctx, dataSet):
	"""iterates over the entries in the parameters table of dataSet.
	"""
	try:
		parTable = dataSet.getTableWithRole("parameters")
	except base.DataError:  # no parameter table
		return
	
	values = {}
	if parTable:  # no data for parameters: keep empty values.
		values = parTable.rows[0]

	for item in parTable.tableDef:
		colDesc = valuemappers.VColDesc(item)
		el = V.PARAM()
		el(value=ctx.mfRegistry.getMapper(colDesc)(values.get(item.name)))
		defineField(el, colDesc)
		_addID(el, item, ctx)
		yield el


####################### Tables and Resources


def _iterSTC(tableDef, serManager):
	"""adds STC groups for the systems to votTable fetching data from 
	tableDef.
	"""
	def getIdFor(colRef):
		return serManager.getColDescByName(colRef.dest)["ID"]
	for ast in tableDef.getSTCDefs():
		yield modelgroups.marshal_STC(ast, getIdFor)


def _iterNotes(serManager):
	"""yields GROUPs for table notes.

	The idea is that the note is in the group's description, and the FIELDrefs
	give the columns that the note applies to.
	"""
	# add notes as a group with FIELDrefs, but don't fail on them
	for key, note in serManager.notes.iteritems():
		noteId = serManager.getOrMakeIdFor(note)
		noteGroup = V.GROUP(name="note-%s"%key, ID=noteId)[
			V.DESCRIPTION[note.getContent(targetFormat="text")]]
		for col in serManager:
			if col["note"] is note:
				noteGroup[V.FIELDref(ref=col["ID"])]
		yield noteGroup


def _makeRef(baseType, ref, container, serManager):
	"""returns a new node of baseType reflecting the group.TypedRef 
	instance ref.

	container is the destination of the reference.  For columns, that's
	the table definition, but for parameters, this must be the table
	itself rather than its definition because it's the table's
	params that are embedded in the VOTable.
	"""
	return baseType(
		ref=serManager.getOrMakeIdFor(ref.resolve(container)),
		utype=ref.utype,
		ucd=ref.ucd)


def _iterGroups(container, serManager):
	"""yields GROUPs for the RD groups within container, taking params and
	fields from serManager's table.

	container can be a tableDef or a group.
	"""
	for group in container.groups:
		votGroup = V.GROUP(ucd=group.ucd, utype=group.utype, name=group.name)
		votGroup[V.DESCRIPTION[group.description]]

		for ref in group.columnRefs:
			votGroup[_makeRef(V.FIELDref, ref,
				serManager.table.tableDef, serManager)]

		for ref in group.paramRefs:
			votGroup[_makeRef(V.PARAMref, ref,
				serManager.table, serManager)]

		for param in group.params:
			votGroup[_makeVOTParam(serManager, param)]

		for subgroup in _iterGroups(group, serManager):
			votGroup[subgroup]

		yield votGroup


def makeTable(ctx, table):
	"""returns a Table node for the table.Table instance table.
	"""
	sm = valuemappers.SerManager(table, mfRegistry=ctx.mfRegistry,
		idManager=ctx, acquireSamples=ctx.acquireSamples)
	result = V.TABLE(name=table.tableDef.id)[
		V.DESCRIPTION[base.getMetaText(table.tableDef, "description")],
		_iterNotes(sm),
		_iterGroups(table.tableDef, sm),
		_iterTableParams(sm),
		_iterFields(sm)]

	if ctx.version>(1,1):
		result[_iterSTC(table.tableDef, sm)]

	return votable.DelayedTable(result,
		sm.getMappedTuples(),
		tableEncoders[ctx.tablecoding],
		overflowElement=ctx.overflowElement)


def _makeResource(ctx, data):
	"""returns a Resource node for the rsc.Data instance data.
	"""
	res = V.RESOURCE(type=base.getMetaText(data, "_type"))[
		_iterResourceMeta(ctx, data),
		_iterParams(ctx, data)]
	for table in data:
		if table.role!="parameters":
			res[makeTable(ctx, table)]
	res[ctx.overflowElement]
	return res

############################# Toplevel/User-exposed code


def makeVOTable(data, ctx=None, **kwargs):
	"""returns a votable.V.VOTABLE object representing data.

	data can be an rsc.Data or an rsc.Table.  data can be a data or a table
	instance, tablecoding any key in votable.tableEncoders.

	You may pass a VOTableContext object; if you don't a context
	with all defaults will be used.

	A deprecated alternative is to directly pass VOTableContext constructor
	arguments as additional keyword arguments.  Don't do this, though,
	we'll probably remove the option to do so at some point.
	
	You will usually pass the result to votable.write.  The object returned
	contains DelayedTables, i.e., most of the content will only be realized at
	render time.
	"""
	ctx = ctx or VOTableContext(**kwargs)

	data = rsc.wrapTable(data)
	if ctx.version==(1,1):
		vot = V.VOTABLE11()
	elif ctx.version==(1,2):
		vot = V.VOTABLE()
	else:
		raise common.VOTableError("No toplevel element for VOTable version %s"%
			ctx.version)
	vot[_iterToplevelMeta(ctx, data)]
	vot[_makeResource(ctx, data)]
	if ctx.suppressNamespace:  
		# use this for "simple" table with nice element names
		vot._fixedTagMaterial = ""

	# What follows is a hack around the insanity of stuffing
	# unused namespaces and similar detritus into VOTable's roots.
	rootAttrs = data.getMeta("_votableRootAttributes")
	if rootAttrs:
		rootHacks = [vot._fixedTagMaterial]+[
			item.getContent() for item in rootAttrs]
		vot._fixedTagMaterial = " ".join(s for s in rootHacks if s)

	return vot


def writeAsVOTable(data, outputFile, ctx=None, **kwargs):
	"""a formats.common compliant data writer.

	See makeVOTable for the arguments.
	"""
	ctx = ctx or VOTableContext(**kwargs)
	vot = makeVOTable(data, ctx)
	votable.write(vot, outputFile)


def getAsVOTable(data, ctx=None, **kwargs):
	"""returns a string containing a VOTable representation of data.

	For information on the arguments, refer to makeVOTable.
	"""
	ctx = ctx or VOTableContext(**kwargs)
	dest = StringIO()
	writeAsVOTable(data, dest, ctx)
	return dest.getvalue()


def format(data, outputFile, **ctxargs):
# used for construction of the formats.common interface
	return writeAsVOTable(data, outputFile, VOTableContext(**ctxargs))

common.registerDataWriter("votable", format, 
	"application/x-votable+xml")
common.registerDataWriter("votabletd", functools.partial(
	format, tablecoding="td"), "text/xml")
