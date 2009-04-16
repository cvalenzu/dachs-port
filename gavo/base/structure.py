"""
Representation of structured data deserializable from XML.

We want all the managed attribute stuff since the main user input comes
from resource descriptors, and we want relatively strong input validation
here.  Also, lots of fancy copying and crazy cross-referencing is
going on in our resource definitions, so we want a certain amount of
rigorous structure.  Finally, a monolithic parser for that stuff
becomes *really* huge and tedious, so I want to keep the XML parsing
information in the constructed objects themselves.


Parseables
----------

Parseables are object having a method

feedEvent(ctx, type, name, value=None) -> callable, unicode or None

These process parse events.  ctx is a parse context, basically a container
you can use to communicate parse information (like "make no database
queries" or a map of ids and objects).

type can be:

* value -- causes the feed method on the attribute name to be called.
* start -- returns a new feed receiver for the attribute name.
* end -- returns a new feed receiver for the current attribute's parent.

feedEvent returns either a callable (that be called on the next event
call) or a unicode object name to signify that whatever is being parsed is
atomic and they will expect a feed("value", name, value) for the content
of the element.  If feedEvent returns None it means that the root
element has finished.

You can build feedEvent methods using the Parser class; this make the
whole thing a bit clearer and more robust.


Structures
----------

These contain attribute definitions (shared between all instances) and
attribute values (instance specific).

One hack with them is content addition.  The parser in xmlstruct turns
content on a structure itself into value events with the name of the element
itself.  By default, this will cause an error to be raised.  However,
if a structure has an attribute with a StructureContent value, the content
will be stored as a unicode string in the content attribute.  This is
a bit bad because structures may in this way not have attributes named
like themselves.
"""

import new
import weakref

from gavo import utils
from gavo.base import attrdef
from gavo.base import parsecontext
from gavo.utils.excs import StructureError, Replace, LiteralParseError


class ChangeParser(Exception):
	"""is an exception that can be raised at some point during a parse
	to notify the EventProcessor to change its current parser "out of
	order".

	Again, this is a hack for ref=-Attributes.
	"""
	def __init__(self, newParser):
		Exception.__init__(self, "You should never see this")
		self.newParser = newParser


class RefAttribute(attrdef.AttributeDef):
	"""is an attribute that replaces the current parent with a reference
	to an item coming from the context's idmap.
	
	This is a bit tricky in that whatever is referenced keeps its parent,
	and of course you have all kinds of aliasing nightmares.

	I wouldn't have come up with this mess if it weren't so useful in RDs.

	One could think about stuffing these into R/O proxies, but let's see
	if we're hurting.  Plus, there's OriginalAttribute that doesn't
	have such pitfalls (but is much slower due to copying).

	See parsecontext.OriginalAttribute of a discussion on name.
	"""
	computed_ = True
	typeDesc_ = "id reference"

	def __init__(self, name="ref", description="A reference to another node"
			" that will stand in here.  You cannot add attributes or children"
			" to the element referenced here.  Do not use this unless you know"
			" what you are doing.", forceType=None):
		assert name=='ref'
		attrdef.AttributeDef.__init__(self, name, attrdef.Computed, description)
		self.forceType = forceType

	@property
	def default_(self):
		return None

	def feed(self, ctx, parent, literal):
		if literal is None:
			return
		srcOb = ctx.getById(literal, self.forceType)
		newOb = makeStructureReference(srcOb, parent.parent)
		raise ChangeParser(newOb.feedEvent)

	def getCopy(self, instance, newParent):
		return None  # these have no content


class Parser(object):
	"""is a callable that routes events.

	It is constructed with up to three functions for handling start,
	value, and end events.
	"""
	def __init__(self, start=None, value=None, end=None):
		self.start, self.value, self.end = start, value, end
	
	def __call__(self, ctx, type, name, value):
		if type=="start":
			return self.start(ctx, name, value)
		elif type=="value":
			return self.value(ctx, name, value)
		elif type=="end":
			return self.end(ctx, name, value)
		else:
			raise StructureError("Illegal event type while building: '%s'"%type)


