"""
Resource mixins.
"""

import warnings

from gavo import base
from gavo.base import activetags
from gavo.rscdef import procdef


class ProcessEarly(procdef.ProcApp):
	"""A code fragment run by the mixin machinery when the structure
	being worked on is being finished.

	Access the structure mixed in as "substrate".
	"""
	name_ = "processEarly"
	formalArgs = "substrate"


class ProcessLate(procdef.ProcApp):
	"""A code fragment run by the mixin machinery when the parser parsing
	everything exits.

	Access the structure mixed in as "substrate", the root structure of
	the whole parse tree as root, and the context that is just about
	finishing as context.
	"""
	name_ = "processLate"
	formalArgs = "substrate, root, context"


class MixinDef(activetags.ReplayBase):
	"""A definition for a resource mixin.

	Resource mixins are resource descriptor fragments typically rooted
	in tables (though it's conceivable that other structures could
	grow mixin attributes as well).

	They are used to define and implement certain behaviours components of
	the DC software want to see:

	- products want to be added into their table, and certain fields are required
		within tables describing products
	- tables containing positions need some basic machinery to support scs.
	- siap needs quite a bunch of fields

	Mixins consist of events that are played back on the structure
	mixing in before anything else happens (much like original) and
	two procedure definitions, viz, processEarly and processLate.
	These can access the structure that has the mixin as substrate.

	processEarly is called as part of the substrate's completeElement
	method.  processLate is executed just before the parser exits.  This
	is the place to fix up anything that uses the table mixed in.  Note,
	however, that you should be as conservative as possible here -- you
	should think of DC structures as immutable as long as possible.

	Programmatically, you can check if a certain table mixes in 
	something by calling its mixesIn method.
	"""
	name_ = "mixinDef"

	_doc = base.UnicodeAttribute("doc", description="Documentation for"
		" this mixin", strip=False)
	_events = base.StructAttribute("events", 
		childFactory=activetags.EmbeddedStream,
		description="Events to be played back into the structure mixing"
		" this in", copyable=True)
	_processEarly = base.StructAttribute("processEarly", 
		default=None, 
		childFactory=ProcessEarly,
		description="Code executed at element fixup.")
	_processLate = base.StructAttribute("processLate", 
		default=None, 
		childFactory=ProcessLate,
		description="Code executed resource fixup.")

	def applyTo(self, destination, ctx):
		"""replays the stored events on destination and arranges for processEarly
		and processLate to be run.
		"""
		self.replay(self.events.events, destination, ctx)
		if self.processEarly is not None:
			self.processEarly.compile(destination)(destination)
		if self.processLate is not None:
			def procLate(rootStruct, parseContext):
				self.processLate.compile(destination)(
					destination, rootStruct, parseContext)
			ctx.addExitFunc(procLate)


class MixinAttribute(base.SetOfAtomsAttribute):
	def __init__(self, **kwargs):
		kwargs["itemAttD"] = base.UnicodeAttribute("mixin", strip=True)
		kwargs["description"] = kwargs.get("description", 
			"Reference to a mixin this table should contain.")
		base.SetOfAtomsAttribute.__init__(self, "mixin", **kwargs)
		# Hack: Remove at about svn revision 2000

	_deprecatedNamesMap = {
		"positions": "//scs#positions",
		"q3cpositions": "//scs#q3cpositions",
		"q3cindex": "//scs#q3cindex",
		"bboxSIAP": "//siap#bbox",
		"pgsSIAP": "//siap#pgs",
		"products": "//products#table",
	}	

	def feed(self, ctx, instance, mixinRef):
		if mixinRef in self._deprecatedNamesMap:
			warnings.warn("Deprecated id %s mixed in, use %s instead"%(
					mixinRef, self._deprecatedNamesMap[mixinRef]),
				DeprecationWarning)
			mixinRef = self._deprecatedNamesMap[mixinRef]
		mixin = ctx.resolveId(mixinRef, instance=instance, forceType=MixinDef)
		mixin.applyTo(instance, ctx)
		base.SetOfAtomsAttribute.feed(self, ctx, instance, mixinRef)

	def iterParentMethods(self):
		def mixesIn(instance, mixinRef):
			return mixinRef in instance.mixins
		yield "mixesIn", mixesIn

	# no need to override feedObject: On copy and such, replay has already
	# happened.
