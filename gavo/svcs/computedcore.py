"""
Cores wrapping some external program directly, or having some
python code doing things.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.svcs import core


class ComputedCore(core.Core):
	"""A core wrapping external applications.
	
	ComputedCores wrap command line tools taking command line arguments,
	reading from stdin, and outputting to stdout.

	The command line arguments are taken from the inputTable's parameters,
	stdin is created by serializing the inputTable's rows like they are 
	serialized for with the TSV output, except only whitespace is entered 
	between the values.
	
	The output is the primary table of parsing the program's output with
	the data child.

	While in principle more declarative than PythonCores, these days I'd
	say rather use one of those.
	"""
	name_ = "computedCore"

	_computer = rscdef.ResdirRelativeAttribute("computer",
		default=base.Undefined, description="Resdir-relative basename of"
			" the binary doing the computation.  The standard rules for"
			" cross-platform binary name determination apply.",
			copyable=True)
	_resultParse = base.StructAttribute("resultParse",
		description="Data descriptor to parse the computer's output.",
		childFactory=rscdef.DataDescriptor, copyable=True)

	def start_(self, ctx, name, value):
		if name=="outputTable":
			raise base.StructureError("Cannot define a computed core's"
				" output table.", hint="Computed cores have their output"
				" defined by the primary table of resultParse.")
		return core.Core.start_(self, ctx, name, value)

	def completeElement(self, ctx):
		raise base.StructureError("ComputedCore was a bad idea and"
			" is therefore removed in DaCHS 1.0")


class CoreProc(rscdef.ProcApp):
	"""A definition of a pythonCore's functionalty.

	This is a procApp complete with setup and code; you could inherit
	between these.

	coreProcs see the embedding service, the input table passed, and the
	query metadata as service, inputTable, and queryMeta, respectively.

	The core itself is available as self.
	"""
	name_ = "coreProc"
	requiredType = "coreProc"
	formalArgs = "self, service, inputTable, queryMeta"

	additionalNamesForProcs = {
		"rsc": rsc
	}


class PythonCore(core.Core):
	"""A core doing computation using a piece of python.

	See `Python Cores instead of Custom Cores`_ in the reference.
	"""
	name_ = "pythonCore"

	_computer = base.StructAttribute("coreProc", default=base.Undefined,
		childFactory=CoreProc, 
		description="Code making the outputTable from the inputTable.",
		copyable=True)

	def expand(self, s):
		# macro expansion should ideally take place in the service,
		# but that's impossible in general because a core could be
		# in use by several services.  Hence, we go ask the RD
		return self.rd.expand(s)
	def run(self, service, inputTable, queryMeta):
		return self.coreProc.compile()(self, service, inputTable, queryMeta)
