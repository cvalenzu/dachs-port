"""
Classes and methods to support vizier-type specifications on fields.
"""

import re

from pyparsing import Word, Literal, Optional, Forward, Group,\
	ZeroOrMore, nums, Suppress, ParseException, StringEnd, Regex,\
	OneOrMore, Or, MatchFirst, CharsNotIn

import gavo
from gavo import typesystems
from gavo.parsing import typeconversion


class ParseNode(object):
	"""is a parse node, consisting of an operator and children.

	The parse trees returned by the various parse functions are built by
	these.
	"""
	def __init__(self, children, operator):
		self.children = children
		self.operator = operator
	
	def __str__(self):
		return "(%s %s)"%(self.operator, " ".join([str(c) for c in self.children]))

	__repr__ = __str__

	def _insertChild(self, index, key, sqlPars):
		"""inserts children[index] into sqlPars with a unique key and returns
		the key.

		children[index] must be atomic (i.e., no ParseNode).
		"""
		item = self.children[index]
		if item==None:
			return None
		assert not isinstance(item, ParseNode)
		return getSQLKey(key, item, sqlPars)

	def asSQL(self, key, sqlPars):
		if self.operator in self._standardOperators:
			return "%s %s %%(%s)s"%(key, self.operator, 
				self._insertChild(0, key, sqlPars))
		else:
			return self._sqlEmitters[self.operator](self, key, sqlPars)


class NumericNode(ParseNode):
	"""is a node containing numeric operands (floats or dates).
	"""
	def _emitBinop(self, key, sqlPars):
		return joinOperatorExpr(self.operator,
			[c.asSQL(key, sqlPars) for c in self.children])
		
	def _emitUnop(self, key, sqlPars):
		operand = self.children[0].asSQL(key, sqlPars)
		if operand:
			return "%s (%s)"%(self.operator, operand)

	def _emitEnum(self, key, sqlPars):
		return "%s IN (%s)"%(key, ", ".join([
					"%%(%s)s"%self._insertChild(i, key, sqlPars) 
				for i in range(len(self.children))]))

	_standardOperators = set(["=", ">=", ">", "<=", "<"])
	_sqlEmitters = {
		'..': lambda self, key, sqlPars: "%s BETWEEN %%(%s)s AND %%(%s)s"%(key, 
			self._insertChild(0, key, sqlPars), self._insertChild(1, key, sqlPars)),
		'AND': _emitBinop,
		'OR': _emitBinop,
		'NOT': _emitUnop,
		',': _emitEnum,
	}


class StringNode(ParseNode):
	def asSQL(self, key, sqlPars):
		if self.operator=="[":
			return "[%s]"%self.children[0]
		if self.operator in self._nullOperators:
			return self._nullOperators[self.operator]
		else:
			return super(StringNode, self).asSQL(key, sqlPars)
	
	def _makePattern(self, key, sqlPars):
		parts = []
		for child in self.children:
			if isinstance(child, basestring):
				parts.append(re.escape(child))
			else:
				parts.append(child.asSQL(key, sqlPars))
		return "".join(parts)

	_patOps = {
		"~": "~*",
		"=": "~",
		"!~": "!~*",
		"!": "!~",
	}
	def _emitPatOp(self, key, sqlPars):
		pattern = self._makePattern(key, sqlPars)
		return "%s %s %%(%s)s"%(key, self._patOps[self.operator],
			getSQLKey(key, pattern, sqlPars))

	def _emitEnum(self, key, sqlPars):
		query = "%s IN (%s)"%(key, ", ".join([
					"%%(%s)s"%self._insertChild(i, key, sqlPars) 
				for i in range(len(self.children))]))
		if self.operator=="!=,":
			query = "NOT (%s)"%query
		return query
	
	_nullOperators = {"*": ".*", "?": "."}
	_standardOperators = set(["<", ">", "<=", ">=", "==", "!="])
	_sqlEmitters = {
		"~": _emitPatOp,
		"=": _emitPatOp,
		"!~": _emitPatOp,
		"!": _emitPatOp,
		"=,": _emitEnum,
		"=|": _emitEnum,
		"!=,": _emitEnum,
		}


def _getNodeFactory(op, nodeClass):
	def _(s, loc, toks):
		return nodeClass(toks, op)
	return _


def _makeNotNode(s, loc, toks):
	if len(toks)==1:
		return toks[0]
	elif len(toks)==2:
		return NumericNode(toks[1:], "NOT")
	else: # Can't happen :-)
		raise Exception("Busted by not")


def _makePmNode(s, loc, toks):
	return NumericNode([toks[0]-toks[1], toks[0]+toks[1]], "..")


def _makeDatePmNode(s, loc, toks):
	"""returns a +/- node for dates, i.e., toks[1] is a float in days.
	"""
	days = typeconversion.make_timeDelta(days=toks[1])
	return NumericNode([toks[0]-days, toks[0]+days], "..")


