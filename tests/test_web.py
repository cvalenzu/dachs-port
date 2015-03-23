"""
Tests for various parts of the server infrastructure, using trial.
"""

#c Copyright 2008-2015, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from cStringIO import StringIO
import atexit
import os

import trialhelpers

from gavo import api
from gavo import base
from gavo import svcs
from gavo import utils
from gavo.imp import formal

base.DEBUG = True
from gavo.user.logui import LoggingUI
LoggingUI(base.ui)


class AdminTest(trialhelpers.ArchiveTest):
	def _makeAdmin(self, req):
		req.user = "gavoadmin"
		req.password = api.getConfig("web", "adminpasswd")

	def testDefaultDeny(self):
		return self.assertStatus("/seffe/__system__/adql", 401)
	
	def testFormsRendered(self):
		return self.assertGETHasStrings("/seffe/__system__/adql", {}, [
			"ADQL Query</a>", 
			"Schedule downtime for", 
			'action="http://localhost'],
			rm=self._makeAdmin)
	
	def testDowntimeScheduled(self):
		def checkDowntimeCanceled(ignored):
			self.assertRaises(api.NoMetaKey,
				api.getRD("__system__/adql").getMeta, "_scheduledDowntime",
				raiseOnFail=True)

		def cancelDowntime(ignored):
			return self.assertPOSTHasStrings("/seffe/__system__/adql", 
				{"__nevow_form__": "setDowntime"}, [],
				rm=self._makeAdmin)

		def checkDowntime(ignored):
			self.assertEqual(
				str(api.getRD("__system__/adql").getMeta("_scheduledDowntime")),
				'2009-10-13')
			return self.assertGETHasStrings("/__system__/adql/query/availability", 
				{}, ["<avl:downAt>2009-10-13<"])

		return trialhelpers.runQuery(self.renderer,
			"POST", "/seffe/__system__/adql", 
			{"__nevow_form__": "setDowntime", "scheduled": "2009-10-13"}, 
			self._makeAdmin
		).addCallback(checkDowntime
		).addCallback(cancelDowntime
		).addCallback(checkDowntimeCanceled)

	def testBlockAndReload(self):
		def checkUnBlocked(ignored):
			return self.assertGETHasStrings("/seffe/__system__/adql", {},
				["currently is not blocked"], self._makeAdmin)
	
		def reload(ignored):
			return trialhelpers.runQuery(self.renderer,
				"POST", "/seffe/__system__/adql", 
				{"__nevow_form__": "adminOps", "submit": "Reload RD"}, 
				self._makeAdmin
			).addCallback(checkUnBlocked)

		def checkBlocked(ignored):
			return self.assertGETHasStrings("/seffe/__system__/adql", {},
				["currently is blocked", "invalid@whereever.else"], self._makeAdmin
			).addCallback(reload)

		return trialhelpers.runQuery(self.renderer,
			"POST", "/seffe/__system__/adql", 
			{"__nevow_form__": "adminOps", "block": "Block"}, 
			self._makeAdmin
		).addCallback(checkBlocked)


class CustomizationTest(trialhelpers.ArchiveTest):
	def testSidebarRendered(self):
		return self.assertGETHasStrings("/data/test/basicprod/form", {}, [
			'<a href="mailto:invalid@whereever.else">site operators</a>',
			'<div class="exploBody"><span class="plainmeta">ivo://'
				'x-unregistred/data/test/basicprod</span>'])
	
	def testMacrosExpanded(self):
		return self.assertGETHasStrings("/__system__/dc_tables/list/info", {}, [
			"Information on Service 'Unittest Suite Public Tables'",
			"tables available for ADQL querying within the\nUnittest Suite",
			"Unittest Suite Table Infos</a>",])

	def testExpandedInXML(self):
		return self.assertGETHasStrings("/oai.xml", {
			"verb": "GetRecord",
			"metadataPrefix": "ivo_vor",
			"identifier": "ivo://x-unregistred/__system__/services/registry"
		}, [
			"<title>Unittest Suite Registry</title>",
			"<managedAuthority>x-unregistred</managedAuthority>"])


