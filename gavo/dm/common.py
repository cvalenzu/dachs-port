"""
Common code for new-style Data Model support.

In particular, this defines a hierachy of Annotation objects.  The annotation
of DaCHS tables is an ObjectAnnotation, the other Annotation classes
(conceptually, all are key-value pairs) make up their inner structure.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import contextlib
import re
import weakref

from gavo import utils
from gavo import votable
from gavo.votable import V


VODML_NAME = "vo-dml"


@contextlib.contextmanager
def containerTypeSet(ctx, typeName):
	"""a context manager to control the type currently serialised in a VOTable.
	
	ctx is a VOTable serialisation context (that we liberally hack into).
	"""
	if not hasattr(ctx, "_dml_typestack"):
		ctx._dml_typestack = []
	ctx._dml_typestack.append(typeName)
	try:
		yield
	finally:
		ctx._dml_typestack.pop()


def completeVODMLId(ctx, roleName):
	"""completes roleName to a full (standard) vo-dml id.

	This is based on what the containerTypeSet context manager leaves
	in the VOTable serialisation context ctx.
	"""
	return roleName

# current spec wants hierarchical strings here.  Let's not.
	if ":" in roleName:
		# we allow the use of fully qualified role names and don't touch them
		return roleName
	return "%s.%s"%(ctx._dml_typestack[-1], roleName)


def parseTypeName(typename):
	"""returns modelname, package (None for the empty package), name
	for a VO-DML type name.

	Malformed names raise a ValueError.

	>>> parseTypeName("dm:type")
	('dm', None, 'type')
	>>> parseTypeName("dm:pck.type")
	('dm', 'pck', 'type')
	>>> parseTypeName(":malformed.typeid")
	Traceback (most recent call last):
	ValueError: ':malformed.typeid' is not a valid VO-DML type name
	"""
	mat = re.match("([\w_-]+):(?:([\w_-]+)\.)?([\w_-]+)", typename)
	if not mat:
		raise ValueError("'%s' is not a valid VO-DML type name"%typename)
	return mat.groups()


class AnnotationBase(object):
	"""A base class for of structs.

	Basically, these are pairs of a role name and something else, which
	depends on the actual subclass (e.g., an atomic value, a reference,
	a sequence of key-value pairs, a sequence of other objects, ...).

	They have a method getVOT(ctx, instance) -> xmlstan, which, using a
	votablewrite.Context ctx, will return mapping-document conformant VOTable
	xmlstan; instance is the rsc/rscdef structure the annotation is produced
	for.

	Use asSIL() to retrieve a simple string representation.

	Compund annotations (sequences, key-value pairs) should use
	add(thing) to build themselves up.

	AnnotationBase is abstract and doesn't implement some of these methods.
	"""
	def __init__(self, name, instance):
		self.name = name
		if instance is None: # should only be true for the root
			self.instance = instance
		else:
			self.instance = weakref.ref(instance)

	def getVOT(self, ctx, instance):
		raise NotImplementedError("%s cannot be serialised (override getVOT)."%
			self.__class__.__name__)

	def asSIL(self):
		raise NotImplementedError("%s cannot be serialised (override asSIL)."%
			self.__class__.__name__)

	def add(self, thing):
		raise ValueError(
			"%s is not a compound annotation."%self.__class__.__name__)

	def iterNodes(self):
		yield self


class TableRelativeAnnotation(AnnotationBase):
	"""A base class for annotations that must be adapted or discarded when 
	an annotation is copied.
	"""
	# This currently is only used as a sentinel for such annotations.
	# Perhaps we should modify copy here?


class AtomicAnnotation(AnnotationBase):
	"""An annotation of an atomic value, i.e., a key-value pair.

	These can take optional metadata.
	"""
	def __init__(self, name=None, value=None, unit=None, 
			ucd=None, instance=None):
		AnnotationBase.__init__(self, name, instance)
		self.value, self.unit, self.ucd = value, unit, ucd

	def copy(self, newInstance):
		return self.__class__(
			self.name, self.value, self.unit, self.ucd, 
			newInstance)

	def getVOT(self, ctx, instance):
		# if we have additional metadata, serialise this using a param
		if self.unit or self.ucd:
			attrs = votable.guessParamAttrsForValue(self.value)
			attrs.update({
				"unit": self.unit,
				"ucd": self.ucd})

			param = V.PARAM(name=self.name,
				id=ctx.getOrMakeIdFor(self.value), 
					dmrole=completeVODMLId(ctx, self.name),
					**attrs)
			ctx.getEnclosingContainer()[
				votable.serializeToParam(param, self.value)]
			return V.CONSTANT(ref=param.id)

		else:
			# no additional metadata, just dump a literal string
			# (technically, we should use ivoa: types.  Oh, bother, another
			# type system, just what we need).
			return V.LITERAL(dmtype="ivoa:string")[
				utils.safe_str(self.value)]


	def asSIL(self, suppressType=False):
		if suppressType:
			return self.value.asSIL()
		else:
			return "%s: %s"%(self.name, self.value.asSIL())


class _WithMapCopyMixin(object):
	"""A mixin furnishing a class with a copyWithAnnotationMap method.

	The class mixing this in must provide an iterator iterChildRoles
	yielding child annotations one by one.

	Every compound annotation must mix this in in order to provide
	halfway sane copying semantics when columns get re-mixed in new
	tables (which we do all the time).

	We also expect a method copyEmpty(i) that returns an instance of the
	Annotation but without any child annotations.

	In return, this will furnish a copy(i) method based on copyEmpty
	and iterChildRoles.
	"""
	def copyWithAnnotationMap(self, annotationMap, container, instance):
		"""returns a copy of this annotation, with annotations mentioned
		in annotationMap replaced.

		Table-related annotations (currently, Param- and ColumnAnnotations)
		not mentioned in annotationMap) will be discarded.

		This is used when annotation tables with columns copied from
		other tables.  annotationMap, normally generated by 
		dmrd.SynthesizedRoles, then maps the old annotations to the elements
		that should be annotated in the new table.
		"""
		copy = self.copyEmpty(instance)
		if instance is None: # I'm the new root 
			instance = copy

		for role in self.iterChildRoles():
			
			if role in annotationMap:
				copy.add(
					annotationMap[role].getAnnotation(
						role.name, container, instance))
			
			elif isinstance(role, TableRelativeAnnotation):
				pass

			elif hasattr(role, "copyWithAnnotationMap"):
				copy.add(role.copyWithAnnotationMap(
					annotationMap, container, instance))

			else:
				copy.add(role.copy(instance))

		return copy

	def copy(self, newInstance):
		return self.copyWithAnnotationMap({}, None, newInstance)


class _AttributeGroupAnnotation(AnnotationBase, _WithMapCopyMixin):
	"""An internal base class for DatatypeAnnotation and ObjectAnnotation.
	"""
	def __init__(self, name, type, instance):
		AnnotationBase.__init__(self, name, instance)
		self.type = type
		if self.type is None:
			# TODO: infer from parent?  from DM?
			self.modelPrefix = getattr(instance, "modelPrefix", "undefined")
		else:
			self.modelPrefix, _, _ = parseTypeName(self.type)

		self.childRoles = {}

	def __getitem__(self, key):
		child = self.childRoles.__getitem__(key)
		if isinstance(child, AtomicAnnotation):
			return child.value
		else:
			return child
	
	def __contains__(self, key):
		return key in self.childRoles

	def copyEmpty(self, newInstance):
		return self.__class__(self.name, self.type, newInstance)

	def iterChildRoles(self):
		return self.childRoles.itervalues()

	def add(self, role):
		assert role.name not in self.childRoles
		self.childRoles[role.name] = role

	def asSIL(self, suppressType=False):
		if suppressType or self.type is None:
			typeAnn = ""
		else:
			typeAnn = "(%s) "%self.type

		return "%s{\n  %s}\n"%(typeAnn,
			"\n  ".join(r.asSIL() for r in self.childRoles.values()))

	def getVOT(self, ctx, instance):
		"""helps getVOT.
		"""
		ctx.addVODMLPrefix(self.modelPrefix)
		ctx.groupIdsInTree.add(id(self))
		res = V.INSTANCE(
				dmtype=self.type,
				ID=ctx.getOrMakeIdFor(self))
		
		for role, ann in self.childRoles.iteritems():
			res[V.ATTRIBUTE(dmrole=completeVODMLId(ctx, role))[
					ann.getVOT(ctx, instance)]]

		return res

class DatatypeAnnotation(_AttributeGroupAnnotation):
	"""An annotation for a datatype.

	Datatypes are essentially simple groups of attributes; they are used
	*within* objects (e.g., to group photometry points, or positions, or
	the like.
	"""


class ObjectAnnotation(_AttributeGroupAnnotation):
	"""An annotation for an object.

	Objects are used for actual DM instances.  In particular,
	every annotation of a DaCHS table is rooted in an object.
	"""


class CollectionAnnotation(AnnotationBase, _WithMapCopyMixin):
	"""A collection contains 0..n things of the same type.
	"""
	def __init__(self, name, type, instance):
		AnnotationBase.__init__(self, name, instance)
		self.type = type
		# these can have atomic children, in which case we don't manage types
		if self.type is not None:
			self.modelPrefix, _, _ = parseTypeName(type)
		self.children = []

	def __getitem__(self, index):
		child = self.children[index]
		if isinstance(child, AtomicAnnotation):
			return child.value
		else:
			return child

	def __len__(self):
		return len(self.children)

	def iterChildRoles(self):
		return iter(self.children)

	def copyEmpty(self, newInstance):
		return self.__class__(self.name, self.type, newInstance)

	def add(self, child):
		self.children.append(child)
	
	def asSIL(self):
		if self.type is None:
			opener = "["
		else:
			opener = "(%s) ["%(self.type,)

		bodyItems = []
		for r in self.children:
			bodyItems.append(r.asSIL(suppressType="True"))

		return "%s: \n  %s%s]\n"%(
			self.name,
			opener,
			"\n  ".join(bodyItems))

	def getVOT(self, ctx, instance):
# So... it's unclear at this point what to do here -- I somehow feel
# we should serialise collections into a table.  But then this would
# entail one table each whenever an attribute is potentially sequence-valued,
# and that doesn't seem right either.  So, we'll dump multiple things
# into one attribute for now and see how far we get with than.
		if self.type:
			ctx.addVODMLPrefix(self.modelPrefix)
		return [c.getVOT(ctx, instance) for c in self.children]

	
def _test():
	import doctest, common
	doctest.testmod(common)


if __name__=="__main__":
	_test()
