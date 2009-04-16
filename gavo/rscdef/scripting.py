"""
Support code for attaching scripts to objects.
"""

import re
import sys
import weakref

from pyparsing import Word, OneOrMore, ZeroOrMore, QuotedString, Forward,\
	SkipTo, Optional, StringEnd, Regex, LineEnd, Suppress, ParserElement,\
	Literal, White, ParseException, dblQuotedString

from gavo import base
from gavo import utils
from gavo.base import sqlsupport


class Error(base.Error):
	pass


def _getSQLScriptGrammar():
	"""returns a pyparsing ParserElement that splits SQL scripts into
	individual commands.

	The rules are: One statement per line, but linebreaks are ignored
	withing strings and inside of open parens.
	"""
	atom = Forward()
	atom.setName("Atom")

	sqlComment = Literal("--")+SkipTo("\n", include=True)
	cStyleComment = Literal("/*")+SkipTo("*/", include=True)
	comment = sqlComment | cStyleComment

	simpleStr = QuotedString(quoteChar="'", escChar="\\", unquoteResults=False)
	dollarQuoted = Regex(r"(?s)\$(\w*)\$.*?\$\1\$")
	dollarQuoted.setName("dollarQuoted")
	strLiteral = simpleStr | dollarQuoted
	strLiteral.setName("strLiteral")

	parenExpr = "(" + ZeroOrMore( atom | "\n" ) + ")"
	parenExpr.setName("parenExpr")

	other = Regex("[^(')$\n\\\\]+")
	other.setName("other")

	ignoredLinebreak = Suppress(Literal("\\\n"))
	ignoredLinebreak.setName("ignored linebreak")
	literalBackslash = Literal("\\")
	literalDollar = Literal("$") + ~ Literal("$")
	statementEnd = ( Literal('\n') | StringEnd())
	statementEnd.setName("end of line")
	emptyLine = Regex("\\s*\n")
	emptyLine.setName("empty line")

	atom <<  ( ignoredLinebreak | Suppress(comment) | other | strLiteral | 
		parenExpr | literalDollar | literalBackslash )
	statement = OneOrMore(atom) + statementEnd
	statement.setName("statement")
	statement.setParseAction(lambda s, p, toks: " ".join(toks))

	script = OneOrMore( statement | emptyLine ) + StringEnd()
	script.setName("script")
	script.setParseAction(lambda s, p, toks: [t for t in toks.asList()
		if t.strip()])

	if False:
		atom.setDebug(True)
		other.setDebug(True)
		parenExpr.setDebug(True)
		strLiteral.setDebug(True)
		statement.setDebug(True)
		statementEnd.setDebug(True)
		dollarQuoted.setDebug(True)
		literalDollar.setDebug(True)
		literalBackslash.setDebug(True)
		ignoredLinebreak.setDebug(True)
		emptyLine.setDebug(True)
	return script


def getSQLScriptGrammar(memo=[]):
	if not memo:
		memo.append(_getSQLScriptGrammar())
	return memo[0]


class SQLScriptRunner(object):
	"""is an interface to run simple static scripts on the SQL data base.

	The script should be a string containing one command per line.  You
	can use the backslash as a continuation character.  Leading whitespace
	on a continued line is ignored, the linefeed becomes a single blank.

	A leading "-" is ignored for backward compatibility.  It used to
	mean that a command may fail, but that's far too messy until postgres
	grows nested transactions.
	"""
	def _parseScript(self, script):
		queries = []
		for query in getSQLScriptGrammar().parseString(script):
			failOk = False
			if query.startswith("-"):
				failOk = True
				query = query[1:]
			queries.append((failOk, query))
		return queries

	def run(self, script, verbose=False, connection=None):
		"""runs script in a transaction of its own.
		"""
		borrowedConnection = connection is not None
		if not borrowedConnection:
			connection = base.getDefaultDBConnection()
		queries = self._parseScript(script)
		cursor = connection.cursor()
		for ignored, query in queries:
			query = query.strip()
			if not query:
				continue
			if sqlsupport.debug:
				print query
			cursor.execute(query)
		cursor.close()
		if not borrowedConnection:
			connection.commit()
			connection.close()

# XXXXXX TODO: unify with run
	def runBlindly(self, script, querier):
		"""executes all commands of script in sequence without worrying
		about the consequences.

		No rollbacks will be tried, so these scripts should only contain
		commands guaranteed to work (or whose failure indicates the whole
		operation is pointless).  Thus, failOk is ignored.
		"""
		queries = self._parseScript(script)
		for _, query in queries:
			querier.query(query)


