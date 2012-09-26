# -*- coding: iso-8859-1 -*-
"""
Tests for grammars and their helpers.
"""

import datetime
import os
import struct
from cStringIO import StringIO

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.grammars import binarygrammar
from gavo.grammars import columngrammar
from gavo.grammars import common
from gavo.grammars import fitsprodgrammar
from gavo.grammars import regrammar
from gavo.helpers import testtricks



class PredefinedRowfilterTest(testhelpers.VerboseTest):
	def testOnIndex(self):
		dd = testhelpers.getTestRD().getById("expandOnIndex")
		data = rsc.makeData(dd, forceSource=[{"b": 3, "c": 4, "a": "eins"}])
		self.assertEqual(data.getPrimaryTable().rows,
			[{'a': u'eins', 'c': 4, 'b': 3, 'd': 3}, 
				{'a': u'eins', 'c': 4, 'b': 3, 'd': 4}])

	def testDateRange(self):
		dd = testhelpers.getTestRD().getById("expandOnDate")
		data = rsc.makeData(dd, forceSource=[{"start": datetime.date(2000, 5, 8), 
				"end": datetime.date(2000, 5, 10), "a": "line1"},
			{"start": datetime.date(2005, 5, 8), 
			"end": datetime.date(2005, 5, 8), "a": "line2"},])
		self.assertEqual(data.getPrimaryTable().rows, [
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 8, 0, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 8, 12, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 9, 0, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 9, 12, 0)},
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 10, 0, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 10, 12, 0)}, 
			{'a': u'line2', 'e': datetime.datetime(2005, 5, 8, 0, 0)}, 
			{'a': u'line2', 'e': datetime.datetime(2005, 5, 8, 12, 0)}])

	def testDateRangeDefault(self):
		dd = testhelpers.getTestRD().getById("expandOnDateDefault")
		data = rsc.makeData(dd, forceSource=[{"start": datetime.date(2000, 5, 8), 
				"end": datetime.date(2000, 5, 9), "a": "line1"},
			{"start": datetime.date(2005, 5, 8), 
			"end": datetime.date(2005, 5, 8), "a": "line2"},])
		self.assertEqual(data.getPrimaryTable().rows, [
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 8, 0, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 9, 0, 0)}, 
			{'a': u'line2', 'e': datetime.datetime(2005, 5, 8, 0, 0)}])

	def testExpandComma(self):
		dd = testhelpers.getTestRD().getById("expandComma")
		data = rsc.makeData(dd, forceSource=[{"stuff": "x,yz,foo, bar ",
			"b": 23}, {"stuff":"quux", "b": 3}])
		self.assertEqual(data.getPrimaryTable().rows, [
			{'a': u'x', 'b': 23}, {'a': u'yz', 'b': 23}, 
			{'a': u'foo', 'b': 23}, {'a': u'bar', 'b': 23}, 
			{'a': u'quux', 'b': 3}])


class SequencedRowfilterTest(testhelpers.VerboseTest):
	def _makeGrammar(self, rowgenDefs):
		return base.parseFromString(rscdef.getGrammar("dictlistGrammar"), 
			"<dictlistGrammar>%s</dictlistGrammar>"%rowgenDefs)

	def _getProcessedFor(self, filterDefs, input):
		g = self._makeGrammar(filterDefs)
		res = list(g.parse(input))
		for row in res:
			del row["parser_"]
		return res

	def testSimplePipe(self):
		res = self._getProcessedFor("""
			<rowfilter><code>
					row["output"] = row["input"]+1
					del row["input"]
					yield row
			</code></rowfilter>
			<rowfilter><code>
					row["processed"] = row["output"]*row["output"]
					yield row
			</code></rowfilter>""", [{"input": 2}])
		self.assertEqual(res, [{"output":3, "processed":9}])
	
	def testForking(self):
		res = self._getProcessedFor("""
			<rowfilter><code>
					b = row["input"]
					del row["input"]
					row["output"] = b
					yield row.copy()
					row["output"] += b
					yield row
			</code></rowfilter>
			<rowfilter><code>
					row["processed"] = row["output"]*row["output"]
					yield row.copy()
					row["processed"] = row["processed"]*row["output"]
					yield row
			</code></rowfilter>""", [{"input": 2}])
		self.assertEqual(res, [
			{"output":2, "processed":4},
			{"output":2, "processed":8},
			{"output":4, "processed":16},
			{"output":4, "processed":64},])


ignoreTestData = [
	{'a': 'xy', 'b': 'cc', 'd': 'yok'},
	{'a': 'xy', 'b': 'DD'},
	{'a': 'zz', 'b': ''},
	]

