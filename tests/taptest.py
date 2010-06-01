"""
Simple tests for TAP and environs.

All these tests really stink because TAP isn't really a good match for the
basically stateless unit tests that are executed in an arbitrary order.

There's more TAP/UWS related tests in test_tap.py; these require a
running reactor and are based on trial.
"""

from __future__ import with_statement

import os
import Queue
import time
import threading

from nevow import inevow
from nevow.testutil import FakeRequest
from twisted.python.components import registerAdapter

from gavo import base
from gavo import rscdesc  # uws needs getRD
from gavo.protocols import tap
from gavo.protocols import uws
from gavo.web import taprender

import testhelpers
import adqltest



class TAPFakeRequest(FakeRequest):
# The UWS machinery wants its arguments in scalars, hence this class.
	def __init__(self, *args, **kwargs):
		FakeRequest.__init__(self, *args, **kwargs)
		self.scalars = self.args


class _PlainActions(uws.UWSActions):
	def __init__(self):
		uws.UWSActions.__init__(self, "plainActions", [
			(uws.PENDING, uws.QUEUED, "noOp"),
			(uws.QUEUED, uws.EXECUTING, "run"),
			(uws.EXECUTING, uws.COMPLETED, "noOp"),
			(uws.QUEUED, uws.ABORTED, "noOp"),
			(uws.EXECUTING, uws.ABORTED, "noOp"),
			(uws.COMPLETED, uws.DESTROYED, "noOp"),])
	
	def run(self, newState, uwsJob, ignored):
		uwsJob = uws.EXECUTING
		f = open(os.path.join(uwsJob.getWD(), "ran"))
		f.write("ran")
		f.close()
		uwsJob.changeToPhase(uws.COMPLETED)


uws.registerActions(_PlainActions)


class _FakeJob(object):
	"""A scaffolding class for UWSJob.
	"""
	def __init__(self, phase):
		self.phase = phase


class _FakeContext(object):
	"""A scaffolding class for testing renderers.
	"""
	def __init__(self, **kwargs):
		self.request = TAPFakeRequest(args=kwargs)
		self.args = kwargs

registerAdapter(lambda ctx: ctx.request, _FakeContext, inevow.IRequest)


class PlainActionsTest(testhelpers.VerboseTest):
	"""tests for uws actions.
	"""
	def setUp(self):
		self.actions = uws.getActions("plainActions")

	def testSimpleTransition(self):
		job = _FakeJob(object)
		self.actions.getTransition(uws.PENDING, uws.QUEUED)(uws.QUEUED, job, None)
		self.assertEqual(job.phase, uws.QUEUED)
	
	def testFailingTransition(self):
		self.assertRaises(base.ValidationError,
			self.actions.getTransition, uws.PENDING, uws.COMPLETED)
	

class PlainJobCreationTest(testhelpers.VerboseTest):
	"""tests for working job creation and destruction.
	"""
# yet another huge, sequential test.  Ah well, better than nothing, I guess.

	def _createJob(self):
		with uws.UWSJob.createFromRequest(TAPFakeRequest(args={"foo": "bar"}), 
				"plainActions") as job:
			return job.jobId

	def _deleteJob(self, jobId):
		with uws.UWSJob.makeFromId(jobId) as job:
			job.delete()

	def _assertJobCreated(self, jobId):
		querier = base.SimpleQuerier()
		res = querier.runIsolatedQuery("SELECT quote FROM uws.jobs WHERE"
			" jobId=%(jobId)s", locals())
		querier.close()
		self.assertEqual(len(res), 1)
		job = uws.UWSJob.makeFromId(jobId)
		self.assertEqual(job.getParameter("foo"), "bar")
		self.failUnless(os.path.exists(job.getWD()))

	def _assertJobDeleted(self, jobId):
		querier = base.SimpleQuerier()
		res = querier.runIsolatedQuery("SELECT quote FROM uws.jobs WHERE"
			" jobId=%(jobId)s", locals())
		querier.close()
		self.assertEqual(len(res), 0)
		self.assertRaises(base.NotFoundError, uws.UWSJob.makeFromId, jobId)
		self.failIf(os.path.exists(os.path.join(base.getConfig("uwsWD"), jobId)))

	def testBigAndUgly(self):
		jobId = self._createJob()
		self._assertJobCreated(jobId)
		self._deleteJob(jobId)
		self._assertJobDeleted(jobId)


