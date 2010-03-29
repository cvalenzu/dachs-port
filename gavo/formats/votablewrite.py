"""
Functions for generating VOTables to and from internal data
representations.

This is glue code to the more generic GAVO votable library.  In particular,
it governs the application of base.SerManagers and their column descriptions
(which are what is passed around as colDescs in this module to come up with 
VOTable FIELDs and the corresponding values.
"""

import functools
import itertools
from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import stc
from gavo import utils
from gavo import votable
from gavo.base import valuemappers
from gavo.formats import common
from gavo.grammars import votablegrammar
from gavo.votable import V


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

	VOTableContexts are constructed with

	* a value mapper registry (typically, valuemappers.defaultMFRegistry)
	* the tablecoding (one of the keys of votable.tableEncoders).
	"""
	def __init__(self, mfRegistry, tablecoding='binary'):
		self.mfRegistry = mfRegistry
		self.tablecoding = tablecoding


################# Turning simple metadata into VOTable elements.

def _iterInfoInfos(dataSet):
	"""returns a sequence of V.INFO items from the info meta of dataSet.
	"""
	for infoItem in dataSet.getMeta("info", default=[]):
		name, value, id = infoItem.infoName, infoItem.infoValue, infoItem.infoId
		yield V.INFO(name=name, value=value, id=id)[infoItem.getContent()]


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
	if colDesc.has_key("nullvalue"):
		valEl(null=str(colDesc["nullvalue"]))
	return valEl


# keys copied from colDescs to FIELDs in _getFieldFor
_voFieldCopyKeys = ["name", "ID", "datatype", "ucd",
	"utype", "unit"]

def _defineField(element, colDesc):
	"""adds attributes and children to element from colDesc.

	element can be a V.FIELD or a V.PARAM *instance* and is changed in place.

	This function returns None to remind people we're changing in place
	here.
	"""
	# complain if you got an Element rather than an instance -- with an
	# Element, things would appear to work, but changes are lost when
	# this function ends.
	assert not isinstance(element, type)
	element(arraysize=colDesc["arraysize"],
		**dict((key, colDesc.get(key)) for key in _voFieldCopyKeys))[
		_makeValuesForColDesc(colDesc),
		V.DESCRIPTION[colDesc["description"]]]


def _iterFields(serManager):
	"""iterates over V.FIELDs based on serManger's columns.
	"""
	for colDesc in serManager:
		el = V.FIELD()
		_defineField(el, colDesc)
		yield el


def _iterParams(ctx, dataSet):
	"""iterates over the entries in the parameters row of dataSet.
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
		_defineField(el, colDesc)
		yield el


####################### Tables and Resources


def _makeUtypeContainer(serManager, utype, value):
	"""returns a PARAM or FIELDref element serializing the utype, value pair.

	If the value is a ColRef, the result will be a FIELDref.  serManagers
	make up IDs for their constituent fields, so we don't need to worry.
	"""
	if isinstance(value, stc.ColRef):
		return V.FIELDref(utype=utype, ref=serManager.getColDescByName(
			value.dest)["ID"])
	else:
		return V.PARAM(name=utype.split(".")[-1], utype=utype, value=value,
			datatype="char", arraysize="*")


def _iterSTC(tableDef, serManager):
	"""adds STC groups for the systems to votTable fetching data from 
	tableDef.
	"""
	for stcId, ast in tableDef.getSTCSystems(serManager):
		sysTypes, cooTypes = stc.getUtypeGroups(ast)
		yield V.GROUP(utype="stc:AstroCoordSystem", ID=stcId)[
			[_makeUtypeContainer(serManager, utype, value)
				for utype, value in sysTypes]]
		yield V.GROUP(utype="stc:AstroCoords", ref=stcId)[
			[_makeUtypeContainer(serManager, utype, value)
				for utype, value in cooTypes]]


def _makeTable(ctx, table):
	"""returns a Table node for the table.Table instance table.
	"""
	sm = valuemappers.SerManager(table, mfRegistry=ctx.mfRegistry,
		idManager=ctx)
	result = V.TABLE(name=table.tableDef.id)[
		V.DESCRIPTION[base.getMetaText(table.tableDef, "description")],
		_iterSTC(table.tableDef, sm),
		_iterFields(sm)]
	return votable.DelayedTable(result,
		sm.getMappedTuples(),
		tableEncoders[ctx.tablecoding])


def _makeResource(ctx, data):
	"""returns a Resource node for the rsc.Data instance data.
	"""
	res = V.RESOURCE(type=base.getMetaText(data, "_type"))[
		_iterResourceMeta(ctx, data),
		_iterParams(ctx, data)]
	for table in data:
		if table.role!="parameters" and table.tableDef.columns:
			res[_makeTable(ctx, table)]
	return res

############################# Toplevel/User-exposed code


def makeVOTable(ctx, data):
	"""returns a votable.V.VOTABLE object representing data.

	data can be an rsc.Data or an rsc.Table.  You will usually pass
	the result to votable.write.  The object returned contains DelayedTables,
	i.e., most of the content will only be realized at render time.

	ctx is a VOTableContext instance.
	"""
	data = rsc.wrapTable(data)
	vot = V.VOTABLE()
	vot[_iterToplevelMeta(ctx, data)]
	vot[_makeResource(ctx, data)]
	return vot


def writeAsVOTable(data, outputFile, tablecoding="binary"):
	"""a formats.common compliant data writer.

	data can be a data or a table instance, tablecoding any key in
	votable.tableEncoders.

	data can be a Data or Table instance.
	"""
	ctx = VOTableContext(valuemappers.defaultMFRegistry,
		tablecoding=tablecoding)
	vot = makeVOTable(ctx, data)
	votable.write(vot, outputFile)


def getAsVOTable(data, tablecoding="binary"):
	"""returns a string containing a VOTable representation of data.

	This is mainly intended for debugging and "known-small" tables.

	data can be a data or a table instance, tablecoding any key in
	votable.tableEncoders.
	"""
	dest = StringIO()
	writeAsVOTable(data, dest, tablecoding=tablecoding)
	return dest.getvalue()


common.registerDataWriter("votable", writeAsVOTable)
common.registerDataWriter("votabletd", functools.partial(
	writeAsVOTable, tablecoding="td"))