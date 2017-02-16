"""
Description and handling of inputs to services.

This module in particular describes the InputKey, the primary means
of describing input widgets and their processing.

They are collected in contextGrammars, entities creating input tables
and parameters.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import itertools

from gavo import base
from gavo import grammars
from gavo import rscdef
from gavo import utils
from gavo.rscdef import column
from gavo.svcs import dalipars
from gavo.svcs import pql
from gavo.svcs import vizierexprs

MS = base.makeStruct


_RENDERER_ADAPTORS = {
	'form': vizierexprs.adaptInputKey,
	'pql': pql.adaptInputKey,
	'dali': dalipars.adaptInputKey,
}

def getRendererAdaptor(renderer):
	"""returns a function that returns input keys adapted for renderer.

	The function returns None if no adapter is necessary.  This
	only takes place for inputKeys within a buildFrom condDesc.
	"""
	return _RENDERER_ADAPTORS.get(renderer.parameterStyle)


class InputKey(column.ParamBase):
	"""A description of a piece of input.

	Think of inputKeys as abstractions for input fields in forms, though
	they are used for services not actually exposing HTML forms as well.

	Some of the DDL-type attributes (e.g., references) only make sense here
	if columns are being defined from the InputKey.

	Properties evaluated:

	* defaultForForm -- a value entered into form fields by default
	  (be stingy with those; while it's nice to not have to set things
	  presumably right for almost everyone, having to delete stuff
	  you don't want over and over is really annoying).
	* adaptToRenderer -- a true boolean literal here causes the param
	  to be adapted for the renderer (e.g., float could become vizierexpr-float).
		You'll usually not want this, because the expressions are 
		generally evaluated by the database, and the condDescs do the
		adaptation themselves.  This is mainly for rare situations like
		file uploads in custom cores.
	* notForRenderer -- a renderer name for which this inputKey is suppressed
	* onlyForRenderer -- a renderer name for which this inputKey will be 
	  preserved; it will be dropped for all others.
	"""
	name_ = "inputKey"

	# XXX TODO: make widgetFactory and showItems properties.
	_widgetFactory = base.UnicodeAttribute("widgetFactory", default=None,
		description="A python expression for a custom widget"
		" factory for this input,"
		" e.g., 'Hidden' or 'widgetFactory(TextArea, rows=15, cols=30)'",
		copyable=True)
	_showItems = base.IntAttribute("showItems", default=3,
		description="Number of items to show at one time on selection widgets.",
		copyable=True)
	_inputUnit = base.UnicodeAttribute("inputUnit", default=None,
		description="Override unit of the table column with this.",
		copyable=True)
	_std = base.BooleanAttribute("std", default=False,
		description="Is this input key part of a standard interface for"
		" registry purposes?",
		copyable=True)
	_multiplicity = base.UnicodeAttribute("multiplicity", default=None,
		copyable=True,
		description="Set"
			" this to single to have an atomic value (chosen at random"
			" if multiple input values are given),"
			" forced-single to have an atomic value"
			" and raise an exception if multiple values come in, or"
			" multiple to receive lists.  On the form renderer, this is"
			" ignored, and the values are what nevow formal passes in."
			" If not given, it is single unless there is a values element with"
			" options, in which case it's multiple.")
	
	# Don't validate meta for these -- while they are children
	# of validated structures (services), they don't need any
	# meta at all.  This should go as soon as we have a sane
	# inheritance hierarchy for tables.
	metaModel = None

	def completeElement(self, ctx):
		self._completeElementNext(InputKey, ctx)
		if self.restrictedMode and self.widgetFactory:
			raise base.RestrictedElement("widgetFactory")

		if self.multiplicity is None:
			if self.isEnumerated():
				self.multiplicity = "multiple"
			else:
				self.multiplicity = "single"

	def onElementComplete(self):
		self._onElementCompleteNext(InputKey)
		# compute scaling if an input unit is given
		self.scaling = None
		if self.inputUnit:
			self.scaling = base.computeConversionFactor(self.inputUnit, self.unit)

	def onParentComplete(self):
		if self.parent and hasattr(self.parent, "required"):
			# children of condDescs inherit their requiredness
			# (unless defaulted)
			self.required = self.parent.required
		# but if there's a default, never require an input
		if self.value:
			self.required = False

	def validateValue(self, literal):
		"""raises a ValidationError if literal cannot be deserialised into
		an acceptable value for self.
		"""
		self._parse(literal)

	def computeCoreArgValue(self, inputList):
		"""parses some input for this input key.

		This takes into account multiplicities, type conversions, and
		all the remaining horrors.

		It will return a list or a single value, depending on multiplity.
		"""
		if not inputList:
			if self.value is not None:
				inputList = [self.value]

			elif self.values and self.values.default:
				inputList = [self.values.default]

			elif self.required:
				raise base.ValidationError(
					"Required parameter %s missing."%self.name,
					self.name)

			else:
				return None

		if self.multiplicity=="forced-single" and len(inputList)>1:
			raise base.MultiplicityError(
				"Inputs for the parameter %s must not have more than"
				" one value; hovever, %s was passed in."%(
					self.name,
					str(inputList)),
				colName=self.name)

		if self.multiplicity=="multiple":
			vals = [v for v in (self._parse(val) for val in inputList)
				if v is not None]
			return vals or None


		else:
			if inputList:
				 return self._parse(inputList[-1])
			else:
				return None

	@classmethod
	def fromColumn(cls, column, **kwargs):
		"""returns an InputKey for query input to column.
		"""
		if isinstance(column, InputKey):
			if kwargs:
				return column.change(**kwargs)
			else:
				return column

		instance = cls(None)
		instance.feedObject("original", column)

		for k,v in kwargs.iteritems():
			instance.feed(k, v)
		if not "required" in kwargs:
			instance.feedObject("required", False)
		instance.dmRoles = rscdef.OldRoles(column.dmRoles)
		return instance.finishElement(None)


def filterInputKeys(keys, rendName, adaptor=None):
	"""filters inputKeys in key, only returning those compatible with
	rendName.

	adaptor is is a function taking and returning an inputKey that is used
	for input keys with an adaptToRenderer property.
	"""
	for key in keys:
		if key.getProperty("onlyForRenderer", None) is not None:
			if key.getProperty("onlyForRenderer")!=rendName:
				continue
		if key.getProperty("notForRenderer", None) is not None:
			if key.getProperty("notForRenderer")==rendName:
				continue

		if base.parseBooleanLiteral(key.getProperty("adaptToRenderer", "False")
				) and adaptor:
			key = adaptor(key)

		yield key
	

class InputTD(base.Structure, base.StandardMacroMixin):
	"""an input for a core.

	These aren't actually proper tables but actually just collection of
	the param-like inputKeys.  They serve as input declarations for cores
	and services (where services derive their inputTDs from the cores' ones by
	adapting them to the current renderer.  Their main use is for the derivation
	of contextGrammars.

	They can carry metadata, though, which is sometimes convenient when 
	transporting information from the parameter parsers to the core.
	
	For the typical dbCores (and friends), these are essentially never
	explicitly defined but rather derived from condDescs.

	Do *not* read input values by using table.getParam.  This will only
	give you one value when a parameter has been given multiple times.
	Instead, use the output of the contextGrammar (inputParams in condDescs).
	Only there you will have the correct multiplicities.
	"""
	name_ = "inputTable"

	_inputKeys = rscdef.ColumnListAttribute("inputKeys",
		childFactory=InputKey, 
		description='Input parameters for this table.', 
		copyable=True)

	_groups = base.StructListAttribute("groups",
		childFactory=rscdef.Group,
		description="Groups of inputKeys (this is used for form UI formatting).",
		copyable=True)

	_exclusive = base.BooleanAttribute("exclusive",
		description="If true, context grammars built from this will"
			" raise an error if contexts passed in have keys not defined"
			" by this table",
		default=False,
		copyable=True)
	_rd = rscdef.RDAttribute()

	def __iter__(self):
		return iter(self.inputKeys)

	def adaptForRenderer(self, renderer):
		"""returns an inputTD tailored for renderer.

		This is discussed in svcs.core's module docstring.
		"""
		newKeys = list(
			filterInputKeys(self.inputKeys, renderer.name,
				getRendererAdaptor(renderer)))

		if newKeys!=self.inputKeys:
			return self.change(inputKeys=newKeys, parent_=self)
		else:
			return self
	
	def resolveName(self, ctx, name):
		"""returns a column name from a queried table of the embedding core,
		if available.

		This is a convenicence hack that lets people reference columns from
		a TableBasedCore by their simple, non-qualified names.
		"""
		if self.parent and hasattr(self.parent, "queriedTable"):
			return self.parent.queriedTable.resolveName(ctx, name)
		raise base.NotFoundError(id, "Element with id or name", "name path",
			hint="There is not queried table this name could be resolved in.")


class CoreArgs(base.MetaMixin):
	"""A container for core arguments.

	There's inputTD, which reference the renderer-adapted input table,
	and args, the ContextGrammar processed input.  For kicks, we also
	have rawArgs, which is the contextGrammar's input (if you find
	you're using it, tell us; that's pointing to a problem on our side).

	getParam(name) -> value and getParamDict() -> dict methods are
	present for backward compatibility.
	"""
	def __init__(self, inputTD, args, rawArgs):
		self.inputTD, self.args, self.rawArgs = inputTD, args, rawArgs
		base.MetaMixin.__init__(self)
	
	def getParam(self, name):
		return self.args.get(name)

	def getParamDict(self):
		return self.args

	@classmethod
	def fromRawArgs(cls, inputTD, rawArgs, contextGrammar=None):
		"""returns a CoreArgs instance built from an inputDD and 
		ContextGrammar-parseable rawArgs.

		contextGrammar can be overridden, e.g., to cache or to add
		extra, non-core keys.
		"""
		if contextGrammar is None:
			contextGrammar = MS(ContextGrammar, inputTD=inputTD)
		ri = contextGrammar.parse(rawArgs)
		_ = list(ri)  #noflake: ignored value
		return cls(inputTD, ri.getParameters(), rawArgs)


class ContextRowIterator(grammars.RowIterator):
	"""is a row iterator over "contexts", i.e. single dictionary-like objects.

	The source token expected here can be a request.args style dictionary
	with lists of strings as arguments, or a parsed dictionary from nevow
	formal. Non-list literals in the latter are packed into a list to ensure
	consistent behaviour.
	"""
	def __init__(self, grammar, sourceToken, **kwargs):
		self.locator = "(internal)"
		grammars.RowIterator.__init__(self, grammar,
			utils.CaseSemisensitiveDict(sourceToken),
			**kwargs)

	def _ensureListValues(self):
		"""this turns lonely values in the sourceToken into lists so we
		don't have to special-case nevow formal dicts.
		"""
		for key, value in self.sourceToken.iteritems():
			if not isinstance(value, list):
				if value is None:
					self.sourceToken[key] = []
				else:
					self.sourceToken[key] = [value]
	
	def _ensureNoExtras(self):
		"""makes sure sourceToken has no keys not mentioned in the grammar.

		Here, we assume case-insensitive arguments for now.  If we ever
		want to change that... oh, my.

		This is only exectued for grammars with rejectExtras.
		"""
		inKeys = set(n.lower() for n in self.sourceToken)
		expectedKeys = set(k.name.lower() for k in self.grammar.iterInputKeys())
		if inKeys-expectedKeys:
			raise base.ValidationError("The following parameter(s) are"
				" not accepted by this service: %s"%",".join(
					sorted(inKeys-expectedKeys)),
				"(various)")

	def _iterRows(self):
		# we don't really return any rows, but this is where our result
		# dictionary is built.
		self._ensureListValues()
		if self.grammar.rejectExtras:
			self._ensureNoExtras()
		
		self.coreArgs = {} 

		for ik in self.grammar.iterInputKeys():
			self.locator = "param %s"%ik.name
			self.coreArgs[ik.name] = ik.computeCoreArgValue(
				self.sourceToken.get(ik.name))

		if False:
			yield {}  # contextGrammars yield no rows.
			
	def getParameters(self):
		return self.coreArgs
	
	def getLocator(self):
		return self.locator


class ContextGrammar(grammars.Grammar):
	"""A grammar for web inputs.

	The source tokens for context grammars are dictionaries; these
	are either typed dictionaries from nevow formal, where the values
	usually are atomic, or, preferably, the dictionaries of lists
	from request.args.

	ContextGrammars never yield rows, so they're probably fairly useless
	in normal cirumstances.

	In normal usage, they just yield a single parameter row,
	corresponding to the source dictionary possibly completed with
	defaults, where non-requried input keys get None defaults where not
	given.  Missing required parameters yield errors.

	This parameter row honors the multiplicity specification, i.e., single or
	forced-single are just values, multiple are lists.  The content are
	*parsed* values (using the InputKeys' parsers).

	Since most VO protocols require case-insensitive matching of parameter
	names, matching of input key names and the keys of the input dictionary
	is attempted first literally, then disregarding case.
	"""
	name_ = "contextGrammar"

	_inputTD = base.ReferenceAttribute("inputTD", 
		default=base.NotGiven, 
		description="The input table from which to take the input keys",
		copyable=True)

	_inputKeys = base.StructListAttribute("inputKeys",
		childFactory=InputKey,
		description="Extra input keys not defined in the inputTD.  This"
			" is used when services want extra input processed by them rather"
			" than their core.",
		copyable=True)

	_original = base.OriginalAttribute("original")

	rowIterator = ContextRowIterator

	rejectExtras = False

	def onElementComplete(self):
		self._onElementCompleteNext(ContextGrammar)
		self.rejectExtras = self.inputTD.exclusive

	def iterInputKeys(self):
		return itertools.chain(iter(self.inputTD), iter(self.inputKeys))


_OPTIONS_FOR_MULTIS = {
	"forced-single": ", single=True, forceUnique=True",
	"single": ", single=True",
	"multiple": "",
}

