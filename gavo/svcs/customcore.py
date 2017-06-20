"""
User-defined cores

XXX TODO: Revise this to have events before module replayed.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import utils
from gavo.svcs import core


class ModuleAttribute(base.UnicodeAttribute):
# XXX TODO: this is a bad hack since it assumes id on instance has already
# been set.  See above on improving all this using an event replay framework.
	typeDesc = "resdir-relative path to a module; no extension is allowed"

	def feed(self, ctx, instance, modName):
		modName = os.path.join(instance.rd.resdir, modName)
		userModule, _ = utils.loadPythonModule(modName)
		newCore = userModule.Core(instance.parent)
		ctx.idmap[instance.id] = newCore
		raise base.Replace(newCore)


class CustomCore(core.Core):
	"""A wrapper around a core defined in a module.

	This core lets you write your own cores in modules.

	The module must define a class Core.  When the custom core is
	encountered, this class will be instanciated and will be used
	instead of the CustomCore, so your code should probably inherit 
	core.Core.

	See `Writing Custom Cores`_ for details.
	"""
	name_ = "customCore"

	_module = ModuleAttribute("module", default=base.Undefined,
		description="Path to the module containing the core definition.")


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