def _getBinopFactory(op):
	def _(s, loc, toks):
		if len(toks)==1:
			return toks[0]
		else:
			return NumericNode(toks, op)
	return _


def _makeSimpleExprNode(s, loc, toks):
	if len(toks)==1:
		return NumericNode(toks[0:], "=")
	else:
		return NumericNode(toks[1:], toks[0])



def getComplexGrammar(baseLiteral, pmBuilder, errorLiteral=None):
	"""returns the root element of a grammar parsing numeric vizier-like 
	expressions.

	This is used for both dates and floats, use baseLiteral to match the
	operand terminal.  The trouble with dates is that the +/- operator
	has a simple float as the second operand, and that's why you can
	pass in an errorLiteral and and pmBuilder.
	"""
	if errorLiteral==None:
		errorLiteral = baseLiteral

	preOp = Literal("=") |  Literal(">=") | Literal(">"
		) | Literal("<=") | Literal("<")
	rangeOp = Literal("..")
	pmOp = Literal("+/-") | Literal("\xb1".decode("iso-8859-1"))
	orOp = Literal("|")
	andOp = Literal("&")
	notOp = Literal("!")
	commaOp = Literal(",")

	preopExpr = Optional(preOp) + baseLiteral
	rangeExpr = baseLiteral + Suppress(rangeOp) + baseLiteral
	valList = baseLiteral + OneOrMore( Suppress(commaOp) + baseLiteral)
	pmExpr = baseLiteral + Suppress(pmOp) + errorLiteral
	simpleExpr = rangeExpr | pmExpr | valList | preopExpr

	expr = Forward()

	notExpr = Optional(notOp) +  simpleExpr
	andExpr = notExpr + ZeroOrMore( Suppress(andOp) + notExpr )
	orExpr = andExpr + ZeroOrMore( Suppress(orOp) + expr)
	expr << orExpr
	exprInString = expr + StringEnd()

	rangeExpr.setName("rangeEx")
	rangeOp.setName("rangeOp")
	notExpr.setName("notEx")
	andExpr.setName("andEx")
	andOp.setName("&")
	orExpr.setName("orEx")
	expr.setName("expr")
	simpleExpr.setName("simpleEx")

	preopExpr.setParseAction(_makeSimpleExprNode)
	rangeExpr.setParseAction(_getNodeFactory("..", NumericNode))
	pmExpr.setParseAction(pmBuilder)
	valList.setParseAction(_getNodeFactory(",", NumericNode))
	notExpr.setParseAction(_makeNotNode)
	andExpr.setParseAction(_getBinopFactory("AND"))
	orExpr.setParseAction(_getBinopFactory("OR"))

	return exprInString


floatLiteral = Regex(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?").setParseAction(
			lambda s, pos, tok: float(tok[0]))
# XXX TODO: be a bit more lenient in what you accept as a date
dateLiteral = Regex(r"\d\d\d\d-\d\d-\d\d").setParseAction(
			lambda s, pos, tok: typeconversion.make_dateTimeFromString(tok[0]))


def parseNumericExpr(str, baseSymbol=getComplexGrammar(floatLiteral, 
		_makePmNode)):
	"""returns a parse tree for vizier-like expressions over floats.
	"""
	return baseSymbol.parseString(str)[0]


def parseDateExpr(str, baseSymbol=getComplexGrammar(dateLiteral,
		_makeDatePmNode, floatLiteral)):
	"""returns a parse tree for vizier-like expressions over ISO dates.

	Note that the semantic validity of the date (like, month<13) is not
	checked by the grammar.
	"""
	return baseSymbol.parseString(str)[0]


def _makeOpNode(s, loc, toks):
	return StringNode(toks[1:], toks[0])


def getStringGrammar():
	"""returns a grammar for parsing vizier-like string expressions.
	"""
