"""
Writing annotations in RDs.

This module provides the glue between annotations (typically in SIL)
and the rest of the RDs.  It provides the ResAnnotation struct, which
contains the SIL, and the makeAttributeAnnotation function at is a factory
for attribute annotations.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import functools
import itertools

from gavo import base
from gavo.dm import common
from gavo.dm import sil


class SynthesizedRoles(base.Structure):
	"""DM annotation copied and adapted to a new table.

	This is a stand-in for DataModelRoles in tables not parsed from
	XMLs.  Their DM structure is defined through references the columns and
	params make to the annotations their originals had.

	These have no attributes but just arrange for the new annotations
	to be generated.
	"""
	name_ = "_synthesizedRoles"

	def _synthesizeAnnotations(self, rd, ctx):
		annotationMap = {}

		# First, construct a map from column/param annotations in
		# the old annotations to new columns and params.  As a
		# side effect, the dmRoles of the new items are cleared.
		for item in itertools.chain(self.parent.params, self.parent.columns):
			for annotation in item.dmRoles.oldRoles:
				annotationMap[annotation()] = item
			item.dmRoles = []

		# Then, collect the annotations we have to copy
		oldInstances = set(ann.instance() for ann in annotationMap)

		# tell the instances to copy themselves, replacing references
		# accordingly.
		newInstances = []
		for oldInstance in oldInstances:
			newInstances.append(
				oldInstance.copyWithAnnotationMap(
					annotationMap, self.parent, None))
		self.parent.annotations = newInstances

	def completeElement(self, ctx):
		ctx.addExitFunc(self._synthesizeAnnotations)
		self._completeElementNext(SynthesizedRoles, ctx)


class DataModelRoles(base.Structure):
	"""an annotation of a table in terms of data models.

	The content of this element is a Simple Instance Language clause.
	"""

# We defer the parsing of the contained element to (hopefully) the
# end of the parsing of the RD to enable forward references with
# too many headaches (stubs don't cut it: we (may) need to know types).
# 
# There's an additional complication in that we may want to 
# access parsed annotations while parsing other annotations
# (e.g., when processing foreign keys).
# To allow the thing to "parse itself" in such situations, we do
# all the crazy magic with the _buildAnnotation function.
	name_ = "dm"

	_sil = base.DataContent(description="SIL (simple instance language)"
		" annotation.", copyable=True)

	def completeElement(self, ctx):
		def _buildAnnotation():
			try:
				self._parsedAnnotation = sil.getAnnotation(
					self.content_, getAnnotationMaker(self.parent))
				self.parent.annotations.append(self._parsedAnnotation)
			except Exception, ex:
				raise base.ui.logOldExc(base.StructureError(str(ex),
					pos=self.getSourcePosition()))
			self._buildAnnotation = lambda: None
		self._buildAnnotation = _buildAnnotation

		ctx.addExitFunc(lambda rd, ctx: self._buildAnnotation())
		self._completeElementNext(DataModelRoles, ctx)

	def parse(self):
		"""returns a parsed version of the embedded annotation.

		Do not call this while the RD is still being built, as dm
		elements may contain forward references, and these might
		not yet be available during the parse.
		"""
		self._buildAnnotation()
		return self._parsedAnnotation

	def copy(self, newParent, ctx):
		# we use the general mechanism used for recovering annotations from
		# columns and params in tables here so we're independent of
		# changes in columns.
		return SynthesizedRoles(newParent).finishElement(ctx)


def makeAttributeAnnotation(container, instance, attName, attValue):
	"""returns a typed annotation for attValue within container.

	When attValue is a literal, this is largely trivial.  If it's a reference,
	this figures out what it points to and creates an annotation of
	the appropriate type (e.g., ColumnAnnotation, ParamAnnotation, etc).

	container in current DaCHS should be a TableDef or something similar;
	this function expects at least a getByName function and an rd attribute.

	instance is the root of the current annotation.  Complex objects should
	keep a (weak) reference to that.   We don't have parent links in
	our dm trees, and without a reference to the root there's no
	way we can go "up".

	This is usually used as a callback from within sil.getAnnotation and
	expects Atom and Reference instances as used there.
	"""
	if isinstance(attValue, sil.Atom):
		return common.AtomicAnnotation(attName, attValue, instance=instance)
	
	elif isinstance(attValue, sil.Reference):
		# try name-resolving first (resolveId only does id resolving on
		# unadorned strings)
		try:
			res = container.getByName(attValue)
		except base.NotFoundError:
			res = base.resolveId(container.rd, attValue, instance=container)

		if not hasattr(res, "getAnnotation"):
			raise base.StructureError("Element %s cannot be referenced"
				" within a data model."%repr(res))
		
		return res.getAnnotation(attName, container, instance)

	else:
		assert False


def getAnnotationMaker(container):
	"""wraps makeAttributeAnnotationMaker such that names are resolved
	within container.
	"""
	return functools.partial(makeAttributeAnnotation, container)
