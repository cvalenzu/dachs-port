"""
Tests for function definitions and applications.
"""

from gavo import base
from gavo.rscdef import macros
from gavo.rscdef import procdef

import testhelpers


class TestApp(procdef.ProcApp):
	name_ = "testApp"
	requiredType = "t_t"
	formalArgs = "source, dest"


class Foo(base.Structure, macros.MacroPackage):
	name_ = "foo"
	_apps = base.StructListAttribute("apps", childFactory=TestApp)
	_defs = base.StructListAttribute("defs", childFactory=procdef.ProcDef)
	def __init__(self, parent, **kwargs):
		base.Structure.__init__(self, parent, **kwargs)
		self.source, self.dest = {}, {}

	def onElementComplete(self):
		self._cApps = [a.compile() for a in self.apps]
		self._onElementCompleteNext(Foo)

	def runApps(self):
		for a in self._cApps:
			a(self.source, self.dest)

	def macro_foobar(self):
		return "Foobar"
	def macro_mesmerize(self, arg):
		return "".join(reversed(list(arg)))


class NoDefTest(testhelpers.VerboseTest):
	"""tests for ProcApps without procDefs.
	"""
	def testVerySimple(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'/></foo>")
		f.runApps()
		self.assertEqual(f.dest, {})
	
	def testDoesSomething(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>"
			"\t\tdest['fobba'] = source</code></testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {"fobba": {}})
	
	def testMultiline(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>\n"
			"\t\tfor i in range(source['count']):\n"
			"\t\t\tdest[i] = 42-i</code></testApp></foo>")
		f.source["count"] = 2
		f.runApps()
		self.assertEqual(f.dest, {0: 42, 1: 41})
	
	def testWithParSetup(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>\n"
			"\t\tfor i in range(count):\n"
			"\t\t\tdest[i] = 42-i</code>\n"
			"<setup><par key='count'>2</par></setup>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {0: 42, 1: 41})

	def testWithParAndBinding(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>\n"
			"\t\tfor i in range(count):\n"
			"\t\t\tdest[i] = 42-i</code>\n"
			"<setup><par key='count'/></setup><bind key='count'>2</bind>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {0: 42, 1: 41})

	def testUnboundFails(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"Parameter count is not defaulted in x and thus must be bound.",
			base.parseFromString, (Foo, "<foo><testApp name='x'><code>\n"
			"\t\tfor i in range(count):\n"
			"\t\t\tdest[i] = 42-i</code>\n"
			"<setup><par key='count'/></setup>"
			"</testApp></foo>"))

	def testBadKeyFails(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"Bad key for procedure argument: ''",
			base.parseFromString, (Foo, "<foo><testApp name='x'>"
			"<setup><par key=''/></setup>"
			"</testApp></foo>"))
		self.assertRaisesWithMsg(base.StructureError, 
			"Bad key for procedure argument: 'a key'",
			base.parseFromString, (Foo, "<foo><testApp name='x'>"
			"<setup><par key='a key'/></setup>"
			"</testApp></foo>"))
	
	def testWithMacros(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>\n"
			r"dest[\foobar] = weird+'\\\\n'</code>"
			r"<setup><par key='weird'>'\mesmerize{something}'</par>"
			"<par key='Foobar'>'res'</par></setup>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {'res': r'gnihtemos\n'})
	
	def testParentPresent(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>"
			"\t\tdest['isRight'] = 'runApps' in dir(parent)</code></testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {"isRight": True})


class WithDefTest(testhelpers.VerboseTest):
	def testSimpleDef(self):
		f = base.parseFromString(Foo, "<foo><procDef type='t_t' id='b'>"
			"<code>dest['par']='const'</code></procDef>"
			"<testApp name='x' procDef='b'/>"
			"</foo>")
		f.runApps()
		self.assertEqual(f.dest, {"par": 'const'})

	def testPDDefaulting(self):
		f = base.parseFromString(Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'>'const'</par></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'/>"
			"</foo>")
		f.runApps()
		self.assertEqual(f.dest, {"par": 'const'})

	def testPDRebinding(self):
		f = base.parseFromString(Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'>'const'</par></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'><bind key='par'>'noconst'</bind>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {"par": 'noconst'})

	def testFilling(self):
		f = base.parseFromString(Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'/></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'><bind key='par'>'noconst'</bind>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {"par": 'noconst'})

	def testNoFillRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			"Parameter par is not defaulted in x and thus must be bound.",
			base.parseFromString, (Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'/></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'>"
			"</testApp></foo>"))

	def testFillRandomRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			"May not bind non-existing parameter(s) random.",
			base.parseFromString, (Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'/></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'><bind key='random'>'noconst'</bind>"
			"<bind key='par'>4</bind>"
			"</testApp></foo>"))
	
# Test mixing for setups here?  I don't think so, it's rather cranky anyway.

if __name__=="__main__":
	testhelpers.main(WithDefTest)
