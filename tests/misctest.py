"""
Some unit tests not yet fitting anywhere else.
"""

from cStringIO import StringIO
import datetime
import new
import os
import shutil
import sys
import tempfile
import unittest

import numpy

from gavo import base
from gavo import helpers
from gavo import rscdef
from gavo import rscdesc
from gavo import stc
from gavo import utils
from gavo.base import valuemappers
from gavo.helpers import filestuff
from gavo.utils import pyfits
from gavo.utils import stanxml

import testhelpers


class MapperTest(unittest.TestCase):
	"""collects tests for votable/html value mappers.
	"""
	def testJdMap(self):
		colDesc = {"sample": datetime.datetime(2005, 6, 4, 23, 12, 21),
			"unit": "d", "ucd": None}
		mapper = valuemappers.datetimeMapperFactory(colDesc)
		self.assertAlmostEqual(2453526.4669097224,
			mapper(datetime.datetime(2005, 6, 4, 23, 12, 21)))
		self.assertAlmostEqual(2434014.6659837961,
			mapper(datetime.datetime(1952, 1, 3, 3, 59, 1)))
		self.assertAlmostEqual(2451910.0,
			mapper(datetime.datetime(2000, 12, 31, 12, 00, 00)))
		self.assertAlmostEqual(2451909.999988426,
			mapper(datetime.datetime(2000, 12, 31, 11, 59, 59)))

	def testFactorySequence(self):
		m1 = lambda cp: lambda val: "First"
		m2 = lambda cp: lambda val: "Second"
		mf = valuemappers.ValueMapperFactoryRegistry()
		mf.registerFactory(m1)
		self.assertEqual(mf.getMapper({})(0), "First", 
			"Registring mappers doesn't work")
		mf.registerFactory(m2)
		self.assertEqual(mf.getMapper({})(0), "Second", 
			"Factories registred later are not tried first")
	
	def testStandardMappers(self):
		def assertMappingResult(dataField, value, literal):
			cp = valuemappers.VColDesc(dataField)
			cp["sample"] = value
			self.assertEqual(literal,
				unicode(valuemappers.defaultMFRegistry.getMapper(cp)(value)))
			
		for dataField, value, literal in [
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="Y-M-D"),
				datetime.date(2003, 5, 4), "2003-05-04"),
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="yr"),
				datetime.date(2003, 5, 4), '2003.33607118'),
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="d"),
				datetime.date(2003, 5, 4), '2452763.5'),
			(base.makeStruct(rscdef.Column, name="d", type="timestamp", unit="d"),
				datetime.datetime(2003, 5, 4, 20, 23), '2452764.34931'),
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="d", 
					ucd="VOX:Image_MJDateObs"),
				datetime.date(2003, 5, 4), '52763.0'),
			(base.makeStruct(rscdef.Column, name="d", type="date", unit="yr"),
				None, ' '),
			(base.makeStruct(rscdef.Column, name="d", type="integer"),
				None, '-2147483648'),
		]:
			assertMappingResult(dataField, value, literal)


class RenamerDryTest(unittest.TestCase):
	"""tests for some aspects of the file renamer without touching the file system.
	"""
	def testSerialization(self):
		"""tests for correct serialization of clobbering renames.
		"""
		f = filestuff.FileRenamer({})
		fileMap = {'a': 'b', 'b': 'c', '2': '3', '1': '2'}
		self.assertEqual(f.makeRenameProc(fileMap),
			[('b', 'c'), ('a', 'b'), ('2', '3'), ('1', '2')])
	
	def testCycleDetection(self):
		"""tests for cycle detection in renaming recipies.
		"""
		f = filestuff.FileRenamer({})
		fileMap = {'a': 'b', 'b': 'c', 'c': 'a'}
		self.assertRaises(filestuff.Error, f.makeRenameProc, fileMap)


class RenamerWetTest(unittest.TestCase):
	"""tests for behaviour of the file renamer on the file system.
	"""
	def setUp(self):
		def touch(name):
			f = open(name, "w")
			f.close()
		self.testDir = tempfile.mkdtemp("testrun")
		for fName in ["a.fits", "a.txt", "b.txt", "b.jpeg", "foo"]:
			touch(os.path.join(self.testDir, fName))

	def tearDown(self):
		shutil.rmtree(self.testDir, onerror=lambda exc: None)

	def testOperation(self):
		"""tests an almost-realistic application
		"""
		f = filestuff.FileRenamer.loadFromFile(
			StringIO("a->b \nb->c\n 2->3\n1 ->2\n\n# a comment\n"
				"foo-> bar\n"))
		f.renameInPath(self.testDir)
		found = set(os.listdir(self.testDir))
		expected = set(["b.fits", "b.txt", "c.txt", "c.jpeg", "bar"])
		self.assertEqual(found, expected)
	
	def testNoClobber(self):
		"""tests for effects of repeated application.
		"""
		f = filestuff.FileRenamer.loadFromFile(
			StringIO("a->b \nb->c\n 2->3\n1 ->2\n\n# a comment\n"
				"foo-> bar\n"))
		f.renameInPath(self.testDir)
		self.assertRaises(filestuff.Error, f.renameInPath, self.testDir)