def sortAttrs(attrSeq):
	"""evaluates the before attributes on the AttributeDefs in attrsSeq
	and returns a sequence satisfying them.

	It returns a reference to attrSeq for convenience.
	"""
	beforeGraph = []
	for att in attrSeq:
		if att.before:
			beforeGraph.append((att.name_, att.before))
	if beforeGraph:
		attDict = dict((a.name_, a) for a in attrSeq)
		sortedNames = utils.topoSort(beforeGraph)
		sortedAtts = [attDict[n] for n in sortedNames]
		attrSeq = sortedAtts+list(set(attrSeq)-set(sortedAtts))
	return attrSeq
	

class StructType(type):
	"""is a metaclass for the representation of structured data.

	StructType classes with this will be called structures within
	the DC software.

	Structures do quite a bit of the managed attribute nonsense to
	meaningfully catch crazy user input.

	Basically, you give a Structure class attributes (preferably with
	underscores in front) specifying the attributes the instances
	should have and how they should be handled.

	Structures must be constructed with a parent (for the root
	element, this is None).  All other arguments should be keyword
	arguments.  If given, they have to refer to existing attributes,
	and their values will directly give the the values of the
	attribute (i.e., parsed values).

	Structures should always inherit from StructBase below and
	arrange for its constructor to be called, since, e.g., default
	processing happens there.

	Structures have a managedAttrs dictionary containing names and
	attrdef.AttributeDef objects for the defined attributes.
	"""
	def __init__(cls, name, bases, dict):
		type.__init__(cls, name, bases, dict)
		cls._collectManagedAttrs()
		cls._insertAttrMethods()
	
	def _collectManagedAttrs(cls):
		"""collects a dictionary of managed attributes in managedAttrs.
		"""
		managedAttrs, completedCallbacks, attrSeq = {}, [], []
		for name in dir(cls):
			if not hasattr(cls, name):
				continue
			val = getattr(cls, name)
			if isinstance(val, attrdef.AttributeDef):
				managedAttrs[val.name_] = val
				attrSeq.append(val)
				if hasattr(val, "xmlName_"):
					managedAttrs[val.xmlName_] = val
				if val.aliases:
					for alias in val.aliases:
						managedAttrs[alias] = val
		cls.attrSeq = sortAttrs(attrSeq)
		cls.managedAttrs = managedAttrs
		cls.completedCallbacks = completedCallbacks
	
	def _insertAttrMethods(cls):
		"""adds methods defined by cls's managedAttrs for the parent to
		cls.
		"""
		for val in set(cls.managedAttrs.itervalues()):
			for name, meth in val.iterParentMethods():
				if isinstance(meth, property):
					setattr(cls, name, meth)
				else:
					setattr(cls, name, new.instancemethod(meth, None, cls))


class DataContent(attrdef.UnicodeAttribute):
	"""is a magic attribute that allows character content to be added to
	a structure.
	"""
	typeDesc_ = "string"

	def __init__(self, default="", 
			description="Undocumented", **kwargs):
		attrdef.UnicodeAttribute.__init__(self, "content_", default, 
			description, **kwargs)

	def makeUserDoc(self):
		return ("Character content of the element (defaulting to %s) -- %s"%(
			repr(self.default_), self.description_))


