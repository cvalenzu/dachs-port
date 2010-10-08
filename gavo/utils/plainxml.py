"""
Some XML hacks.

StartEndHandler simplifies the creation of SAX parsers, intended for 
client code or non-DC XML parsing.

iterparse is an elementtree-inspired thin expat layer; both VOTable
and base.structure parsing builds on it.
"""

import collections
import weakref
import xml.sax
from xml.parsers import expat
from xml.sax.handler import ContentHandler

from gavo.utils import excs
from gavo.utils import misctricks

class ErrorPosition(object):
	"""A wrapper for an error position.

	Construct it with file name, line number, and column.  Use None
	for missing or unknown values.
	"""
	fName = None
	def __init__(self, fName, line, column):
		self.line = line or '?'
		self.col = column
		if self.col is None: 
			self.col = '?'
		self.fName = fName
	
	def __str__(self):
		if self.fName:
			return "%s, (%s, %s)"%(self.fName, self.line, self.col)
		else:
			return "(%s, %s)"%(self.line, self.col)


class iterparse(object):
	"""iterates over start, data, and end events in source.

	To keep things simple downstream, we swallow all namespace prefix,
	if present.

	iterparse is constructed with a source (anything that can read(source))
	and optionally a custom error class.  This error class needs to
	have the message as the first argument.  Since expat error messages
	usually contain line number and column in them, no extra pos attribute
	is supported.

	Since the parser typically is far ahead of the events seen, we
	do our own bookkeeping by storing the parser position with each
	event.  The *end* of the construct that caused an event can
	be retrieved using pos.
	"""
	chunkSize = 2**20
	"The number of bytes handed to expat from iterparse at one go."

	def __init__(self, source, parseErrorClass=excs.StructureError):
		self.source = source
		self.parseErrorClass = parseErrorClass
		self.inputName = getattr(source, "name", None)
		self.parser = expat.ParserCreate()
		self.parser.buffer_text = True
		self.lastLine, self.lastColumn = 1, 0
		# We want ordered attributes for forcing attribute names to be
		# byte strings.
		self.parser.returns_unicode = True
		self.evBuf = collections.deque()
		self.parser.StartElementHandler = (lambda name, attrs, buf=self.evBuf: 
			buf.append((("start", name.split(":")[-1], attrs), 
				(self.parser.CurrentLineNumber, self.parser.CurrentColumnNumber))))
		self.parser.EndElementHandler = (lambda name, buf=self.evBuf: 
			buf.append((("end", name.split(":")[-1], None),
				(self.parser.CurrentLineNumber, self.parser.CurrentColumnNumber))))
		self.parser.CharacterDataHandler = (lambda data, buf=self.evBuf:
			buf.append((("data", None, data), None)))

	def __iter__(self):
		return self

	def next(self):
		if not self.evBuf:
			try:
				nextChunk = self.source.read(self.chunkSize)
				if not nextChunk:
					self.close()
					raise StopIteration("File is exhausted")
				self.parser.Parse(nextChunk)
			except expat.ExpatError, ex:
				newEx = self.parseErrorClass(ex.message)
				newEx.posInMsg = True  # see base.xmlstruct
				raise misctricks.logOldExc(newEx)
			if not self.evBuf:
				raise self.getParseError("Permature end of input.")
		event, pos = self.evBuf.popleft()
		if pos is not None:
			self.lastLine, self.lastColumn = pos
		return event

	def close(self):
		self.parser.Parse("", True)

	@property
	def pos(self):
		return ErrorPosition(self.inputName, self.lastLine, self.lastColumn)

	def getParseError(self, msg):
		res = self.parseErrorClass("At %s: %s"%(self.pos, msg))
		res.posInMsg = True # see base.xmlstruct
		return res


class StartEndHandler(ContentHandler):
	"""This class provides startElement, endElement and characters
	methods that translate events into method calls.

	When an opening tag is seen, we look of a _start_<element name>
	method and, if present, call it with the name and the attributes. 
	When a closing tag is seen, we try to call _end_<element name> with
	name, attributes and contents.	If the _end_xxx method returns a
	string (or similar), this value will be added to the content of the
	enclosing element.

	Rather than overriding __init__, you probably want to override
	the _initialize() method to create the data structures you want
	to fill from XML.
	"""
	def __init__(self):
		ContentHandler.__init__(self)
		self.realHandler = weakref.proxy(self)
		self.elementStack = []
		self.contentsStack = [[]]
		self._initialize()

	def _initialize(self):
		pass

	def processingInstruction(self, target, data):
		self.contentsStack[-1].append(data)

	def cleanupName(self, name):
		return name.split(":")[-1].replace("-", "_")

	def startElement(self, name, attrs):
		self.contentsStack.append([])
		name = self.cleanupName(name)
		self.elementStack.append((name, attrs))
		if hasattr(self.realHandler, "_start_%s"%name):
			getattr(self.realHandler, "_start_%s"%name)(name, attrs)
		elif hasattr(self, "_defaultStart"):
			self._defaultStart(name, attrs)

	def endElement(self, name, suppress=False):
		contents = "".join(self.contentsStack.pop())
		name = self.cleanupName(name)
		_, attrs = self.elementStack.pop()
		res = None
		if hasattr(self.realHandler, "_end_%s"%name):
			res = getattr(self.realHandler,
				"_end_%s"%name)(name, attrs, contents)
		elif hasattr(self, "_defaultEnd"):
			res = self._defaultEnd(name, attrs, contents)
		if isinstance(res, basestring) and not suppress:
			self.contentsStack[-1].append(res)

	def characters(self, chars):
		self.contentsStack[-1].append(chars)
	
	def getResult(self):
		return self.contentsStack[0][0]

	def getParentTag(self):
		if self.elementStack:
			return self.elementStack[-1][0]
	
	def parse(self, stream):
		xml.sax.parse(stream, self)
		return self
	
	def parseString(self, string):
		xml.sax.parseString(string, self)
		return self
	
	def getAttrsAsDict(self, attrs):
		"""returns attrs as received from SAX as a dictionary.

		The main selling point is that any namespace prefixes are removed from
		the attribute names.  Any prefixes on attrs remain, though.
		"""
		return dict((k.split(":")[-1], v) for k, v in attrs.items())