# XXX TODO: should we cut at =| (which is currently parsed as (= |)?
	simpleOperator = Literal("==") | Literal("!=") | Literal(">=") |\
		Literal(">") | Literal("<=") | Literal("<")
	simpleOperand = Regex(".*")
	simpleExpr = simpleOperator + simpleOperand
	
	commaOperand = Regex("[^,]+")
	barOperand = Regex("[^|]+")
	commaEnum = Literal("=,") + commaOperand + ZeroOrMore(
		Suppress(",") + commaOperand)
	exclusionEnum = Literal("!=,") + commaOperand + ZeroOrMore(
		Suppress(",") + commaOperand)
	barEnum = Literal("=|") + barOperand + ZeroOrMore(
		Suppress("|") + barOperand)
	enumExpr = exclusionEnum | commaEnum | barEnum

	patLiterals = CharsNotIn("[*?")
	wildStar = Literal("*")
	wildQmark = Literal("?")
	setElems = CharsNotIn("]")
	setSpec = Suppress("[") + setElems + Suppress("]")
	pattern = OneOrMore(setSpec | wildStar | wildQmark | patLiterals)

	patternOperator = Literal("~") | Literal("=") | Literal("!~") |\
		Literal("!") | Literal("=")
	patternExpr = patternOperator + pattern

	nakedExpr = pattern.copy()

	stringExpr = enumExpr | simpleExpr | patternExpr | nakedExpr
	
	doc = stringExpr + StringEnd()

	stringExpr.setName("StringExpr")
	enumExpr.setName("EnumExpr")

	debug = False
	stringExpr.setDebug(debug)
	patLiterals.setDebug(debug)

	simpleExpr.setParseAction(_makeOpNode)
	patternExpr.setParseAction(_makeOpNode)
	enumExpr.setParseAction(_makeOpNode)
	nakedExpr.setParseAction(_getNodeFactory("~", StringNode))
	wildStar.setParseAction(_makeOpNode)
	wildQmark.setParseAction(_makeOpNode)
	setElems.setParseAction(_getNodeFactory("[", StringNode))

	return doc


def parseStringExpr(str, baseSymbol=getStringGrammar()):
	return baseSymbol.parseString(str)[0]


parsers = {
	"vexpr-float": parseNumericExpr,
	"vexpr-date": parseDateExpr,
	"vexpr-string": parseStringExpr,
}

def getParserForType(dbtype):
	return parsers.get(dbtype)


def getSQL(field, inPars, sqlPars):
# XXX TODO refactor, sanitize
	try:
		val = inPars[field.get_source()]
		if val!=None:
			if field.get_dbtype().startswith("vexpr") and isinstance(val, basestring):
				return parsers[field.get_dbtype()](val).asSQL(
					field.get_dest(), sqlPars)
			else:
				if isinstance(val, (list, tuple)):
					if len(val)==1 and val[0]==None:
						return ""
					return "%s IN %%(%s)s"%(field.get_dest(), getSQLKey(field.get_dest(),
						val, sqlPars))
				else:
					return "%s=%%(%s)s"%(field.get_dest(), getSQLKey(field.get_dest(),
						val, sqlPars))
	except ParseException:
		raise gavo.ValidationError(
			"Invalid input (see help on search expressions)", field.get_source())


def joinOperatorExpr(operator, operands):
	"""filters empty operands and joins the rest using operator.

	The function returns an expression string or None for the empty expression.
	"""
	operands = filter(None, operands)
	if not operands:
		return None
	elif len(operands)==1:
		return operands[0]
	else:
		return operator.join([" (%s) "%op for op in operands]).strip()


class ToVexprConverter(typesystems.FromSQLConverter):
	typeSystem = "vizerexpr"
	simpleMap = {
		"smallint": "vexpr-float",
		"integer": "vexpr-float",
		"int": "vexpr-float",
		"bigint": "vexpr-float",
		"real": "vexpr-float",
		"float": "vexpr-float",
		"double precision": "vexpr-float",
		"double": "vexpr-float",
		"text": "vexpr-string",
		"char": "vexpr-string",
		"date": "vexpr-date",
		"timestamp": "vexpr-date",
	}

	def mapComplex(self, sqlType, length):
		if sqlType=="char":
			return "vexpr-string"

getVexprFor = ToVexprConverter().convert


def getSQLKey(key, value, sqlPars):
	"""adds value to sqlPars and returns a key for inclusion in a SQL query.

	This function is used to build parameter dictionaries for SQL queries, 
	avoiding overwriting parameters with accidental name clashes.
	It works like this:

	>>> sqlPars = {}
	>>> getSQLKey("foo", 13, sqlPars)
	'foo0'
	>>> getSQLKey("foo", 14, sqlPars)
	'foo1'
	>>> getSQLKey("foo", 13, sqlPars)
	'foo0'
	>>> sqlPars["foo0"], sqlPars["foo1"]; sqlPars = {}
	(13, 14)
	>>> "WHERE foo<%%(%s)s OR foo>%%(%s)s"%(getSQLKey("foo", 1, sqlPars),
	...   getSQLKey("foo", 15, sqlPars))
	'WHERE foo<%(foo0)s OR foo>%(foo1)s'
	"""
	ct = 0
	while True:
		dataKey = "%s%d"%(key, ct)
		if not sqlPars.has_key(dataKey) or sqlPars[dataKey]==value:
			break
		ct += 1
	sqlPars[dataKey] = value
	return dataKey


def _test():
	import doctest, vizierexprs
	doctest.testmod(vizierexprs)


if __name__=="__main__":
	if True:
		_test()
	else:
		print parseStringExpr("NGC*")
