"""
Cores are the standard object for computing things in the DC.

This module also contains the registry for cores.  If you want to
be able to refer to cores from within an RD, you need to enter your
core here.

Cores return pairs of a type and a payload.  Renderers should normally
be prepared to receive (None, OutputTable) and (mime/str, data/str),
though individual cores might return other stuff (and then only
work with select renderers).

In general, the input table definition is mandatory, i.e., you have
to come up with it.  Services do this either ad-hoc from input from
the web or using an inputDD.

The output table, on the other hand, is "advisory", mainly for registry
and documentation purposes ("I *could* return this").  In particular
DBBasedCores will usually adapt to the service's wishes when it comes
to the output table structure, not to mention the ADQL core.  This doesn't
hurt since whatever is returned comes with structure documentation of
its own.

Cores may also want to adapt to renderers.  This is a bit of a hack to
support, e.g., form and scs within a single service, which avoids
two different VOResource records just because of slightly differning
input definitions.

The interface here is the adaptForRenderer method.  It takes a single
argument, the renderer, either as a simple name resolvable in the renderer
registry, or as a renderer instance or class.  It must return a new
core instance.

Currently, two mechanisms for core adaptation are in place:

(1) generically, inputKeys can have properties onlyForRenderer and 
notForRenderer with the obvious semantics.

(2) cores that have condDescs may adapt by virtue of condDesc's 
adaptForRenderer method.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import utils
from gavo.svcs import inputdef
from gavo.svcs import outputdef


CORE_REGISTRY = {
#	elementName -> module (without gavo.), class name
	"adqlCore": ("protocols.adqlglue", "ADQLCore"),
	"customCore": ("svcs.customcore", "CustomCore"),
	"datalinkCore": ("protocols.datalink", "DatalinkCore"),
	"dbCore": ("svcs.standardcores", "DBCore"),
	"debugCore": ("svcs.core", "DebugCore"),
	"fancyQueryCore": ("svcs.standardcores", "FancyQueryCore"),
	"fixedQueryCore": ("svcs.standardcores", "FixedQueryCore"),
	"nullCore": ("svcs.standardcores", "NullCore"),
	"productCore": ("protocols.products", "ProductCore"),
	"pythonCore": ("svcs.customcore", "PythonCore"),
	"registryCore": ("registry.oaiinter", "RegistryCore"),
	"scsCore": ("protocols.scs", "SCSCore"),
	"siapCutoutCore": ("protocols.siap", "SIAPCutoutCore"),
	"ssapCore": ("protocols.ssap", "SSAPCore"),
	"tapCore": ("protocols.tap", "TAPCore"),
	"uploadCore": ("svcs.uploadcores", "UploadCore"),
}


def getCore(name):
	if name not in CORE_REGISTRY:
		raise base.NotFoundError(name, "core", "registred cores")
	cls = utils.loadInternalObject(*CORE_REGISTRY[name])
	if cls.name_!=name:
		raise base.ReportableError("Internal Error: Core %s is registred"
			" under the wrong name."%name,
			hint="This is probably a typo in svcs.core; it needs"
			" to be fixed there")
	return cls


class _OutputTableFactory(object):
	"""The childFactory for a core's outputTable.

	On call, it will return a slightly amended copy of the 
	queried table.

	This means that you must set the queried table before mentioning the
	outputs.
	"""
	name_ = "outputTable"

	def __call__(self, parent):
		if parent._ot_prototype is None:
			ot = outputdef.OutputTableDef(parent)
			parent._ot_prototype = base.parseFromString(ot,
				parent.outputTableXML or "<outputTable/>")
		return parent._ot_prototype.copy(parent)


class Core(base.Structure):
	"""A definition of the "active" part of a service.

	A core will receive input from a renderer in the form of a ``svcs.CoreArgs``
	(see `Core Args`_).  A core will return a table or perhaps directly
	data as discussed in `DaCHS' Service Interface`_ .

	The abstract core element will never occur in resource descriptors.  See 
	`Cores Available`_ for concrete cores.  Use the names of the concrete
	cores in RDs.
	"""
	name_ = "core"

	inputTableXML = None
	outputTableXML = None

	# the cached prototype of the output table, filled in by 
	# _OutputTableFactory
	_ot_prototype = None

	_rd = rscdef.RDAttribute()
	_inputTable = base.StructAttribute("inputTable", 
		default=base.NotGiven,
		childFactory=inputdef.InputTD, 
		description="Description of the input data", 
		copyable=True)

	_outputTable = base.StructAttribute("outputTable", 
		default=base.NotGiven,
		childFactory=_OutputTableFactory(),
		description="Table describing what fields are available from this core", 
		copyable=True)

	_original = base.OriginalAttribute()

	_properties = base.PropertyAttribute()

	def __init__(self, parent, **kwargs):
		if self.inputTableXML is not None:
			if "inputTable" not in kwargs:
				kwargs["inputTable"] = base.parseFromString(
					inputdef.InputTD, self.inputTableXML)

		base.Structure.__init__(self, parent, **kwargs)

	def __repr__(self):
		return "<%s at %s>"%(self.__class__.__name__, id(self))
	
	def __str__(self):
		return repr(self)

	def completeElement(self, ctx):
		self._completeElementNext(Core, ctx)
		self.initialize()
		if self.inputTable is base.NotGiven:
			self.inputTable = base.makeStruct(inputdef.InputTD)
		if self.outputTable is base.NotGiven:
			self.outputTable = self._outputTable.childFactory(self)

	def initialize(self):
		"""override to configure the custom core before use.

		This is typically where you pull input or output tables
		from the RD in customCores.  Actual DaCHS code should use
		completeElement as usual.
		"""

	def adaptForRenderer(self, renderer):
		"""returns a core object tailored for renderer.
		"""
		newIT = self.inputTable.adaptForRenderer(renderer)
		if newIT is self.inputTable:
			return self
		else:
			return self.change(inputTable=newIT)

	def run(self, service, inputData, queryMeta):
		raise NotImplementedError("%s cores are missing the run method"%
			self.__class__.__name__)

	def makeUserDoc(self):
		return ("Polymorphous core element.  May contain any of the cores"
			" mentioned in `Cores Available`_ .")


class DebugCore(Core):
	"""a core that returns its arguments stringified in a table.

	You need to provide an external input tables for these.
	"""
	name_ = "debugCore"

	outputTableXML = """
		<outputTable>
			<outputField name="key" type="text"
				description="Name of an input parameter"/>
			<outputField name="value" type="text"
				description="(First) value passed (or None)"/>
		</outputTable>"""
	
	def run(self, service, inputTable, queryMeta):
		rows = []
		for par in inputTable.inputTD:
			if par.type=="file":
				value = inputTable.args[par.name][1].read()
			else:
				value = inputTable.args[par.name]
			rows.append({"key": par.name, "value": utils.safe_str(value)})
		return rsc.TableForDef(self.outputTable, rows=rows)


