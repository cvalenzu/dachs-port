"""
A simplified API to single-table VOTables.

The basic idea is: open(...) -> (table, metadata),

where table is a numpy array.
"""

import numpy
from numpy import rec

from gavo.votable import parser
from gavo.votable.model import VOTable as V


# map from VOTable datatypes to numpy type designators:
numpyType = {
	"short": numpy.int16,
	"int": numpy.int32,
	"long": numpy.int64,
	"float": numpy.float32,
	"double": numpy.float64,
	"boolean": numpy.bool,
	"char": str,
	"floatComplex": numpy.complex64,
	"doubleComplex": numpy.complex128,
	"unsignedByte": numpy.uint8,
	"unicodeChar": numpy.unicode_
}


class TableMetadata(object):
	"""Metadata for a VOTable table instance, i.e., column definitions, groups,
	etc.

	These are constructed with a VOTable TABLE instance.
	"""
	def __init__(self, tableElement):
		self.votTable = tableElement
		self.fields = list(tableElement.iterChildrenOfType(V.FIELD))
# ... do stuff ...

	def __iter__(self):
		return iter(self.fields)
	
	def __len__(self):
		return len(self.fields)
	
	def __getitem__(self, index):
		return self.fields[index]


def makeDtype(tableMetadata):
	"""returns an record array datatype for a given table metadata.
	"""
	dtypes = []
	seen = set()
	for f in tableMetadata:
		name = f.getDesignation().encode('ascii', 'ignore')
		while name in seen:
			name = name+"_"
		seen.add(name)
		shape = f.getShape()
		if shape is None:
			dtypes.append((name, numpyType[f.a_datatype]))
		else:
			dtypes.append((
				name,
				numpyType[f.a_datatype],
				shape))
	return dtypes


def load(source):
	"""returns (data, metadata) from the first table of a VOTable.

	data is a list of records (as a list), metadata a TableMetadata instance.

	source can be a string that is then interpreted as a local file name,
	or it can be a file-like object.
	"""
	if isinstance(source, basestring):
		source = file(source)
	rows = None
	for rows in parser.parse(source):
		break
	if rows is None: # No table included
		return None, None
	fields = TableMetadata(rows.tableDefinition)
	return list(rows), fields