class StaticTest(trialhelpers.ArchiveTest):
	def testSimple(self):
		return self.assertGETHasStrings("/data/cores/rds/static/", {}, [
			'<td><a href="test-gavorc">test-gavorc</a>',
			'<title>Directory listing for //data/cores/rds/static/</title>'])
	
	def testRendererInferred(self):
		def assertRightURL(failure):
			self.assertTrue("http://localhost:8080/data/cores/rds/static/"
				in failure.getErrorMessage())

		return self.assertGETRaises("/data/cores/rds", {}, 
			svcs.WebRedirect, alsoCheck=assertRightURL)

	def testSlashAdded(self):
		def assertRightURL(failure):
			self.assertTrue("http://localhost:8080/data/cores/rds/static/"
				in failure.getErrorMessage())

		return self.assertGETRaises("/data/cores/rds/static", {}, 
			svcs.WebRedirect, alsoCheck=assertRightURL)
	
	def testStaticFile(self):
		return self.assertGETHasStrings("/data/cores/rds/static/ex.fits", {}, [
			"BITPIX  =                   16"])

	def test404(self):
		return self.assertStatus("/data/cores/rds/static/ex.fit", 404)

	def testWithIndexFile(self):
		return self.assertGETHasStrings("/data/test/basicprod/static/", {}, [
			"alpha: 23 34 33.45"])

	def testSubDir(self):
		return self.assertGETHasStrings("/data/cores/rds/static/bin/", {},
			["Directory listing for //data/cores/rds/static/bin/"])

	def testAutoMinification(self):
		return self.assertGETHasStrings("/static/js/fancyroot.js", {},
			["ResourceHeader);fetchSubject"])

		
class FormTest(trialhelpers.ArchiveTest):
	def testSimple(self):
		return self.assertGETHasStrings("/data/test/basicprod/form", {}, [
				'<a href="/static/help_vizier.shtml#floats">[?num. expr.]</a>',
				"<h1>Somebody else's problem</h1>",
			])
	
	def testInputSelection(self):
		return self.assertGETHasStrings("/data/cores/cstest/form", {}, [
				'Coordinates (as h m s, d m s or decimal degrees), or SIMBAD',
				'Search radius in arcminutes',
				'A sample magnitude'
			])
	
	def testMultigroupMessages(self):
		return self.assertGETHasStrings("/data/cores/impgrouptest/form", {
				"rV": "invalid", 
				"mag": "bogus", 
				formal.FORMS_KEY: "genForm",
			}, [
				# assert multiple form items in one line:
				'class="description">Ah, you know.',
				'class="inmulti"',
				'<div class="message">Not a valid number; Not a valid number</div>',
				'value="invalid"'])
	
	def testCSSProperties(self):
		return self.assertGETHasStrings("/data/cores/cstest/form", {}, [
			'class="field string numericexpressionfield rvkey"',
			'.rvkey { background:red; }'])
	
	def testInputKeyDefault(self):
		return self.assertGETHasStrings("/data/cores/grouptest/form", {}, [
				'value="-4.0"'
			])

	def testInputKeyFilled(self):
		return self.assertGETHasStrings("/data/cores/grouptest/form", 
			{"rV": "9.25"}, [
				'value="9.25"'
			])

	def testSCSPositionComplains(self):
		return self.assertGETHasStrings("/data/cores/cstest/form", {
				"hscs_pos": "23,24", "__nevow_form__": "genForm", "VERB": 3}, 
				["Field hscs_sr: If you query for a position, you must give"
					" a search radius"])

	def testJSONOnForm(self):
		return self.assertGETHasStrings("/data/cores/cstest/form", {
				"hscs_sr": "2000", "hscs_pos": "2,14", "rV": "", "__nevow_form__": 
				"genForm", "VERB": 3, "_FORMAT": "JSON"}, 
				['"queryStatus": "Ok"', '"dbtype": "real"'])

	def testServiceKeyRendered(self):
		self.assertGETHasStrings("/data/cores/uploadtest/form", {},
			['<div class="description">A service key</div>'])