class TimeCalcTest(testhelpers.VerboseTest):
	"""tests for time transformations.
	"""
	def testJYears(self):
		self.assertEqual(stc.jYearToDateTime(1991.25),
			datetime.datetime(1991, 04, 02, 13, 30, 00))
		self.assertEqual(stc.jYearToDateTime(2005.0),
			datetime.datetime(2004, 12, 31, 18, 0))
	
	def testRoundtrip(self):
		for yr in range(2000):
			self.assertAlmostEqual(2010+yr/1000., stc.dateTimeToJYear(
				stc.jYearToDateTime(2010+yr/1000.)), 7,
				"Botched %f"%(2010+yr/1000.))

	def testBYears(self):
		self.assertEqual(stc.bYearToDateTime(1950.0),
			datetime.datetime(1949, 12, 31, 22, 9, 46, 861900))
	
	def testBRoundtrip(self):
		for yr in range(2000):
			self.assertAlmostEqual(1950+yr/1000., stc.dateTimeToBYear(
				stc.bYearToDateTime(1950+yr/1000.)), 7,
				"Botched %f"%(1950+yr/1000.))

	def testBesselLieske(self):
		"""check examples from Lieske, A&A 73, 282.
		"""
		for bessel, julian in [
				(1899.999142, 1900),
				(1900., 1900.000858),
				(1950., 1949.999790),
				(1950.000210, 1950.0),
				(2000.0, 1999.998722),
				(2000.001278, 2000.0)]:
			self.assertAlmostEqual(stc.dateTimeToJYear(stc.bYearToDateTime(bessel)),
				julian, places=5)


class ProcessorTest(testhelpers.VerboseTest):
	"""tests for some aspects of helper file processors.

	Since setUp is relatively expensive, and also because sequencing
	is important, we do all in one test.  It would be kinda cool if
	TestSuites would have setUp and tearDown...
	"""
	_rdText = """<resource schema="filetest"><data id="import">
		<sources pattern="*.fits"/><fitsProdGrammar/>
		</data></resource>"""

	def _writeFITS(self, destPath, seed):
		hdu = pyfits.PrimaryHDU(numpy.zeros((2,seed+1), 'i2'))
		hdu.header.update("SEED", seed, "initial number")
		hdu.header.update("WEIRD", "W"*seed)
		hdu.header.update("RECIP", 1./(1+seed))
		hdu.writeto(destPath)

	def setUp(self):
		self.resdir = os.path.join(base.getConfig("tempDir"), "filetest")
		self.origInputs = base.getConfig("inputsDir")
		base.setConfig("inputsDir", base.getConfig("tempDir"))
		if os.path.exists(self.resdir): # Leftover from previous run?
			return
		os.mkdir(self.resdir)
		for i in range(10):
			self._writeFITS(os.path.join(self.resdir, "src%d.fits"%i), i)
		f = open(os.path.join(self.resdir, "filetest.rd"), "w")
		f.write(self._rdText)
		f.close()

	def tearDown(self):
		base.setConfig("tempDir", self.origInputs)
		shutil.rmtree(self.resdir, True)

	class SimpleProcessor(helpers.HeaderProcessor):
		def __init__(self, *args, **kwargs):
			helpers.HeaderProcessor.__init__(self, *args, **kwargs)
			self.headersBuilt = 0

		def _isProcessed(self, srcName):
			return self.getPrimaryHeader(srcName).has_key("SQUARE")

		def _getHeader(self, srcName):
			hdr = self.getPrimaryHeader(srcName)
			hdr.update("SQUARE", hdr["SEED"]**2)
			self.headersBuilt += 1
			return hdr

	def _getHeader(self, srcName):
		hdus = pyfits.open(os.path.join(self.resdir, srcName))
		hdr = hdus[0].header
		hdus.close()
		return hdr

	def _testPlainRun(self):
		# Normal run, no headers present yet
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(stdout.split('\r')[-1].strip(), 
			"10 files processed, 0 files with errors")
		self.assertEqual(proc.headersBuilt, 10)
		self.failUnless(os.path.exists(
			os.path.join(self.resdir, "src9.fits.hdr")))
		self.failUnless(self._getHeader("src9.fits.hdr").has_key("SQUARE"))
		# we don't run with applyHeaders here
		self.failIf(self._getHeader("src9.fits").has_key("SQUARE"))

	def _testRespectCaches(self):
		"""tests that no processing is done when cached headers are there.

		This needs to run after _testPlainRun.
		"""
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(stdout.split('\r')[-1].strip(), 
			"10 files processed, 0 files with errors")
		self.assertEqual(proc.headersBuilt, 0)
	
	def _testNoCompute(self):
		"""tests that no computations take place with --no-compute.
		"""
		sys.argv = ["misctest.py", "--no-compute"]
		os.unlink(os.path.join(self.resdir, "src4.fits.hdr"))
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(proc.headersBuilt, 0)

	def _testRecompute(self):
		"""tests that missing headers are recomputed.

		This needs to run before _testApplyCaches and after _testNoCompute.
		"""
		sys.argv = ["misctest.py"]
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(stdout.split('\r')[-1].strip(), 
			"10 files processed, 0 files with errors")
		self.assertEqual(proc.headersBuilt, 1)

	def _testApplyCaches(self):
		"""tests the application of headers to sources.

		This needs to run after _testPlainRun
		"""
		sys.argv = ["misctest.py", "--apply"]
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(stdout.split('\r')[-1].strip(), 
			"10 files processed, 0 files with errors")
		self.assertEqual(proc.headersBuilt, 0)
		self.failUnless(self._getHeader("src9.fits").has_key("SQUARE"))
		# see if data survived
		hdus = pyfits.open(os.path.join(self.resdir, "src9.fits"))
		na = hdus[0].data
		self.assertEqual(na.shape, (2, 10))
	
	def _testForcedRecompute(self):
		"""tests for working --reprocess.
		"""
		sys.argv = ["misctest.py", "--reprocess"]
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(proc.headersBuilt, 10)

	def _testBugfix(self):
		"""tests for working --reprocess --apply.

		This must run last since we're monkeypatching SimpleProcessor.
		"""
		def newGetHeader(self, srcName):
			hdr = self.getPrimaryHeader(srcName)
			hdr.update("SQUARE", hdr["SEED"]**3)
			self.headersBuilt += 1
			return hdr
		sys.argv = ["misctest.py", "--reprocess", "--apply"]
		self.SimpleProcessor._getHeader = new.instancemethod(newGetHeader,
			None, self.SimpleProcessor)
		sys.argv = ["misctest.py", "--reprocess"]
		proc, stdout, _ = testhelpers.captureOutput(helpers.procmain,
			(self.SimpleProcessor, "filetest/filetest", "import"))
		self.assertEqual(self._getHeader("src6.fits.hdr")["SQUARE"], 216)

	def testAll(self):
		self._testPlainRun()
		self._testRespectCaches()
		self._testNoCompute()
		self._testRecompute()
		self._testForcedRecompute()
		self._testApplyCaches()
		self._testForcedRecompute()
		self._testBugfix()


