"""
Definitions and shared code for STC processing.
"""

import itertools

from gavo.utils import ElementTree

class STCError(Exception):
	pass

class STCSParseError(Exception):
	"""is raised if an STC-S expression could not be parsed.

	Low-level routines raise a pyparsing ParseException.  Only higher
	level functions raise this error.  The offending expression is in
	the expr attribute, the start position of the offending phrase in pos.
	"""
	def __init__(self, msg, expr=None, pos=None):
		Exception.__init__(self, msg)
		self.pos, self.expr = pos, expr

class STCLiteralError(STCError):
	"""is raised when a literal is not well-formed.

	There is an attribute literal giving the malformed literal.
	"""
	def __init__(self, msg, literal=None):
		Exception.__init__(self, msg)
		self.literal = literal

class STCInternalError(STCError):
	"""is raised when assumptions about the library behaviour are violated.
	"""

class STCValueError(STCError):
	"""is raised when some STC specification is inconsistent.
	"""

class STCNotImplementedError(STCError):
	"""is raised when the current implementation limits are reached.
	"""


STCNamespace = "http://www.ivoa.net/xml/STC/stc-v1.30.xsd"
XlinkNamespace = "http://www.w3.org/1999/xlink"

ElementTree._namespace_map[STCNamespace] = "stc"
ElementTree._namespace_map[XlinkNamespace] = "xlink"


# The following lists have to be updated when the STC standard is
# updated.  They are used for building the STC-X namespace.

# known space reference frames
stcSpaceRefFrames = set(["ICRS", "FK4", "FK5", "ECLIPTIC", "GALACTIC_I",
		"GALACTIC_II", "SUPER_GALACTIC", "AZ_EL", "BODY", "GEO_C", "GEO_D", "MAG",
		"GSE", "GSM", "SM", "HGC", "HGS", "HPC", "HPR", "HEE", "HEEQ", "HGI",
		"HRTN", "MERCURY_C", "VENUS_C", "LUNA_C", "MARS_C", "JUPITER_C_III",
		"SATURN_C_III", "UNKNOWNFrame"])

# known space reference positions
stcRefPositions = set(["TOPOCENTER", "BARYCENTER", "HELIOCENTER", "GEOCENTER",
		"LSR", "LSRK", "LSRD", "GALACTIC_CENTER", "LOCAL_GROUP_CENTER", "MOON",
		"EMBARYCENTER", "MERCURY", "VENUS", "MARS", "JUPITER", "SATURN", "URANUS",
		"NEPTUNE", "PLUTO", "RELOCATABLE", "UNKNOWNRefPos", "CoordRefPos"])

# known flavors for coordinates
stcCoordFlavors = set(["SPHERICAL", "CARTESIAN", "UNITSPHERE", "POLAR", 
	"CYLINDRICAL", "STRING", "HEALPIX"])

# known time scales
stcTimeScales = set(["TT", "TDT", "ET", "TAI", "IAT", "UTC", "TEB", "TDB",
	"TCG", "TCB", "LST", "nil"])


class CachedGetter(object):
	def __init__(self, getter):
		self.cache, self.getter = None, getter
	
	def __call__(self):
		if self.cache is None:
			self.cache = self.getter()
		return self.cache


# Nodes for ASTs

class ASTNodeType(type):
	"""is a metaclass for ASTs.

	The idea is quite similar to the GAVO DC's Structure class, only we keep it
	much simpler: Define children in a class definition and make sure they are
	actually present.
	
	ASTNodes are supposed to be immutable; the are defined during construction.
	Currently, nothing keeps you from changing them afterwards, but that may
	change.

	The classes' constructor is defined to accept all attributes as arguments
	(you probably want to use keyword arguments here).  It is the constructor
	that sets up the attributes, so ASTNodes must not have an __init__ method.
	However, they may define a method _setupNode that is called just before the
	artificial constructor returns.
	
	To define the attributes of the class, add _a_<attname> attributes
	giving a default to the class.  The default should normally be either
	None for 1:1 or 1:0 mappings or an empty tuple for 1:n mappings.
	The defaults must return a repr that constructs them, since we create
	a source fragment.
	"""
	def __init__(cls, name, bases, dict):
		cls._collectAttributes()
		cls._buildConstructor()
	
	def _collectAttributes(cls):
		cls._nodeAttrs = []
		for name in dir(cls):
			if name.startswith("_a_"):
				cls._nodeAttrs.append((name[3:], getattr(cls, name)))
	
	def _buildConstructor(cls):
		argList, codeLines = ["self"], []
		for argName, argDefault in cls._nodeAttrs:
			argList.append("%s=%s"%(argName, repr(argDefault)))
			codeLines.append("  self.%s = %s"%(argName, argName))
		codeLines.append("  self._setupNode()\n")
		codeLines.insert(0, "def constructor(%s):"%(", ".join(argList)))
		ns = {}
		exec "\n".join(codeLines) in ns
		cls.__init__ = ns["constructor"]


class ASTNode(object):
	__metaclass__ = ASTNodeType

	_a_ucd = None
	_a_id = None

	def _setupNode(self):
		pass

	def __repr__(self):
		return "<%s %s>"%(self.__class__.__name__, " ".join(
			"%s=%s"%(name, repr(val))
			for name, val in self.iterAttributes(skipEmpty=True)))

	def iterAttributes(self, skipEmpty=False):
		"""yields pairs of attributeName, attributeValue for this node.
		"""
		for name, _ in self._nodeAttrs:
			val = getattr(self, name)
			if skipEmpty and not val:
				continue
			yield name, val
	
	def iterNodes(self):
		"""iterates the tree preorder.

		Only ASTNodes are returned, not python values.
		"""
		childIterators = []
		for name, value in self.iterAttributes():
			if isinstance(value, ASTNode):
				childIterators.append(value.iterNodes())
			elif isinstance(value, (list,tuple)) and value:
				if isinstance(value[0], ASTNode):
					childIterators.extend(c.iterNodes() for c in value)
		return itertools.chain((self,), *childIterators)