class ScriptHandler(object):
	"""is a container for the logic of running scripts.

	Objects like ResourceDescriptors and DataDescriptors can have
	scripts attached that may run at certain points in their lifetime.

	This class provides a uniform interface to them.  Right now,
	the have to be constructed just with a resource descriptor and
	a parent.  I do hope that's enough.
	"""
	def __init__(self, parent, rd):
		self.rd, self.parent = rd, weakref.proxy(parent)

	def _runSqlScript(self, script, connection=None):
		runner = SQLScriptRunner()
		runner.run(script, connection=connection)

	def _runSqlScriptInConnection(self, script, connection):
		"""runs a script in connection.

		For this to work, the caller has to pass in a connection keyword argument
		to runScripts.
		"""
		runner = SQLScriptRunner()
		runner.run(script, connection=connection)

	def _runSqlScriptWithQuerier(self, script, querier):
		"""runs a script blindly using querier.

		Any error conditions will abort the script and leave querier's
		connection invalid until a rollback.
		"""
		SQLScriptRunner().runBlindly(script, querier=querier)

	def _runPythonDDProc(self, script):
		"""compiles and run script to a python function working on a
		data descriptor's table(s).

		The function receives the data descriptor (as dataDesc) and a 
		database connection (as connection) as arguments.  The script only
		contains the body of the function, never the header.
		"""
		def makeFun(script):
			ns = dict(globals())
			code = ("def someFun(dataDesc, connection):\n"+
				utils.fixIndentation(script, "      ")+"\n")
			exec code in ns
			return ns["someFun"]
		makeFun(script)(self.parent, sqlsupport.getDefaultDbConnection())

	def _runPythonTableProc(self, script, **kwargs):
		"""compiles and run script to a python function working on a
		with a tableWriter.

		The function receives the TableDef and the TableWriter as recDef and
		tw arguments.  The script only contains the body of the function, never 
		the header.
		"""
		def makeFun(script):
			ns = dict(globals())
			code = ("def someFun(recDef, tw):\n"+
				utils.fixIndentation(script, "      ")+"\n")
			exec code in ns
			return ns["someFun"]
		makeFun(script)(self.parent, **kwargs)

	handlers = {
		"preCreation": _runSqlScript,
		"postCreation": _runSqlScript,
		"processTable": _runPythonDDProc,
		"preIndex": _runPythonTableProc,
		"preIndexSQL": _runSqlScriptInConnection,
		"afterDrop": _runSqlScriptInConnection,
		"viewCreation": _runSqlScriptWithQuerier,
	}
	
	def _runScript(self, script, macroExpander, **kwargs):
		source = macroExpander.expand(script.content_)
		self.handlers[script.type](self, source, **kwargs)

	def runScripts(self, waypoint, macroExpander, **kwargs):
		for script in self.parent.scripts:
			if script.type==waypoint:
				self._runScript(script, macroExpander, **kwargs)


class Script(base.Structure):
	"""A script, i.e., some executable item within a resource descriptor.

	The content of scripts is given by their type -- usually, they are
	either python scripts or SQL with special rules for breaking the
	script into individual statements (which are basically like python's).

	See `Scripting`_.
	"""
	name_ = "script"
	typeDesc_ = "Embedded executable code with a type definition"

	_type = base.EnumeratedUnicodeAttribute("type", base.Undefined,
		description="Type of the script.", 
		validValues=ScriptHandler.handlers.keys(), copyable=True)
	_name = base.UnicodeAttribute("name", default="anonymous",
		description="A human-consumable designation of the script.",
		copyable=True)
	_content = base.DataContent(copyable=True, description="The script body.")


class ScriptingMixin(object):
	"""can be mixed into objects wanting to support scripting.

	The objects have to define a set (or similar) validWaypoints defining
	what waypoints they'll call, must behave like they are Records sporting a 
	ListField "scripts", and must have their resource descriptor in the
	rd attribute.
	"""
	_scripts = base.StructListAttribute("scripts", childFactory=Script,
		description="Code snippets attached to this object.  See Scripting_ .",
		copyable=True)

	def __getScriptHandler(self):
		try:
			return self.__scriptHandler
		except AttributeError:
			self.__scriptHandler = ScriptHandler(self, self.rd)
			return self.__getScriptHandler()

	def __getMacroExpander(self):
		try:
			return self.__macroExpander
		except AttributeError:
			self.__macroExpander = self.getPackage().getExpander()
			return self.__getMacroExpander()

	def runScripts(self, waypoint, **kwargs):
		self.__getScriptHandler().runScripts(waypoint, 
			self.__getMacroExpander(), **kwargs)

	def getPackage(self):
		"""returns a macro package for this object.

		If you mix in MacroPackage into the class that supports scripts,
		this default implementation will do, otherwise you'll have to
		override it.
		"""
		return self

	def hasScript(self, waypoint):
		"""returns True if there is at least one script for waypoint
		on this object.
		"""
		for script in self.scripts:
			if script.type==waypoint:
				return True
		return False