class StructureBase(object):
	"""is a base class for all structures.

	You must arrange for calling its constructor from classes inheriting
	this.

	The constructor receives a parent (another structure, or None)
	and keyword arguments containing values for actual attributes
	(which will be set without any intervening consultation of the
	AttributeDef).

	The attribute definitions talking about structures let you
	set parent to None when constructing default values; they will
	then insert the actual parent.
	"""

	__metaclass__ = StructType

	name_ = attrdef.Undefined

	_id = parsecontext.IdAttribute("id", 
		description="Node identity for referencing")

	def __init__(self, parent, **kwargs):
		self.parent = parent
		
		# set defaults
		for val in self.attrSeq:
			try:
				if not hasattr(self, val.name_): # don't clobber properties
						# set up by attributes.
					setattr(self, val.name_, val.default_)
			except AttributeError: # default on property given
				raise StructureError("%s attributes have builtin defaults only."%
					val.name_)
		
		# set keyword arguments
		for name, val in kwargs.iteritems():
			if name in self.managedAttrs:
				if not hasattr(self.managedAttrs[name], "computed_"):
					self.managedAttrs[name].feedObject(self, val)
			else:
				raise StructureError("%s objects have no attribute %s"%(
					self.__class__.__name__, name))


	def getAttributes(self, attDefsFrom=None):
		"""returns a dict of the current attributes, suitable for making
		a shallow copy of self.

		Struct attributes will not be reparented, so there are limits to
		what you can do with such shallow copies.
		"""
		if attDefsFrom is None:
			attrs = set(self.managedAttrs.values())
		else:
			attrs = set(attDefsFrom.managedAttrs.values())
		try:
			return dict([(att.name_, getattr(self, att.name_))
				for att in attrs])
		except AttributeError, msg:
			raise StructureError("Attempt to copy from invalid source: %s"%
				unicode(msg))
					

	def copy(self, parent):
		"""returns a deep copy of self, reparented to parent.
		"""
		return self.__class__(parent, 
			**dict([(att.name_, att.getCopy(self, None))
				for att in self.attrSeq
					if att.copyable])).finishElement()

	def replace(self, newObject):
		"""tries to locate self in parent and replaces it with newObject.

		This is a bit hapazard since we assume the parent has an attribute
		of our name.  This should normally be the case, but there are no
		guarantees.  So, this might fail.  It's not that bad, though, since
		we mainly need this for ref=-type attributes.
		"""
		self.parent.managedAttrs[self.name_].replace(self.parent, self, newObject)
		newObject.parent = self.parent
	
	def adopt(self, struct):
		struct.parent = self
		return struct

	def iterChildren(self):
		"""iterates over structure children of self.

		To make this work, attributes containing structs must define
		iterStructs methods (and the others must not).
		"""
		for att in self.attrSeq:
			if hasattr(att, "iterChildren"):
				for c in att.iterChildren(self):
					yield c

	@classmethod
	def fromStructure(cls, newParent, oldStructure):
		consArgs = dict([(att.name_, getattr(oldStructure, att.name_))
			for att in oldStructure.attrSeq])
		return cls(newParent, **consArgs)


class ParseableStructure(StructureBase):
	"""is a base class for Structures parseable from EventProcessors (and
	thus XML).
	
	This is still abstract in that you need at least a name_ attribute.
	But it knows how to be fed from a parser, plus you have feed and feedObject
	methods that look up the attribute names and call the methods on the
	respective attribute definitions.
	"""
	def __init__(self, parent, **kwargs):
		StructureBase.__init__(self, parent, **kwargs)
		self.feedEvent = Parser(self._doStart, self._doValue, self._doEnd)

	def finishElement(self):
		return self

	def getDynamicAttribute(self, name):
		"""returns an AttributeDef for name or None.

		The function is only called for names not already present in 
		managedAttributes.

		This is intended for polymorphic attributes that can't go the registry-type
		way (e.g., grammar attribute on data descriptors).

		The AttributeDef returned *must* be entered into managedAttributes
		unless you insist on chaos.

		If this method returns None, the unknown name will raise an error.
		"""

	def _doEnd(self, ctx, name, value):
		try:
			self.finishElement()
		except Replace, ex:
			self.parent.feedObject(name, ex.args[0])
		else:
			if self.parent:
				self.parent.feedObject(name, self)
		# del self.feedEvent (at some point we might selectively reclaim parsers)
		return getattr(self.parent, "feedEvent", None)

	def _doValue(self, ctx, name, value):
		if not name in self.managedAttrs:
			if name=="content_":
				raise StructureError("%s elements must not have character data"
					" content (found '%s')"%(self.name_, 
						utils.makeEllipsis(value, 20)))
			raise StructureError(
				"%s elements have no %s attributes"%(self.name_, name))
		try:
			self.managedAttrs[name].feed(ctx, self, value)
		except Replace, ex:
			return ex.args[0].feedEvent
		return self.feedEvent
	
	def _doStart(self, ctx, name, value):
		if not name in self.managedAttrs:
			attDef = self.getDynamicAttribute(name)
			if not attDef:
				raise StructureError(
					"%s objects cannot have %s children"%(self.__class__.__name__, name))
		else:
			attDef = self.managedAttrs[name]
		if isinstance(attDef, attrdef.AtomicAttribute):
			return name
		else:
			return attDef.create(self, name).getParser(self)

	def getParser(self, parent):
		if hasattr(self, "feedEvent"):
			return self.feedEvent
		raise StructureError("%s element was asked for a parser after"
			" parsing."%self.name_)

	def feed(self, name, literal, ctx=None):
		"""feeds the literal to the attribute name.

		If you do not have a proper parse context ctx, so there
		may be restrictions on what literals can be fed.
		"""
		self.managedAttrs[name].feed(ctx, self, literal)
	
	def feedObject(self, name, ob):
		"""feeds the object ob to the attribute name.
		"""
		self.managedAttrs[name].feedObject(self, ob)

	def iterEvents(self):
		"""yields an event sequence that transfers the copyable information
		from self to something receiving the events.

		If something is copyable or not is specified by the AttributeDefinition.
		"""
		for att in self.attrSeq:
			if not att.copyable:
				continue
			if hasattr(att, "iterEvents"):
				for ev in att.iterEvents(self):
					yield ev
			else:
				val = getattr(self, att.name_)
				if val!=att.default_:  
					yield ("value", att.name_, att.unparse(val))

	def feedFrom(self, other, ctx=None, suppress=set()):
		"""feeds parsed objects from another structure.

		This only works if the other structure is a of the same or a superclass
		of self.

		This is mainly intended to be used by mixins.
		"""
		if ctx is None:
			ctx = parsecontext.ParseContext()
		evProc = EventProcessor(None, ctx)
		evProc.setRoot(self)
		for ev in other.iterEvents():
			evProc.feed(*ev)


