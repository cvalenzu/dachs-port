"""
Twisted trial-based tests for TAP and UWS.

Synchronous tests go to taptest.py
"""

# IMPORTANT: If you have deferreds in your tests, *return them* form
# the tests.  Looks weird, but that's the only way the reactor gets
# to see them.

from __future__ import with_statement

import datetime
import httplib
import re
import sys
import unittest
import urllib
import urlparse
import warnings

from nevow import context
from nevow import flat
from nevow import testutil
from nevow import url
from nevow import util
from twisted.python import threadable
threadable.init()

from gavo import base
from gavo import rscdesc
from gavo.protocols import scs  # for table's q3c mixin
from gavo.web import weberrors
from gavo.web.taprender import TAPRenderer

import testhelpers
import trialhelpers


class TAPRenderTest(trialhelpers.RenderTest):
	_tapService = base.caches.getRD("__system__/tap").getById("run")
	@property
	def renderer(self):
		return TAPRenderer(None, self._tapService)


class SyncMetaTest(TAPRenderTest):
	"""tests for non-doQuery sync queries.
	"""
	def testVersionRejected(self):
		"""requests with bad version are rejected.
		"""
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "getCapabilities", "VERSION": "0.1"},
			['<INFO name="QUERY_STATUS" value="ERROR">Version mismatch'])

	def testNoSyncPaths(self):
		"""segments below sync are 404.
		"""
		return self.assertStatus("/sync/foo/bar", 404)

	def testCapabilities(self):
		"""simple get capabilities response looks ok.
		"""
		return self.assertGETHasStrings("/sync", 
			{"REQUEST": "getCapabilities"},
			['<ri:Resource ', '<referenceURL>http://'])


class SyncQueryTest(TAPRenderTest):
	"""tests for querying sync queries.
	"""
	def testNoLangRejected(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery", 
				"QUERY": 'SELECT ra FROM roughtest.main WHERE ra<3'},
			['<INFO name="QUERY_STATUS" value="ERROR">Unknown query language'])

	def testBadLangRejected(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "Furz",
				"QUERY": 'SELECT ra FROM roughtest.main WHERE ra<3'},
			['<INFO name="QUERY_STATUS" value="ERROR">Unknown query language'])

	def testSimpleQuery(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT ra FROM roughtest.main WHERE ra<2'},
			['<FIELD ID="ra" arraysize="1" datatype="float" name="ra"'
			' ucd="pos.eq.ra;meta.main" unit="deg"><DESCRIPTION>RA</DESCRIPTION>'])

	def testBadFormat(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT ra FROM roughtest.main WHERE ra<2',
				"FORMAT": 'xls'},
			['<INFO name="QUERY_STATUS" value="ERROR">Unsupported format \'xls\''])

	def testClearVOT(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT ra FROM roughtest.main WHERE ra<2',
				"FORMAT": "votable/td"},
			['<DATA><TABLEDATA><TR><TD>0.96319</TD>'])

	def testCSV(self):
		return self.assertGETHasStrings("/sync", {
				"REQUEST": "doQuery",
				"LANG": "ADQL",
				"QUERY": 'SELECT ra,de FROM roughtest.main WHERE ra<2',
				"FORMAT": "text/csv"},
			['0.96319,71.6269'])

	def testTSV(self):
		return self.assertGETHasStrings("/sync", {
			"REQUEST": "doQuery",
			"LANG": "ADQL",
			"QUERY": 'SELECT ra FROM roughtest.main WHERE ra<2',
			"FORMAT": "TSV"},
			['0.96319', '\n', '0.56091'])


class SimpleAsyncTest(TAPRenderTest):
	"""tests for some non-ADQL async queries.
	"""
	def testVersionRejected(self):
		"""requests with bad version are rejected.
		"""
		return self.assertPOSTHasStrings("/async", {
				"REQUEST": "getCapabilities",
				"VERSION": "0.1"},
			['<INFO name="QUERY_STATUS" value="ERROR">Version mismatch'])

	def testJobList(self):
		return self.assertGETHasStrings("/async", {}, [
			'<uws:jobs xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0'])

	def testJobCycle(self):
		"""a job is created, and we are redirected to the proper resource.
		"""
		def assertDeleted(result, jobId):
			self.assertEqual(result[1].code, 303)
			next = result[1].headers["location"][len(
				self._tapService.getURL("tap")):]
			self.assertEqual(next, "/async",
				"Deletion redirect doesn't point to job list but to %s"%next)
			return self.assertGETLacksStrings(next, {}, ['jobref id="%s"'%jobId])

		def delete(jobId):
			return trialhelpers.runQuery(self.renderer, "DELETE", "/async/"+jobId, {}
			).addCallback(assertDeleted, jobId)

		def checkPosted(result):
			# jobId is in location of result[1]
			request = result[1]
			self.assertEqual(request.code, 303)
			next = request.headers["location"]
			self.failIf("/async" not in next)
			jobId = next.split("/")[-1]
			return delete(jobId)

		return trialhelpers.runQuery(self.renderer, "POST", "/async", {}
		).addCallback(checkPosted)
		


class JobInfoTest(TAPRenderTest):
	############# Hier weiter: testresource job, etc.
	pass
