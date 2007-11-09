"""
Special gavo widgets and their corresponding types based on nevow formal.
"""

from nevow import tags as T, entities as E
from formal import iformal
from formal import types as formaltypes
from formal import validation
from formal import widget
from formal.util import render_cssid
from zope.interface import implements

from formal.widget import *
from formal import widgetFactory

_linkGeneratingJs = """
function getEnclosingForm(element) {
// returns the form element immediately enclosing element.
	if (element.nodeName=="FORM") {
		return element;
	}
	return getEnclosingForm(element.parentNode);
}

function getSelectedEntries(selectElement) {
// returns an array of all selected entries from a select element 
// in url encoded form
	var result = new Array();
	var i;

	for (i=0; i<selectElement.length; i++) {
		if (selectElement.options[i].selected) {
			result.push(selectElement.name+"="+encodeURIComponent(
				selectElement.options[i].value))
		}
	}
	return result;
}

function makeQueryItem(element) {
// returns an url-encoded query tag item out of a form element
	var val=null;

	switch (element.nodeName) {
		case "INPUT":
			if (element.name && element.value) {
				val = element.name+"="+encodeURIComponent(element.value);
			}
			break;
		case "SELECT":
			return getSelectedEntries(element).join("&");
			break;
		default:
			alert("No handler for "+element.nodeName);
	}
	if (val) {
		return val;
	} else {
		return element.NodeName;
	}
}

function makeResultLink(form) {
	// returns a link to the result sending the HTML form form would
	// yield.
	var fragments = new Array();
	var fragment;
	var i;

	items = form.elements;
	for (i=0; i<items.length; i++) {
		fragment = makeQueryItem(items[i]);
		if (fragment) {
			fragments.push(fragment);
		}
	}
	return form.getAttribute("action")+"?"+fragments.join("&");
}
"""


def getOptionRenderer(initValue):
	"""returns a generator for option fields within a select field.
	"""
	def renderOptions(self, selItems):
		for value, label in selItems:
			option = T.option(value=value)[label]
			if value==initValue:
				yield option(selected="selected")
			else:
				yield option
	return renderOptions


class OutputOptions(object):
	"""a widget that offers various output formats for tables.

	This is for use in a formal form and goes together with the FormalDict
	type below.
	"""
