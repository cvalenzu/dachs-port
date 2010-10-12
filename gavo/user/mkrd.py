"""
Creation of resource descriptors

When we get structured data, we can suggest resource descriptors.

Here, we try this for data described through primary FITS headers and 
VOTables.
"""

# We probably want to turn this around and first create the RD and pass
# that around so the individual analyzers can add, e.g. global metadata.

import os
import re
import sys
from itertools import *

from gavo import base
from gavo import grammars
from gavo import rscdef
from gavo import votable
from gavo import utils
from gavo.base import typesystems
from gavo.formats import votableread
from gavo.utils import ElementTree
from gavo.utils import fitstools

MS = base.makeStruct


ignoredFITSHeaders = set(["COMMENT", "SIMPLE", "BITPIX", "EXTEND", 
	"NEXTEND", "SOFTNAME", "SOFTVERS", "SOFTDATE", "SOFTAUTH", "SOFTINST",
	"HISTORY", "BZERO"])
wcsKey = re.compile("CD.*|CRVAL.*|CDELT.*|NAXIS.*|CRPIX.*|CTYPE.*|CUNIT.*"
	"|CROTA.*|RADECSYS|EQUINOX")


def isIgnoredKeyword(kw):
	"""returns true if kw should not be translated or put into the table.

	This is important for all WCS keywords when you want to compute
	SIAP bboxes; these keywords must not be translated.
	"""
	return kw in ignoredFITSHeaders or wcsKey.match(kw)


def structToETree(aStruct):
	"""returns an ElementTree for the copyable content of aStruct.

	Note that due to manipulations at parse time and non-copyable content,
	this will, in general, not reproduce the original XML trees.
	"""
	nodeStack = [ElementTree.Element(aStruct.name_)]
	for evType, elName, value in aStruct.iterEvents():
		try:
			if evType=="start":
				nodeStack.append(ElementTree.SubElement(nodeStack[-1], elName))
			elif evType=="end":
				nodeStack.pop()
			elif evType=="value":
				if value is None or value is base.NotGiven:
					continue
				if elName=="content_":
					nodeStack[-1].text = value
				else:
					nodeStack[-1].set(elName, value)
			else:
				raise base.Error("Invalid struct event: %s"%evType)
		except:
			base.ui.notifyError("Badness occurred in element %s, event %s,"
				" value %s\n"%(elName, evType, value))
			raise
	return nodeStack[-1]


class EventStorage(object):
	"""is a stand-in for a Structure during parsing.

	It records events coming in from the parser and can later
	replay them.

	It has a name_ attribute and feeds it from the first start event
	it receives.
	"""
	name_ = "events"

	def __init__(self, parent, **kwargs):
		self.parent, self.name_ = parent, None
		self.events, self.handlerStack = [], []
		for k,v in kwargs.iteritems():
			self.feedEvent("value", k, v)
		self.handlerStack.append(parent)
	
	def finishElement(self):
		return self
	
	def feedEvent(self, ctx, type, name, val):
		if type=="start":
			if self.name_ is None:  # enclosing element, baptize me
				self.name_ = name
				self.handlerStack.append(self)
			else:  # memorize we've swallowed an element
				self.handlerStack.append(self.feedEvent)
		self.events.append((type, name, val))
		if type=="end":
			return self.handlerStack.pop()
		return self
	
	def iterEvents(self):
		return islice(self.events, 1, len(self.events)-1)


def makeTableFromFITS(rd, srcName, opts):
	def getHeaderKeys(srcName):
		header = fitstools.openFits(srcName)[0].header
		return header.ascardlist()

	keyMappings = []
	table = rscdef.TableDef(rd, id=opts.tableName, onDisk=True)
	for index, card in enumerate(getHeaderKeys(srcName)):
		if isIgnoredKeyword(card.key):
			continue
		colName = card.key.lower()
		table.feedObject("column", MS(rscdef.Column,
			name=colName, unit="FILLIN", ucd="FILLIN", type="FILLIN",
			description=card.comment))
		keyMappings.append((colName, card.key))
	rd.setProperty("mapKeys", ", ".join("%s:%s"%(k,v) for k,v in keyMappings))
	return table.finishElement()