class IgnoreTests(testhelpers.VerboseTest):
	def _makeGrammar(self, ignoreClauses):
		return base.parseFromString(rscdef.getGrammar("dictlistGrammar"), 
			"<dictlistGrammar><ignoreOn>%s</ignoreOn></dictlistGrammar>"%
				ignoreClauses)

	def _makeBailingGrammar(self, ignoreClauses):
		return base.parseFromString(rscdef.getGrammar("dictlistGrammar"), 
			"<dictlistGrammar><ignoreOn bail='True'>%s</ignoreOn></dictlistGrammar>"%
				ignoreClauses)

	def _assertResultLen(self, ignoreClauses, expectedLength):
		res = list(self._makeGrammar(ignoreClauses).parse(ignoreTestData))
		self.assertEqual(len(res), expectedLength, 
			"%s yielded %s, expected %d rows"%(ignoreClauses, res, expectedLength))

	def testKeyIs(self):
		self._assertResultLen('<keyIs key="a" value="xy"/>', 1)
		self._assertResultLen('<keyIs key="a" value="zz"/>', 2)
		self._assertResultLen('<keyIs key="a" value=""/>', 3)
		self._assertResultLen('<keyIs key="b" value=""/>', 2)
		self._assertResultLen('<keyIs key="d" value="yok"/>', 2)

	def testKeyPresent(self):
		self._assertResultLen('<keyPresent key="a"/>', 0)
		self._assertResultLen('<keyPresent key="b"/>', 0)
		self._assertResultLen('<keyPresent key="d"/>', 2)
		self._assertResultLen('<keyPresent key="yikes"/>', 3)

	def testTriggerSeq(self):
		self._assertResultLen('<keyPresent key="d"/><keyIs key="b" value=""/>'
			, 1)

	def testNot(self):
		self._assertResultLen('<not><keyPresent key="a"/></not>', 3)
		self._assertResultLen('<not><keyPresent key="d"/></not>', 1)
		self._assertResultLen('<not><keyPresent key="d"/>'
			'<keyIs key="b" value=""/></not>', 2)
	
	def testAnd(self):
		self._assertResultLen('<and><keyIs key="a" value="xy"/>'
			'<keyIs key="b" value="DD"/></and>', 2)

	def testBail(self):
		g = self._makeBailingGrammar('<keyMissing key="d"/>')
		def parseAll():
			return list(g.parse(ignoreTestData))
		self.assertRaises(rscdef.TriggerPulled, parseAll)
	
	def testBailNot(self):
		g = self._makeBailingGrammar('<keyMissing key="a"/>')
		list(g.parse(ignoreTestData))


class EmbeddedGrammarTest(testhelpers.VerboseTest):
	def testSimple(self):
		from gavo import rscdesc
		rd = base.parseFromString(rscdesc.RD, 
			"""<resource schema="test"><data id="fake"><embeddedGrammar>
				<iterator><code>
					yield {'x': 1, 'y': 2}
					yield {'x': 2, 'y': 2}
				</code></iterator></embeddedGrammar></data></resource>""")
		self.assertEqual(list(rd.dds[0].grammar.parse(None)),
			[{'y': 2, 'x': 1}, {'y': 2, 'x': 2}])


class KVGrammarTest(testhelpers.VerboseTest):
	def testSimple(self):
		grammar = base.parseFromString(rscdef.getGrammar("keyValueGrammar"),
			'<keyValueGrammar commentPattern="--.*?\*/" enc="utf-8"/>')
		rec = list(grammar.parse(StringIO("a=b\nc=2 --nothing*/\n"
			"wonk�:N�rd".decode("iso-8859-1").encode("utf-8"))))[0]
		self.assertEqual(rec["a"], 'b')
		self.assertEqual(rec["c"], '2')
		self.assertEqual(rec[u"wonk�"], u'N�rd')
	
	def testPairs(self):
		grammar = base.parseFromString(rscdef.getGrammar("keyValueGrammar"),
			'<keyValueGrammar kvSeparators="/" pairSeparators="%"'
			' yieldPairs="True"/>')
		recs = [(v['key'], v['value']) 
			for v in grammar.parse(StringIO("a/b%c/d"))]
		self.assertEqual(recs, [('a', 'b'), ('c', 'd')])

	def testError(self):
		self.assertRaisesWithMsg(base.LiteralParseError,
			"At [<keyValueGrammar commentPat...], (1, 0):"
			" '**' is not a valid value for commentPattern",
			base.parseFromString, 
			(rscdef.getGrammar("keyValueGrammar"),
			'<keyValueGrammar commentPattern="**"/>'))