class StreamingTest(trialhelpers.ArchiveTest):
	def testStreamingWorks(self):
		return self.assertGETHasStrings("/test/stream", {"size": 30}, [
			"123456789012345678901234567890"])
	
	def testChunksWork(self):
		return self.assertGETHasStrings("/test/stream", {"chunksize": "10",
			"size": "35"}, [
			"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx12345"])
	
	def testCrashStreamDoesNotHang(self):
		return self.assertGETHasStrings("/test/streamcrash", {}, [
			"Here is some data.",
			"XXX Internal",
			"raise Exception"])
	
	def testStopProducing(self):

		class StoppingRequest(trialhelpers.FakeRequest):
			def write(self, data):
				trialhelpers.FakeRequest.write(self, data)
				self.producer.stopProducing()

		def assertResult(result):
			# at least one chunk must have been delivered
			self.failUnless(result[0].startswith("xxxxxxxxxx"), 
				"No data delivered at all")
			# ...but the kill must become active before the whole mess
			# has been written
			self.failIf(len(result[0])>utils.StreamBuffer.chunkSize,
				"Kill hasn't happened")

		return trialhelpers.runQuery(self.renderer, "GET", "/test/stream",
			{"chunksize": "10", "size": utils.StreamBuffer.chunkSize*2}, 
			requestClass=StoppingRequest
		).addCallback(assertResult)

	def testClosingConnection(self):

		class ClosingRequest(trialhelpers.FakeRequest):
			def write(self, data):
				raise IOError("Connection closed")

		def assertResult(result):
			self.assertEqual(result[0], "")

		return trialhelpers.runQuery(self.renderer, "GET", "/test/stream",
			{"chunksize": "10", "size": "3500"}, requestClass=ClosingRequest
		).addCallback(assertResult)


_TEMPLATE_TEMPLATE = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
	"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns:n="http://nevow.com/ns/nevow/0.1" 
		xmlns="http://www.w3.org/1999/xhtml">
	<head>
		<title>Template test</title>
		<n:invisible n:render="commonhead"/>
	</head>
	<body>
		%s
	</body>