class Structure(ParseableStructure):
	"""is the base class for user-defined structures.

	It will do some basic validation and will call hooks to complete elements
	and compute computed attributes, based on ParseableStructure's finishElement
	hook.

	Also, it supports onParentCompleted callbacks; this works by checking
	if any managedAttribute has a onParentCompleted method and calling it
	with the current value of that attribute if necessary.
	"""
	def callCompletedCallbacks(self):
		for attName, attType in self.managedAttrs.iteritems():
			if hasattr(attType, "onParentCompleted"):
				attVal = getattr(self, attType.name_)
				if attVal!=attType.default_:
					attType.onParentCompleted(attVal)

	def finishElement(self):
		self.completeElement()
		self.validate()
		self.onElementComplete()
		self.callCompletedCallbacks()
		return self

	def _makeUpwardCaller(methName):
		def _callNext(self, cls):
			try:
				pc = getattr(super(cls, self), methName)
			except AttributeError:
				pass
			else:
				pc()
		return _callNext

	def completeElement(self):
		self._completeElementNext(Structure)

	_completeElementNext = _makeUpwardCaller("completeElement")

	def validate(self):
		for val in set(self.managedAttrs.itervalues()):
			if getattr(self, val.name_) is attrdef.Undefined:
				raise StructureError("You must set %s on %s elements"%(
					val.name_, self.name_))
			if hasattr(val, "validate"):
				val.validate(self)
		self._validateNext(Structure)

	_validateNext = _makeUpwardCaller("validate")

	def onElementComplete(self):
		self._onElementCompleteNext(Structure)

	_onElementCompleteNext = _makeUpwardCaller("onElementComplete")


def makeStructureReference(aStruct, parseParent):
	"""returns a root structure having references of aStruct's attributes but
	raising errors on feedEvent attempts.

	parseParent is the structure that receives the new structure and
	keeps on parsing.

	This is used for ref=-attributes to make sure they are not changed
	from within XML (since that would change the original.  Programmatic
	manipulations still remain possible, and the effort to foil those
	is probably not worth it.
	"""
	newStruct = aStruct.__class__.fromStructure(None, aStruct)
	def doEnd(ctx, name, value):
		parseParent.feedObject(name, newStruct)
		return parseParent.feedEvent
	def raiseError(ctx, name, value):
		raise StructureError("Referenced elements cannot have attributes"
			" or children")
	newStruct.feedEvent = Parser(raiseError, raiseError, doEnd)
	newStruct.finishElement()
	return newStruct


def makeStruct(structClass, **kwargs):
	"""creates a parentless instance of structClass with **kwargs, going
	through all finishing actions.
	"""
	parent = None
	if "parent_" in kwargs:
		parent = kwargs.pop("parent_")
	res = structClass(parent, **kwargs).finishElement()
	return res