class ColDefTest(testhelpers.VerboseTest):
	def testSimple(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			'<columnGrammar colDefs="a:1 B:2-5 C_dfoo:4 _gobble:6-8"/>')
		res = list(g.parse(StringIO("abcdefghijklmnoq")))[0]
		del res["parser_"]
		self.assertEqual(res, {'a': 'a', 'C_dfoo': 'd', 'B': 'bcde', 
			'_gobble': 'fgh'})

	def testFunkyWhite(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			'<columnGrammar colDefs="a :1 B: 2 - 5 C_dfoo: 4 _gobble : 6 -8"/>')
		res = list(g.parse(StringIO("abcdefghijklmnoq")))[0]
		del res["parser_"]
		self.assertEqual(res, {'a': 'a', 'C_dfoo': 'd', 'B': 'bcde', 
			'_gobble': 'fgh'})
	
	def testHalfopen(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			'<columnGrammar><colDefs>a:5- B:-5</colDefs></columnGrammar>')
		res = list(g.parse(StringIO("abcdefg")))[0]
		del res["parser_"]
		self.assertEqual(res, {'a': 'efg', 'B': 'abcde'})

	def testBeauty(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			"""<columnGrammar><colDefs>
				a:      5- 
				B:      -5
				gnugga: 1-2
				</colDefs></columnGrammar>""")
		res = list(g.parse(StringIO("abcdefg")))[0]
		del res["parser_"]
		self.assertEqual(res, {'a': 'efg', 'B': 'abcde', 'gnugga': 'ab'})

	def testErrorBadChar(self):
		self.assertRaisesWithMsg(base.LiteralParseError,
			"At [<columnGrammar><colDefs>a:5...], (1, 34):"
			" 'a:5-% B:-5' is not a valid value for colDefs",
			base.parseFromString, (columngrammar.ColumnGrammar,
			'<columnGrammar><colDefs>a:5-% B:-5</colDefs></columnGrammar>'))
	
	def testErrorNiceHint(self):
		try:
			base.parseFromString(columngrammar.ColumnGrammar,
				'<columnGrammar><colDefs>a:5- B:c</colDefs></columnGrammar>')
		except base.LiteralParseError, ex:
			self.failUnless(ex.hint.endswith(
				"Expected end of text (at char 5), (line:1, col:6)"))
		else:
			self.fail("LiteralParseError not raised")
		 

class BinaryRecordTest(testhelpers.VerboseTest):
	def testTypes(self):
		brd = base.parseFromString(binarygrammar.BinaryRecordDef,
			"""<binaryRecordDef binfmt="packed">
				chr(1s) fong(12s) b(b) B(B) h(h) H(H) i(i) I(I) q(q) Q(Q)
				f(f) d(d)</binaryRecordDef>""")
		self.assertEqual(brd.structFormat, "=1s12sbBhHiIqQfd")
		self.assertEqual(brd.recordLength, 55)

	def testBadIdentifier(self):
		self.assertRaises(base.LiteralParseError,
			base.parseFromString, binarygrammar.BinaryRecordDef,
			"<binaryRecordDef>22s(d)</binaryRecordDef>")

	def testBadCode(self):
		self.assertRaises(base.LiteralParseError,
			base.parseFromString, binarygrammar.BinaryRecordDef,
			"<binaryRecordDef>x(P)</binaryRecordDef>")

	def testNativeTypes(self):
		brd = base.parseFromString(binarygrammar.BinaryRecordDef,
			"<binaryRecordDef>c(1s)s(i)t(d)</binaryRecordDef>")
		self.assertEqual(brd.structFormat, "1sid")
		self.failIf(brd.recordLength==13, "You platform doesn't pack?")


class BinaryGrammarTest(testhelpers.VerboseTest):
	plainTestData = [(42, 0.25), (-30, 40.)]
	plainExpectedResult = [{'s': 42, 't': 0.25}, {'s': -30, 't': 40.0}]

	def testUnarmoredParse(self):
		inputFile = StringIO("u"*20+"".join(struct.pack("id", *r) 
			for r in self.plainTestData))
		grammar = base.parseFromString(binarygrammar.BinaryGrammar,
			"""<binaryGrammar skipBytes="20"><binaryRecordDef>s(i)t(d)
			</binaryRecordDef></binaryGrammar>""")
		self.assertEqual(
			list(grammar.parse(inputFile)),
			self.plainExpectedResult)

	def testNetworkBinfmt(self):
		inputFile = StringIO("".join(struct.pack("!id", *r) 
			for r in self.plainTestData))
		grammar = base.parseFromString(binarygrammar.BinaryGrammar,
			"""<binaryGrammar><binaryRecordDef binfmt="big">s(i)t(d)
			</binaryRecordDef></binaryGrammar>""")
		self.assertEqual(
			list(grammar.parse(inputFile)),
			self.plainExpectedResult)


	def testFortranParse(self):

		def doFortranArmor(data):
			return struct.pack("i%dsi"%len(data), len(data), data, len(data))

		inputFile = StringIO("".join(doFortranArmor(struct.pack("id", *r))
			for r in self.plainTestData))
		grammar = base.parseFromString(binarygrammar.BinaryGrammar,
			"""<binaryGrammar armor="fortran"><binaryRecordDef>s(i)t(d)
			</binaryRecordDef></binaryGrammar>""")
		self.assertEqual(
			list(grammar.parse(inputFile)),
			self.plainExpectedResult)