class UWSMiscTest(testhelpers.VerboseTest):
	"""uws tests not fitting anywhere else.
	"""
	def testBadActionsRaise(self):
		with uws.UWSJob.create(actions="Wullu_ulla99") as job:
			try:
				self.assertRaises(base.NotFoundError, 
					job.changeToPhase, uws.EXECUTING)
			finally:
				job.delete()


class LockingTest(testhelpers.VerboseTest):
	"""tests for working impicit uws locking.
	"""
	def setUp(self):
		with uws.UWSJob.create(actions="plainActions") as job:
			self.jobId = job.jobId
		self.queue = Queue.Queue()
	
	def tearDown(self):
		with uws.UWSJob.makeFromId(self.jobId) as job:
			job.delete()

	def _blockingJob(self):
		# this is started in a thread while self.jobId is held
		self.queue.put("Child started")
		q = base.SimpleQuerier()
		with uws.UWSJob.makeFromId(self.jobId) as job:
			self.queue.put("Job created")

	def testLocking(self):
		with uws.UWSJob.makeFromId(self.jobId) as job:
			child = threading.Thread(target=self._blockingJob)
			child.start()
			# see that child process has started but could not create the job
			self.assertEqual(self.queue.get(True, 1), "Child started")
			# make sure we time out on waiting for another sign of the child --
			# it should be blocking.
			self.assertRaises(Queue.Empty, self.queue.get, True, 0.05)
		# we've closed our handle on job, now child can run
		self.assertEqual(self.queue.get(True, 1), "Job created")


class SimpleRunnerTest(testhelpers.VerboseTest):
	"""tests various taprunner scenarios.
	"""
	resources = [("ds", adqltest.adqlTestTable)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.tableName = self.ds.tables["adql"].tableDef.getQName()

	def testSimpleJob(self):
		jobId = None
		try:
			with uws.UWSJob.create(args={
					"QUERY": "SELECT * FROM %s"%self.tableName,
					"REQUEST": "doQuery",
					"LANG": "ADQL"}) as job:
				jobId = job.jobId
				self.assertEqual(job.phase, uws.PENDING)
				job.changeToPhase(uws.QUEUED, None)

			# let things run, but bail out if nothing happens 
			for i in range(70):
				time.sleep(0.1)
				with uws.UWSJob.makeFromId(jobId) as job:
					if job.phase!=uws.EXECUTING:
						break
			else:
				raise AssertionError("Job does not finish.  Your machine cannot be"
					" *that* slow?")

			with uws.UWSJob.makeFromId(jobId) as job:
				self.assertEqual(job.phase, uws.COMPLETED)
				result = open(os.path.join(job.getWD(), 
					job.getResults()[0]["resultName"])).read()

		finally:
			if jobId is not None:
				with uws.UWSJob.makeFromId(jobId) as job:
					job.delete()
		self.failUnless('xmlns="http://www.ivoa.net/xml/VOTable/' in result)


class UploadSyntaxOKTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	def _runTest(self, sample):
		s, e = sample
		self.assertEqual(tap.parseUploadString(s), e)
	
	samples = [
		('a,b', [('a', 'b'),]),
		('a5_ug,http://knatter?RA=99&DEC=1.54', 
			[('a5_ug', 'http://knatter?RA=99&DEC=1.54'),]),
		('a5_ug,http://knatter?RA=99&DEC=1.54;a,b', 
			[('a5_ug', 'http://knatter?RA=99&DEC=1.54'), ('a', 'b')]),]


class UploadSyntaxNotOKTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	def _runTest(self, sample):
		self.assertRaises(base.ValidationError, tap.parseUploadString,
			sample)
	
	samples = [
		'a,',
		',http://wahn',
		'a,b;',
		'a,b;whacky/name,b',]


if __name__=="__main__":
	testhelpers.main(SimpleRunnerTest)