# OMG, what a ghastly hack.  Clearly, I'm doing this wrong.  Well, it's the
# first thing I'm really trying with formal, so bear with me (and reimplement
# at some point...)
# Anyway: This is supposed to be a "singleton", i.e. the input key is ignored.
	implements(iformal.IWidget)

	def __init__(self, original):
		self.original = original

	def _renderTag(self, key, readonly, format, verbosity, tdEnc):
		if not format:
			format = "HTML"
		if not verbosity:
			verbosity = "2"
		if not tdEnc or tdEnc=="False":
			tdEnc = False
		formatEl = T.select(type="text", name='_FORMAT',
			onChange='adjustOutputFields(this)',
			onMouseOver='adjustOutputFields(this)',
			id=render_cssid(key, "FORMAT"),
			data=[("HTML", "HTML"), ("VOTable", "VOTable"), 
				("VOPlot", "VOPlot")])[
			getOptionRenderer(format)]
		verbosityEl = T.select(type="text", name='_VERB',
			id=render_cssid(key, "VERB"), style="width: auto",
			data=[("1","1"), ("2","2"), ("3","3")])[
				getOptionRenderer(verbosity)]
		tdEncEl = T.input(type="checkbox", id=render_cssid(key, "_TDENC"),
			name="_TDENC", class_="field boolean checkbox", value="True",
			style="width: auto")
		if tdEnc:
			tdEncEl(checked="checked")
		if readonly:
			for el in (formatEl, verbosityEl, tdEncEl):
				el(class_='readonly', readonly='readonly')
		# This crap is reproduced in the JS below -- rats
		if format=="HTML":
			verbVis = tdVis = "hidden"
		elif format=="VOPlot":
			verbVis, tdVis = "visible", "hidden"
		else:
			verbVis = tdVis = "visible"

		return T.div(class_="outputOptions")[
			T.inlineJS(_linkGeneratingJs),
			T.inlineJS('function adjustOutputFields(obj) {'
				'verbNode = obj.parentNode.childNodes[4];'
				'tdNode = obj.parentNode.childNodes[6];'
				'switch (obj.value) {'
					'case "HTML":'
						'verbNode.style.visibility="hidden";'
						'tdNode.style.visibility="hidden";'
						'break;'
					'case "VOPlot":'
						'verbNode.style.visibility="visible";'
						'tdNode.style.visibility="hidden";'
						'break;'
					'case "VOTable":'
						'verbNode.style.visibility="visible";'
						'tdNode.style.visibility="visible";'
						'break;'
					'}'
				'}'
			),
			"Format ", formatEl,
			T.span(id=render_cssid(key, "verbContainer"), style="visibility:%s"%
				verbVis)[" Verbosity ", verbosityEl], " ",
			T.span(id=render_cssid(key, "tdContainer"), style="visibility:%s"%
				tdVis)[tdEncEl, " VOTables for humans "],
			T.span(id=render_cssid(key, "QlinkContainer"))[
				T.a(href="", class_="resultlink", onMouseOver=
						"this.href=makeResultLink(getEnclosingForm(this))")
					["[Result link]"]
			],
		]

	def _getArgDict(self, key, args):
		return {
			"format": args.get("_FORMAT", [''])[0],
			"verbosity": args.get("_VERB", ['2'])[0],
			"tdEnc": args.get("_TDENC", ["False"])[0]}

	def render(self, ctx, key, args, errors):
		return self._renderTag(key, False, **self._getArgDict(key, args))

	def renderImmutable(self, ctx, key, args, errors):
		return self._renderTag(key, True, **self._getArgDict(key, args))

	def processInput(self, ctx, key, args):
		value = self._getArgDict(key, args)
		if not value["format"] in ["HTML", "VOTable", "VOPlot", ""]:
			raise validation.FieldValidationError("Unsupported output format")
		try:
			if not 1<=int(value["verbosity"])<=3:
				raise validation.FieldValidationError("Verbosity must be between"
					" 1 and 3")
		except ValueError:
			raise validation.FieldValidationError("Verbosity must be between"
					" 1 and 3")
		if value["tdEnc"] not in ["True", "False", None]:
			raise validation.FieldValidationError("tdEnc can only be True"
				" or False")
		value["tdEnc"] = value["tdEnc"]=="True"
		return value


class DbOptions(object):
	"""a widget that offers limit and sort options for db based cores.

	This is for use in a formal form and goes together with the FormalDict
	type below.
	"""
	implements(iformal.IWidget)

	def __init__(self, typeOb, service):
		self.service = service
		self.typeOb = typeOb
		self.sortWidget = self._makeSortWidget(service)
		self.limitWidget = self._makeLimitWidget(service)
		
	def _makeSortWidget(self, service):
		keys = [f.get_dest() for f in self.service.getOutputFields(None)]
		return widget.SelectChoice(formaltypes.String(), options=
			[(key, key) for key in keys])
	
	def _makeLimitWidget(self, service):
		keys = [(str(i), i) for i in [1000, 5000, 10000]]
		return widget.SelectChoice(formaltypes.Integer(), options=keys,
			noneOption=("100", 100))

	def render(self, ctx, key, args, errors):
		return T.span["Sort by ",
			self.sortWidget.render(ctx, "_DBOPTIONS_ORDER", args, errors),
			";  limit to ",
			self.limitWidget.render(ctx, "_DBOPTIONS_LIMIT", args, errors),
			" items."]

	# XXX TODO: make this immutable.
	renderImmutable = render

	def processInput(self, ctx, key, args):
		value = {
			"order": self.sortWidget.processInput(ctx, "_DBOPTIONS_ORDER", args),
			"limit": self.limitWidget.processInput(ctx, "_DBOPTIONS_LIMIT", args),
		}
		return value


class FormalDict(formaltypes.Type):
	"""is a formal type for dictionaries.
	"""
	pass


class SimpleSelectChoice(SelectChoice):
	def __init__(self, original, options, noneOption):
		super(SimpleSelectChoice, self).__init__(original,
			[(o,o) for o in options], (noneOption, noneOption))


def makeWidgetFactory(code):
	return eval(code)
