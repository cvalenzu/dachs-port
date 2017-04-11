"""
The specialised annotations for the various entities of VO-DML.

As it's needed for the definition of models, the annotation of immediate
atoms is already defined in common; also see there for the base class
of these.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


# topnote[1]: copying TableRelativeAnnotations is probably not useful in
# the typical case; when you copy an annotation, that's probably because
# you copied a table, and hence your columns and params are different
# from the original table.  When copying the annotations, they will
# still point to the old instances.  Still, for consistency, I'm
# implementing the copy methods here.


import weakref

from gavo.dm import common
from gavo.votable import V


class ColumnAnnotation(common.TableRelativeAnnotation):
	"""An annotation of a table column.

	These reference DaCHS columns.
	"""
	def __init__(self, name, column, instance):
		common.TableRelativeAnnotation.__init__(self, name, instance)
		self.weakref = weakref.ref(column)
		column.dmRoles.append(weakref.ref(self))

	@property
	def value(self):
		return self.weakref()

	def copy(self, newInstance):
		# see topnote(1)
		return self.__class__(self.name, self.weakref(), newInstance)

	def getVOT(self, ctx, instance):
		return V.COLUMN(ref=ctx.getOrMakeIdFor(self.value))


class ParamAnnotation(common.TableRelativeAnnotation):
	"""An annotation of a table param.

	NOTE: in getVOT, container MUST be the table itself, as the table has
	params of its own and does *not* share tableDef's one.
	"""
	def __init__(self, name, param, instance):
		common.TableRelativeAnnotation.__init__(self, name, instance)
		self.weakref = weakref.ref(param)
		param.dmRoles.append(weakref.ref(self))

	@property
	def value(self):
		return self.weakref()

	def copy(self, newInstance):
		# see topnote(1)
		return self.__class__(self.name, self.weakref(), newInstance)

	def getVOT(self, ctx, container):
		referenced = container.getParamByName(self.value.name)
		res = V.CONSTANT(ref=ctx.getOrMakeIdFor(referenced))
		return res


def _the(gen):
	"""returns the first thing the generator gen spits out and makes sure 
	there's nothing more
	"""
	res = gen.next()
	try:
		extra = gen.next()
	except StopIteration:
		return res
	raise TypeError("Generator expected to only return one thing returned"
		" extra %s"%repr(extra))


class GroupRefAnnotation(common.TableRelativeAnnotation):
	"""An annotation always referencing a group that's not lexically
	within the parent.
	"""
	def __init__(self, name, objectReferenced, instance):
		common.TableRelativeAnnotation.__init__(self, name, instance)
		self.objectReferenced = objectReferenced

	def copy(self, newInstance):
		# see topnote(1)
		return self.__class__(self.name, self.objectReferenced, newInstance)

	def getVOT(self, ctx, instance):
		if id(self.objectReferenced) not in ctx.groupIdsInTree:
			ctx.getEnclosingContainer()[
				_the(# fix this: dmvot.getSubtrees(ctx, self.objectReferenced))(
					ID=ctx.getOrMakeIdFor(self.objectReferenced))]
			ctx.groupIdsInTree.add(id(self.objectReferenced))

		return V.REFERENCE[
			V.IDREF[ctx.getIdFor(self.objectReferenced)]]


class ForeignKeyAnnotation(common.TableRelativeAnnotation):
	"""An annotation pointing to an annotation in a different table.

	These are constructed with the attribute name and the foreign key RD
	object.
	"""
	def __init__(self, name, fk, instance):
		common.TableRelativeAnnotation.__init__(self, name, instance)
		self.value = weakref.proxy(fk)

	def copy(self, newInstance):
		return self.__class__(self.name, self.value, newInstance)

	def getVOT(self, ctx, instance):
		# the main trouble here is: What if there's multiple foreign keys
		# into destTD?  To prevent multiple inclusions of a single
		# table, we add a reference to our serialised VOTable stan in
		# destTD's _FKR_serializedVOT attribute.  That will fail
		# if we produce two VOTables from the same table at the same time,
		# but let's worry about that later.
		
		destTD = self.value.inTable
		srcTD = self.value.parent

		raise NotImplementedError("Do not know how to annotate a foreign key")
		pkDecl = V.GROUP(dmrole="vo-dml:ObjectTypeInstance.ID")[[
			V.FIELDref(ref=ctx.getOrMakeIdFor(
					destTD.tableDef.getColumnByName(colName)))
				for colName in self.foreignKey.dest]]
		pkDecl(ID=ctx.getOrMakeIdFor(pkDecl))

		fkDecl = V.GROUP(ref=ctx.getOrMakeIdFor(pkDecl),
			dmtype="vo-dml:ORMReference")[
			[V.FIELDref(ref=ctx.getIdFor(srcTD.getColumnByName(colName)))
				for colName in self.foreignKey.source]]

		targetVOT = getattr(destTD, "_FKR_serializedVOT",
			lambda: None)()
		# weakrefs are None if expired
		if targetVOT is None:
			targetVOT = ctx.makeTable(destTD)
			destTD._FKR_serializedVOT = weakref.ref(targetVOT)
			ctx.getEnclosingResource()[targetVOT]
		
		targetVOT[pkDecl]

		return fkDecl