</html>
"""

class TemplatingTest(trialhelpers.ArchiveTest):
# These must not run in parallel since they're sharing a file name
# (and it's hard to change this since the clean up would have
# to take place in the test callback)

	commonTemplatePath = os.path.join(
		api.getConfig("tempDir"), "trialtemplate")

	def cleanUp(self):
		try:
			os.unlink(self.commonTemplatePath)
		except os.error:
			pass

	def _assertTemplateRendersTo(self, templateBody, args, strings,
			render="fixed"):
		with open(self.commonTemplatePath, "w") as f:
			f.write(_TEMPLATE_TEMPLATE%templateBody)

		svc = api.getRD("//tests").getById("dyntemplate")
		svc._loadedTemplates.pop("fixed", None)
		svc._loadedTemplates.pop("form", None)
		svc.templates[render] = self.commonTemplatePath
		return self.assertGETHasStrings("//tests/dyntemplate/"+render, 
			args, strings)

	def testContentDelivered(self):
		return self._assertTemplateRendersTo(
			'<p>stuff: <n:invisible n:render="data" n:data="parameter foo"/></p>',
			{"foo": "content delivered test"},
			["<p>stuff: content delivered test", 'href="/static/css/gavo_dc.css'])
	
	def testNoParOk(self):
		return self._assertTemplateRendersTo(
			'<p>stuff: <n:invisible n:render="data" n:data="parameter foo"/></p>',
			{},
			["stuff: </p>"])
	
	def testEightBitClean(self):
		return self._assertTemplateRendersTo(
			'<p>stuff: <n:invisible n:render="data" n:data="parameter foo"/></p>',
			{"foo": u"\u00C4".encode("utf-8")},
			["stuff: \xc3\x84</p>"])

	def testMessEscaped(self):
		return self._assertTemplateRendersTo(
			'<p>stuff: <n:invisible n:render="data" n:data="parameter foo"/></p>',
			{"foo": '<script language="nasty&"/>'},
			['&lt;script language="nasty&amp;"/&gt;'])

	def testRDData(self):
		return self._assertTemplateRendersTo(
			'<p n:data="rd //tap" n:render="string"/>',
			{},
			['<p>&lt;resource descriptor for __system__/tap'])

	def testNoRDData(self):
		return self._assertTemplateRendersTo(
			'<div n:data="rd /junky/path/that/leads/nowhere">'
			'<p n:render="ifnodata">No junky weirdness here</p></div>',
			{},
			['<div><p>No junky weirdness'])
	
	def testParamRender(self):
		return self._assertTemplateRendersTo(
			'<div n:data="result">'
			'<p n:render="param a float is equal to %5.2f">aFloat</p>'
			'</div>',
			{"__nevow_form__": "genForm",}, [
				"<p>a float is equal to  1.25</p>"], render="form")

	def testNoParamRender(self):
		return self._assertTemplateRendersTo(
			'<div n:data="result">'
			'<p n:render="param %5.2f">foo</p>'
			'</div>',
			{"__nevow_form__": "genForm",}, [
				"<p>N/A</p>"], render="form")



class PathResoutionTest(trialhelpers.ArchiveTest):
	def testDefaultRenderer(self):
		return self.assertGETHasStrings("/data/cores/impgrouptest", {},
			['id="genForm-rV"']) #form rendered
			
	def testNoDefaultRenderer(self):
		self.assertGETRaises("/data/cores/grouptest", {},
			svcs.UnknownURI)

	def testSlashAtEndRedirects(self):
		def checkRedirect(result):
			self.assertEqual(result[1].code, 301)
			# the destination of the redirect currently is wrong due to trialhelper
			# restrictions.
		return trialhelpers.runQuery(self.renderer, "GET", 
			"/data/cores/convcat/form/", {}
		).addCallback(checkRedirect)


class BuiltinResTest(trialhelpers.ArchiveTest):
	def testRobotsTxt(self):
		return self.assertGETHasStrings("/robots.txt", {},
			['Disallow: /login'])


class ConstantRenderTest(trialhelpers.ArchiveTest):
	def testVOPlot(self):
		return self.assertGETHasStrings("/__system__/run/voplot/fixed",
			{"source": "http%3A%3A%2Ffoo%3Asentinel"}, 
			['<object archive="http://']) # XXX TODO: votablepath is url-encoded -- that can't be right?


class MetaRenderTest(trialhelpers.ArchiveTest):
	def testMacroExpanded(self):
		return self.assertGETHasStrings("/browse/__system__/tap", {},
			['<div class="rddesc"><span class="plainmeta"> Unittest'
				" Suite's Table Access"])


class MetaPagesTest(trialhelpers.ArchiveTest):
	def testGetRR404(self):
		return self.assertGETHasStrings("/getRR/non/existing", {},
			['The resource non#existing is unknown at this site.'])

	def testGetRRForService(self):
		return self.assertGETHasStrings("/getRR/data/pubtest/moribund", {},
			['<identifier>ivo://x-unregistred/data/pubtest/moribund</identifier>'])


class _FakeUpload(object):
	value = "abc, die Katze lief im Schnee.\n"
	file = StringIO(value)
	filename = "test.txt"
	
	def __len__(self):
		return len(self.value)
	

class APIRenderTest(trialhelpers.ArchiveTest):
	def testResonseKey(self):
		return self.assertGETHasStrings("/data/cores/scs/api", 
			{"id": ["/0"], "RESPONSEFORMAT": "tsv"},
			["0\t1.25\t2.5\n"],
			customTest=lambda tx: self.assertFalse("1\t23.0" in tx))

	def testResponseMIME(self):
		return self.assertGETHasStrings("/data/cores/scs/api", 
			{"id": ["/0"], "RESPONSEFORMAT": 
				["application/x-votable+xml;serialization=BINARY2"]},
			["<BINARY2>", "AAAAAAA/oAAAQAQAAAAAAAA="],
			customTest=lambda tx: self.assertFalse("1\t23.0" in tx))
	
	def testMetadataResponse(self):
		return self.assertGETHasStrings("/data/cores/scs/api", 
			{"MAXREC": ["0"]}, [
				'<OPTION name="HTML" value="text/html"/>',
				'name="INPUT:MAXREC"',
				'<TABLEDATA></TABLEDATA>',
				'value="http://localhost:8080/data/cores/scs/api?">Unnamed'])

	def testUploadMetadata(self):
		return self.assertGETHasStrings("/data/cores/uploadtest/api",
			{"MAXREC": ["0"]}, [
				'name="INPUT:UPLOAD"',
				'ucd="par.upload"',
				"of the form 'notarbitrary,URL'",
				"An example upload containing nothing in particular"])
	
	def testUploadInlineBadPar(self):
		return self.assertGETHasStrings("/data/cores/uploadtest/api",
			{"UPLOAD": ["notarbitrary,param:notexisting"]}, [
				'value="ERROR"',
				'Field UPLOAD: param:notexisting references a'
				' non-existing file upload.'])

	def testUploadInlineGoodPar(self):
		return self.assertGETHasStrings("/data/cores/uploadtest/api", {
			"UPLOAD": ["notarbitrary,param:hello"],
			"RESPONSEFORMAT": "votabletd",
			"hello": [_FakeUpload()],
			}, [
				'<TR><TD>notarbitrary</TD><TD>abc, die Katze lief im'
				' Schnee.\n</TD></TR>'])

	def testUploadURL(self):
		_, _, baseURL = trialhelpers.testhelpers.getServerInThread(
			"def, ich bin der Chef.\n", onlyOnce=True)
		return self.assertPOSTHasStrings("/data/cores/uploadtest/api", {
			"UPLOAD": ["notarbitrary,%s"%baseURL],
			"RESPONSEFORMAT": "votabletd",
			"hello": [_FakeUpload()],
			}, [
				'<TR><TD>notarbitrary</TD><TD>def, ich bin der Chef.\n</TD></TR>'])
	
	def testServiceParametersValidated(self):
		return self.assertGETHasStrings("/data/cores/scs/api", 
			{"RESPONSEFORMAT": "fantastic junk"}, 
				["Field RESPONSEFORMAT: u'fantastic junk' is not a valid value for"
					" RESPONSEFORMAT</INFO>"])


class SCSTest(trialhelpers.ArchiveTest):
	def testCasting(self):
		return self.assertGETHasStrings("/data/cores/scs/scs.xml", 
			{"RA": ["1"], "DEC": ["2"], "SR": ["1.5"]},
			['AAAAATA/9AAAAAAAAEAEAAAAAAAA', 'datatype="char"'])

	def testCapability(self):
		return self.assertGETHasStrings("/data/cores/scs/capabilities", {}, [
			'standardID="ivo://ivoa.net/std/VOSI#capabilities"',
			'standardID="ivo://ivoa.net/std/ConeSearch"',
			'xsi:type="vs:ParamHTTP',
			'<name>SR</name>',
			'<sr>1</sr>'])


class TestExamples(trialhelpers.ArchiveTest):
	def testBasic(self):
		return self.assertGETHasStrings("/data/cores/dl/examples", 
			{}, [
			'<title>Examples for Hollow Datalink</title',
			'<h2 property="name"><span class="plainmeta">Example 1</span>',
			'property="dl-id"',
			'ivo://org.gavo.dc/~?bla/foo/qua</em>',
			'resource="#Example2"',
			'<p>This is another example for examples.</p>'])


atexit.register(trialhelpers.provideRDData("test", "import_fitsprod"))
atexit.register(trialhelpers.provideRDData("cores", "import_conecat"))
atexit.register(trialhelpers.provideRDData("test", "ADQLTest"))
