"""
Common interface to table implementations.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import rscdef
from gavo.rsc import common
from gavo.rsc import dbtable
from gavo.rsc import table


def TableForDef(tableDef, suppressIndex=False, 
		parseOptions=common.parseNonValidating, **kwargs):
	"""returns a table instance suitable for holding data described by
	tableDef.

	This is the main interface to table instancation.

	suppressIndex=True can be used to suppress index generation on 
	in-memory tables with primary keys.  Use it when you are sure
	you will not need the index (e.g., if staging an on-disk table).

	See getParseOptions above for parseOptions.
	"""
	if isinstance(tableDef, rscdef.SimpleView):
		tableDef = tableDef.getTableDef()
	if tableDef.onDisk:
		if tableDef.viewStatement:
			cls = dbtable.View
		else:
			cls = dbtable.DBTable
		return cls(tableDef, suppressIndex=suppressIndex, 
			validateRows=parseOptions.validateRows,
			commitAfterMeta=parseOptions.commitAfterMeta,
			tableUpdates=parseOptions.doTableUpdates, **kwargs)
	elif tableDef.forceUnique:
		return table.UniqueForcedTable(tableDef, 
			validateRows=parseOptions.validateRows, **kwargs)
	elif tableDef.primary and not suppressIndex:
		return table.InMemoryIndexedTable(tableDef, 
			validateRows=parseOptions.validateRows, **kwargs)
	else:
		return table.InMemoryTable(tableDef, validateRows=parseOptions.validateRows,
			**kwargs)


