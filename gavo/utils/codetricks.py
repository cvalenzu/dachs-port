"""
Functions dealing with compilation and introspection of python and 
external code.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

import compiler
import compiler.ast
import imp
import itertools
import os
import re
import shutil
import string
import sys
import tempfile
import weakref

from gavo.utils import algotricks
from gavo.utils import excs


class CachedGetter(object):
	"""A cache for a callable.

	This is basically memoization, except that these are supposed to be
	singletons;  CachedGetters should be used where the construction of
	a resource (e.g., a grammar) should be deferred until it is actually
	needed to save on startup times.

	The resource is created on the first call, all further calls just return
	references to the original object.

	You can also leave out the getter argument and add an argumentless method 
	impl computing the value to cache.
	"""
	def __init__(self, getter, *args, **kwargs):
		if getter is None:
			getter = self.impl
		self.cache, self.getter = None, getter
		self.args, self.kwargs = args, kwargs
	
	def __call__(self):
		if self.cache is None:
			self.cache = self.getter(*self.args, **self.kwargs)
			del self.args
			del self.kwargs
		return self.cache


class CachedResource(object):
	"""is like CachedGetter but with a built-in getter.

	Here, you define your class and have a class method impl returning
	what you want.
	"""
	cache = None

	@classmethod 
	def __new__(cls, arg):
		if cls.cache is None:
			cls.cache = cls.impl()
		return cls.cache


class IdManagerMixin(object):
	"""A mixin for objects requiring unique IDs.

	The primaray use case is XML generation, where you want stable IDs
	for objects, but IDs must be unique over an entire XML file.

	The IdManagerMixin provides three methods for doing that:
	
	* makeIdFor(object) -- returns an id for object, or None if makeIdFor has
	  already been called for that object (i.e., it presumable already is
		in the document).
	* getIdFor(object) -- returns an id for object if makeIdFor has already
	  been called before.  Otherwise, a NotFoundError is raised
	* getForId(id) -- returns the object belonging to an id that has
	  been handed out before.  Raises a NotFoundError for unknown ids.
	"""
# Return a proxy instead of raising a KeyError here?  We probably no not
# really want to generate xml with forward references, but who knows?
	def __getIdMaps(self):
		try:
			return self.__objectToId, self.__idsToObject
		except AttributeError:
			self.__objectToId, self.__idsToObject = {}, {}
			return self.__objectToId, self.__idsToObject

	def _fixSuggestion(self, suggestion, invMap):
		for i in itertools.count():
			newId = suggestion+str(i)
			if newId not in invMap:
				return newId

	def makeIdFor(self, ob, suggestion=None):
		map, invMap = self.__getIdMaps()
		if id(ob) in map:
			return None

		if suggestion is not None: 
			if suggestion in invMap:
				newId = self._fixSuggestion(suggestion, invMap)
			else:
				newId = suggestion
		else:
			newId = intToFunnyWord(id(ob))

		# register id(ob) <-> newId map, avoiding refs to ob
		map[id(ob)] = newId
		try:
			invMap[newId] = weakref.proxy(ob)
		except TypeError:  # something we can't weakref to
			invMap[newId] = ob
		return newId
	
	def getIdFor(self, ob):
		try:
			return self.__getIdMaps()[0][id(ob)]
		except KeyError:
			raise excs.NotFoundError(repr(ob), what="object",
				within="id manager %r"%(self,), hint="Someone asked for the"
				" id of an object not managed by the id manager.  This usually"
				" is a software bug.")

	def getForId(self, id):
		try:
			return self.__getIdMaps()[1][id]
		except KeyError:
			raise excs.NotFoundError(id, what="id", within="id manager %r"%(self,),
				hint="Someone asked for the object belonging to an id that has"
				" been generated externally (i.e., not by this id manager).  This"
				" usually is an internal error of the software.")


def _iterDerivedClasses(baseClass, objects):
	"""iterates over all subclasses of baseClass in the sequence objects.
	"""
	for cand in objects:
		try:
			if issubclass(cand, baseClass) and cand is not baseClass:
				yield cand
		except TypeError:  # issubclass wants a class
			pass


def buildClassResolver(baseClass, objects, instances=False,
		key=lambda obj: getattr(obj, "name", None), default=None):
	"""returns a function resolving classes deriving from baseClass
	in the sequence objects by their names.

	This is used to build registries of Macros and RowProcessors.  The
	classes in question have to have a name attribute.

	objects would usually be something like globals().values()

	If instances is True the function will return instances instead
	of classes.

	key is a function taking an object and returning the key under which
	you will later access it.  If this function returns None, the object
	will not be entered into the registry.
	"""
	if instances:
		registry = algotricks.DeferringDict()
	else:
		registry = {}
	for cls in _iterDerivedClasses(baseClass, objects):
		clsKey = key(cls)
		if clsKey is not None:
			registry[clsKey] = cls
	def resolve(name, registry=registry):
		try:
			return registry[name]
		except KeyError:
			if default is not None:
				return default
			raise
	return resolve


def formatDocs(docItems, underliner):
	"""returns RST-formatted docs for docItems.

	docItems is a list of (title, doc) tuples.  doc is currently
	rendered in a preformatted block.
	"""
	def formatDocstring(docstring):
		"""returns a docstring with a consistent indentation.

		Rule (1): any whitespace in front of the first line is discarded.
		Rule (2): if there is a second line, any whitespace at its front
		  is the "governing whitespace"
		Rule (3): any governing whitespace in front of the following lines
		  is removed
		Rule (4): All lines are indented by 2 blanks.
		"""
		lines = docstring.split("\n")
		newLines = [lines.pop(0).lstrip()]
		if lines:
			whitespacePat = re.compile("^"+re.match(r"\s*", lines[0]).group())
			for line in lines:
				newLines.append(whitespacePat.sub("", line))
		return "  "+("\n  ".join(newLines))

	docLines = []
	for title, body in docItems:
		docLines.extend([title, underliner*len(title), "", "::", "",
			formatDocstring(body), ""])
	docLines.append("\n.. END AUTO\n")
	return "\n".join(docLines)


def makeClassDocs(baseClass, objects):
	"""prints hopefully RST-formatted docs for all subclasses
	of baseClass in objects.

	The function returns True if it finds arguments it expects ("docs"
	and optionally a char to build underlines from) in the command line,
	False if not (and it doesn't print anything in this case) if not.

	Thus, you'll usually use it like this:

	if __name__=="__main__":	
		if not makeClassDocs(Macro, globals().values()):
			_test()
	"""
	if len(sys.argv) in [2,3] and sys.argv[1]=="docs":
		if len(sys.argv)==3:
			underliner = sys.argv[2][0]
		else:
			underliner = "."
	else:
		return False
	docs = []
	for cls in _iterDerivedClasses(baseClass, objects):
		try:
			title = cls.name
		except AttributeError:
			title = cls.__name__
		docs.append((title, cls.__doc__))
	docs.sort()
	print formatDocs(docs, underliner)
	return True


def silence(fun, *args, **kwargs):
	"""executes fun(*args, **kwargs) with stdout redirected to /dev/null.

	This would be a classic for context managers once we have python 2.5.

	This is necessary to shut up silly output from libraries like pyparsing
	and pyfits.
	"""
	realstdout = sys.stdout
	sys.stdout = open("/dev/null", "w")
	try:
		res = fun(*args, **kwargs)
	finally:
		sys.stdout.close()
		sys.stdout = realstdout
	return res


def runInSandbox(setUp, func, tearDown, *args, **kwargs):
	"""runs func in a temporary ("sandbox") directory.

	func is called with args and kwargs.  setUp and tearDown are
	two functions also called with args and kwargs; in addition, they
	are passed the path of the tempdir (setUp) or the path of the
	original directory (teardown) in the first argument.
	
	setUp is called after the directory has been created,
	but the process is still in the current WD.
	
	tearDown is called before the temp dir is deleted and in this directory.
	Its return value is the return value of runInSandbox, which is the
	preferred way of getting data out of the sandbox.

	If any of the handlers raise exceptions, the following handlers will not
	be called.  The sandbox will be torn down, though.
	"""
	owd = os.getcwd()
	wd = tempfile.mkdtemp("sandbox")
	try:
		if setUp:
			setUp(wd, *args, **kwargs)
		os.chdir(wd)
		func(*args, **kwargs)
		result = tearDown(owd, *args, **kwargs)
	finally:
		os.chdir(owd)
		shutil.rmtree(wd)
	return result


def compileFunction(src, funcName, useGlobals=None):
	"""runs src through exec and returns the item funcName from the resulting
	namespace.

	This is typically used to define functions, like this:
	>>> resFunc = compileFunction("def f(x): print x", "f")
	>>> resFunc(1); resFunc("abc")
	1
	abc
	"""
	locals = {}
	if useGlobals is None:
		useGlobals = globals()
	try:
		exec src in useGlobals, locals
	except:
		sys.stderr.write("Bad code:\n%s\n"%src)
		raise
	return locals[funcName]


def ensureExpression(expr, errName="unknown"):
	"""raises a LiteralParserError if expr is not a parseable python expression.
	"""
	# bizarre bug in the compiler modules: naked strings are compiled into
	# just a module name.  Fix it by forcing an expression on those:
	if expr.startswith("'") or expr.startswith('"'):
		expr = "''+"+expr
	try:
		ast = compiler.parse(expr)
	except SyntaxError, msg:
		raise excs.BadCode(expr, "expression", msg)
	# An ast for an expression is a Discard inside at Stmt inside the
	# top-level Module
	try:
		exprNodes = ast.node.nodes
		if len(exprNodes)!=1:
			raise ValueError("Not a single statement")
		if not isinstance(exprNodes[0], compiler.ast.Discard):
			raise ValueError("Not an expression")
	except (ValueError, AttributeError), ex:
		raise excs.BadCode(expr, "expression", ex)


def loadPythonModule(fqName):
	"""imports fqName and returns the module with a module description.

	The module description is what what find_module returns.

	fqName is a fully qualified path to the module without the .py.
	"""
	moduleName = os.path.basename(fqName)
	modpath = os.path.dirname(fqName)
	moddesc = imp.find_module(moduleName, [modpath])
	try:
		imp.acquire_lock()
		modNs = imp.load_module(moduleName, *moddesc)
	finally:
		imp.release_lock()
	return modNs, moddesc


def memoized(origFun):
	"""is a very simple memoizing decorator.

	Beware: This decorator is signature-changing (the resulting function will
	accept all positional arguments, but no keyword arguments, only to
	TypeError out when the original function is called.
	"""
	cache = {}
	def fun(*args):
		if args not in cache:
			cache[args] = origFun(*args)
		return cache[args]
	return fun


def document(origFun):
	"""is a decorator that adds a "buildDocsForThis" attribute to its argument.

	This attribute is evaluated by documentation generators.
	"""
	origFun.buildDocsForThis = True
	return origFun


def identity(x):
	return x


def intToFunnyWord(anInt, translation=string.maketrans(
		"-0123456789abcdef", 
		"zaeiousmnthwblpgd")):
	"""returns a sometimes funny (but unique) word from an arbitrary integer.
	"""
	return "".join(reversed(("%x"%anInt).translate(translation)))


def addDefaults(dataDict, defaultDict):
	"""adds key-value pairs from defaultDict to dataDict if the key is missing
	in dataDict.
	"""
	for key, value in defaultDict.iteritems():
		if key not in dataDict:
			dataDict[key] = value


def _test():
	import doctest, codetricks
	doctest.testmod(codetricks)


if __name__=="__main__":
	_test()