def makeDataForFITS(rd, srcName, opts):
	targetTable = rd.tables[0]
	dd = rscdef.DataDescriptor(rd, id="import_"+opts.tableName)
	grammar = grammars.FITSProdGrammar(dd)
	grammar.feedObject("qnd", True)
	rowgen = base.parseFromString(EventStorage, """<events>
		<rowgen predefined="defineProduct">
				<arg key="table">"%s"</arg>
				<arg key="owner">"FILLIN"</arg>
				<arg key="embargo">"FILLIN"</arg>
		</rowgen></events>"""%(targetTable.getQName()))
	grammar.feedObject("rowgen", rowgen)
	grammar.feedObject("mapKeys", MS(grammars.MapKeys,
		content_=rd.getProperty("mapKeys")))
	grammar.finishElement()
	dd.grammar = grammar
	dd.feedObject("make", MS(rscdef.Make, table=targetTable))
	return dd


def makeTableFromVOTable(rd, srcName, opts):
	rawTable = votable.parse(srcName).next().tableDefinition
	return votableread.makeTableDefForVOTable(opts.tableName, 
		tableDefinition, {}, onDisk=True)


def makeDataForVOTable(rd, srcName, opts):
	return MS(rscdef.DataDescriptor,
		grammar=MS(rscdef.getGrammar("voTableGrammar")),
		sources=MS(rscdef.SourceSpec, pattern=srcName),
		makes=[MS(rscdef.Make, table=rd.tables[0])])


tableMakers = {
	"FITS": makeTableFromFITS,
	"VOT": makeTableFromVOTable,
}

dataMakers = {
	"FITS": makeDataForFITS,
	"VOT": makeDataForVOTable,
}

def makeRD(args, opts):
	from gavo import rscdesc
	rd = rscdesc.RD(None, schema=os.path.basename(os.getcwd()))
	rd.feedObject("table", tableMakers[opts.srcForm](rd, args[0], opts))
	rd.feedObject("data", dataMakers[opts.srcForm](rd, args[0], opts))
	return rd.finishElement()


def writePrettyPrintedXML(eTree):
	f = os.popen("xmlstarlet fo", "w")
	ElementTree.ElementTree(eTree).write(f, encoding="utf-8")
	f.close()


def parseCommandLine():
	from optparse import OptionParser
	parser = OptionParser(usage = "%prog [options] <sample>")
	parser.add_option("-f", "--format", help="FITS or VOT, source format."
		"  Default: Detect from file name", dest="srcForm", default=None,
		action="store", type="str")
	parser.add_option("-t", "--table-name", help="Name of the generated table",
		dest="tableName", default="main", action="store", type="str")
	opts, args = parser.parse_args()
	if len(args)!=1:
		parser.print_help()
		sys.exit(1)
	if not opts.srcForm:
		ext = os.path.splitext(args[0])[1].lower()
		if ext in set([".xml", ".vot"]):
			opts.srcForm = "VOT"
		elif ext==".fits":
			opts.srcForm = "FITS"
		else:
			sys.stderr.write("Cannot guess format: %s"%args[0])
			parser.print_help()
			sys.exit(1)
	return opts, args


def main():
	# hack to make id and onDisk copyable so we see them on iterEvent
	rscdef.TableDef._id.copyable = rscdef.TableDef._onDisk.copyable = True
	rscdef.DataDescriptor._id.copyable = True
	opts, args = parseCommandLine()
	rd = makeRD(args, opts)
	writePrettyPrintedXML(structToETree(rd))


if __name__=="__main__":
	#main()
	base.parseFromString(EventStorage, """<events>
		<rowgen predefined="defineProduct">
				<arg key="table">"%s"</arg>
				<arg key="owner">"FILLIN"</arg>
				<arg key="embargo">"FILLIN"</arg>
		</rowgen></events>"""%("xyz"))