class RemoteURLTest(testhelpers.VerboseTest):
	"""tests for urlopenRemote rejecting unwanted URLs.
	"""
	def testNoFile(self):
		self.assertRaises(IOError,
			utils.urlopenRemote, "file:///etc/passwd")
	
	def testHTTPConnect(self):
		# this assumes nothing actually listens on 57388
		self.assertRaisesWithMsg(IOError,
			"Could not open URL http://localhost:57388: Connection refused",
			utils.urlopenRemote, ("http://localhost:57388",))

	def testMalformedURL(self):
		self.assertRaisesWithMsg(IOError, 
			'Could not open URL /etc/passwd: unknown url type: /etc/passwd',
			utils.urlopenRemote, ("/etc/passwd",))


class RegistryTest(testhelpers.VerboseTest):
	def testVSNamespaces(self):
		from gavo.registry import model
		self.assertEqual(model.VS.ucd().namespace,
			model.VSNamespace)
		self.assertEqual(model.VS1.ucd().namespace,
			model.VS1Namespace)

	def testVOTableDataType(self):
		from gavo.registry import model
		self.assertEqual(
			model.VS1.voTableDataType["char"].render(),
			'<dataType arraysize="1" xsi:type="vs1:VOTableType">char</dataType>')
		self.assertEqual(
			model.VS1.voTableDataType["text"].render(),
			'<dataType arraysize="*" xsi:type="vs1:VOTableType">char</dataType>')
		self.assertEqual(
			model.VS1.voTableDataType["integer[20]"].render(),
			'<dataType arraysize="20" xsi:type="vs1:VOTableType">int</dataType>')


class StanXMLTest(testhelpers.VerboseTest):
	class Model(object):
		class MEl(stanxml.Element): 
			local = True
		class Root(MEl):
			childSequence = ["Child"]
		class Child(MEl):
			childSequence = ["Foo", None]

	def testNoTextContent(self):
		M = self.Model
		self.assertRaises(stanxml.ChildNotAllowed, lambda:M.Root["abc"])
	
	def testTextContent(self):
		M = self.Model
		data = M.Root[M.Child[u"a\xA0bc"]]
		self.assertEqual(data.render(), '<Root><Child>a&#160;bc</Child></Root>')
	
if __name__=="__main__":
	testhelpers.main(StanXMLTest)