class FITSProdGrammarTest(testhelpers.VerboseTest):

	sample = os.path.join(base.getConfig("inputsDir"), "data", "ex.fits")
	grammarT = fitsprodgrammar.FITSProdGrammar

	def _getParse(self, grammarDef):
		grammar = base.parseFromString(self.grammarT, grammarDef)
		return list(grammar.parse(self.sample))[0]

	def _assertBasicFieldsPresent(self, d):
		self.assertEqual(len(d), 104)
		self.assertEqual(d["EXTEND"], True)
		self.assertEqual(d["OBSERVER"], "M.Wolf")
		self.assertEqual(d["LATPOLE"], 0.0)
		self.failUnless("PLATE_ID" in d)

	def testBasic(self):
		self._assertBasicFieldsPresent(
			self._getParse("""<fitsProdGrammar qnd="False"/>"""))

	def testBasicQnD(self):
		self._assertBasicFieldsPresent(
			self._getParse("""<fitsProdGrammar/>"""))

	def testNameMapping(self):
		d = self._getParse("""<fitsProdGrammar><mapKeys><map
			dest="blind">EXPTIME</map></mapKeys></fitsProdGrammar>""")
		self.assertEqual(d["blind"], '10801')
	
	def testHDUsField(self):
		d = self._getParse("""<fitsProdGrammar hdusField="__HDUS"/>""")
		self.assertEqual(d["__HDUS"][0].data[0][0], 7896.0)


class ReGrammarTest(testhelpers.VerboseTest):
	def testBadInputRejection(self):
		grammar = base.parseFromString(regrammar.REGrammar,
			"""<reGrammar names="a,b"/>""")
		self.assertRaisesWithMsg(base.SourceParseError,
			"At line 2: Only 1 fields found, expected 2",
			lambda: list(grammar.parse(StringIO("1 2\n3"))),
			())
	

class FilteredInputTest(testhelpers.VerboseTest):
	def testSimple(self):
		with testtricks.testFile("filterInput", "ab\ncd\nef\n") as srcName:
			f = common.FilteredInputFile("tac", open(srcName))
			self.assertEqual(f.read(), "ef\ncd\nab\n")
			f.close()

	def testLargeOutput(self):
		data = "                    \n"*200000
		with testtricks.testFile(
				"filterInput", data, writeGz=True) as srcName:
			f = common.FilteredInputFile("zcat", open(srcName))
			result = f.read()
			self.assertEqual(result, data)
			f.close()

	def testLargeInput(self):
		inF = StringIO("                    \n"*200000)
		f = common.FilteredInputFile("gzip", inF)
		result = f.read()
		self.assertEqual(len(result), 10216)
		f.close()

	def testFailedCommand(self):
		f = common.FilteredInputFile("verpotshket", StringIO("abc"),
			silent=True)
		self.assertRaisesWithMsg(IOError,
			"Child exited with return code 127",
			f.read,
			())

	def testReadWithSizeAndClose(self):
		f = common.FilteredInputFile("yes", StringIO("abc"))
		self.assertEqual("y\n"*10, f.read(20))
		f.close()
		self.assertEqual(f.process.returncode, -15)

	def testReadline(self):
		f = common.FilteredInputFile("zcat", StringIO(
			"H4sIAFcmV1AAA0vkSgQCMDHcABcXAN3p7JLdAAAA".decode("base64")))
		self.assertEqual(f.readline(), "a\n")
		self.assertEqual(f.readline(), "aaaa\n")
		self.assertEqual(f.readline(), "a"*212+"\n")
		self.assertEqual(f.readline(), "\n")
		self.assertEqual(f.readline(), "")

	def testReadlineNoLF(self):
		f = common.FilteredInputFile("cat", StringIO(
			"AAAA\nBBBB"))
		self.assertEqual(f.readline(), "AAAA\n")
		self.assertEqual(f.readline(), "BBBB")


if __name__=="__main__":
	testhelpers.main(FilteredInputTest)