class Generator(Parser):
	"""is an event generator created from python source code embedded
	in an XML element.
	"""
	def __init__(self, parent):
		nextParser = parent.curParser
		self.code = ""
		def start(ctx, name, value):
			raise StructureError("GENERATORs have no children")
		def value(ctx, name, value):
			if name!="content_":
				raise StructureError("GENERATORs have no children")
			self.code = parent.rootStruct.expand(("def gen():\n"+value).rstrip())
			return self
		def end(ctx, name, value):
			vals = {"context": ctx}
			try:
				exec self.code in vals
			except Exception, msg:
				raise LiteralParseError("Invalid code in generator (%s)"%
					unicode(msg), "GENERATOR", self.code)
			for ev in vals["gen"]():
				if ev[0]=="element":
					self._expandElementEvent(ev, parent)
				elif ev[0]=="values":
					self._expandValuesEvent(ev, parent)
				else:
					parent.eventQueue.append(ev)
			return nextParser
		Parser.__init__(self, start, value, end)
	
	def _expandElementEvent(self, ev, parent):
		parent.eventQueue.append(("start", ev[1]))
		for key, val in ev[2:]:
			parent.eventQueue.append(("value", key, val))
		parent.eventQueue.append(("end", ev[1]))

	def _expandValuesEvent(self, ev, parent):
		for key, val in ev[1:]:
			parent.eventQueue.append(("value", key, val))


class EventProcessor(object):
	"""is a dispatcher for parse events to structures.

	It is constructed with the root structure of the result tree, either
	as a type or as an instance.

	After that, events can be fed to the feed method that makes sure
	they are routed to the proper object.
	"""

# The event processor distinguishes between parsing atoms (just one
# value) and structured data using the next attribute.  If it is not
# None, the next value coming in will be turned to a "value" event
# on the current parser.  If it is None, we hand through the event
# to the current structure.

	def __init__(self, rootStruct, ctx):
		self.rootStruct = rootStruct
		self.curParser, self.next = self._parse, None
		self.result, self.ctx = None, ctx
		# a queue of events to replay after the current structured
		# element has been processed
		self.eventQueue = []

	def _processEventQueue(self):
		while self.eventQueue:
			self.feed(*self.eventQueue.pop(0))

	def _feedToAtom(self, type, name, value):
		if type=='start':
			raise StructureError("%s elements cannot have %s children"%(
				self.next, name))
		elif type=='value' or type=="parsedvalue":
			self.curParser(self.ctx, 'value', self.next, value)
		elif type=='end':
			self.next = None

	def _feedToStructured(self, type, name, value):
		next = self.curParser(self.ctx, type, name, value)
		if isinstance(next, basestring):
			self.next = next
		else:
			self.curParser = next
		if type=="end":
			self._processEventQueue()

	def feed(self, type, name, value=None):
		"""feeds an event.

		This is the main entry point for user calls.
		"""
		if type=="start" and name=="GENERATOR":
			self.curParser = Generator(self)
			return
		try:
			if self.next is None:
				self._feedToStructured(type, name, value)
			else:
				self._feedToAtom(type, name, value)
		except ChangeParser, ex:
			self.curParser = ex.newParser
	
	def _parse(self, ctx, evType, name, value):
		"""dispatches an event to the root structure.

		Do not call this yourself unless you know what you're doing.  The
		method to feed "real" events to is feed.
		"""
		if name!=self.rootStruct.name_:
			raise StructureError("Expected root element %s, found %s"%(
				self.rootStruct.name_, name))
		if evType=="start":
			if isinstance(self.rootStruct, type):
				self.result = self.rootStruct(None)
			else:
				self.result = self.rootStruct
			self.result.idmap = ctx.idmap
			return self.result.feedEvent
		else:
			raise StructureError("Bad document structure")
	
	def setRoot(self, root):
		"""artifically inserts an instanciated root element.

		This is only required in odd cases like structure.feedFrom
		"""
		self.result = root
		self.curParser = root.feedEvent
		self.result.idmap = self.ctx.idmap
	
	def notifyPosition(self, line, col):
		"""tells the processor a "last known position".

		xmlstruct does this when ending elements, since that's when all
		the validators run.  Unfortunately, for those, the sax parser
		usually doesn't give locations, so we use this hack.
		"""
		self.ctx.lastRow = line
		self.ctx.lastCol = col
