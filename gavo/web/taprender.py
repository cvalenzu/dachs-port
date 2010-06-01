"""
A renderer for TAP, both sync and async.
"""

from __future__ import with_statement

import traceback

from nevow import inevow
from nevow import rend
from nevow import url
from nevow import util
from twisted.internet import threads
from twisted.python import log

from gavo import base
from gavo import formats
from gavo import svcs
from gavo import utils
from gavo.protocols import tap
from gavo.protocols import taprunner
from gavo.protocols import uws
from gavo.protocols import uwsactions
from gavo.web import common
from gavo.web import grend
from gavo.web import streaming
from gavo.web import vosi
from gavo.votable import V


######## XXX TODO: Remove almost all the sync stuff and replace it with
# protocols.taprunner
class ErrorResource(rend.Page):
	def __init__(self, errMsg):
		self.errMsg = errMsg

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		request.setResponseCode(400)  # make some informed choice here?
		doc = V.VOTABLE[
			V.INFO(name="QUERY_STATUS", value="ERROR")[
					self.errMsg]]
		return doc.render()


class UWSRedirect(rend.Page):
	"""a redirection for UWS (i.e., 303).

	The DC-global redirects use a 302 status, munge redirection URLs, and 
	we don't want any HTML payload here anyway.

	The locactions used here are relative to the tap-renderer's URL
	(i.e., async/ points to the async root).
	"""
	def __init__(self, location):
		self.location = str(
			"%s/%s"%(self.getServiceURL(), location))

	@utils.memoized
	def getServiceURL(self):
		return base.caches.getRD("__system__/tap").getById("run").getURL("tap")

	def renderHTTP(self, ctx):
		req = inevow.IRequest(ctx)
		req.code = 303
		req.setHeader("location", self.location)
		req.setHeader("content-type", "text/plain")
		req.write("Go here: %s\n"%self.location)
		return ""


class TAPQueryResource(rend.Page):
	"""the resource executing sync TAP queries.
	"""
	def _doRender(self, ctx):
		format = taprunner.normalizeTAPFormat(
			common.getfirst(ctx, 'FORMAT', 'votable'))
		formats.checkFormatIsValid(format)
		query = common.getfirst(ctx, 'QUERY', base.Undefined)
		return threads.deferToThread(taprunner.runTAPQuery,
			query, 5, 'untrustedquery'
			).addCallback(self._format, format, ctx)

	def renderHTTP(self, ctx):
		try:
			return self._doRender(ctx
				).addErrback(self._formatError)
		except base.Error, ex:
			traceback.print_exc()
			return ErrorResource(unicode(ex))

	def _formatError(self, failure):
		failure.printTraceback()
		return ErrorResource(failure.getErrorMessage())

	def _format(self, res, format, ctx):
		def writeTable(outputFile):
			return taprunner.writeResultTo(format, res, outputFile)

		request = inevow.IRequest(ctx)
		# if request has an accumulator, we're testing and don't stream
		if hasattr(request, "accumulator"):
			writeTable(request)
			return ""
		else:
			return streaming.streamOut(writeTable, request)


SUPPORTED_LANGS = {
	'ADQL': TAPQueryResource,
	'ADQL-2.0': TAPQueryResource,
}


def getQueryResource(service, ctx):
	lang = common.getfirst(ctx, 'LANG', None)
	try:
		generator = SUPPORTED_LANGS[lang]
	except KeyError:
		return ErrorResource("Unknown query language '%s'"%lang)
	return generator()


def getSyncResource(service, ctx, segments):
	if segments:
		raise svcs.UnknownURI("No resources below sync")
	request = common.getfirst(ctx, "REQUEST", base.Undefined)
	if request=="doQuery":
		return getQueryResource(service, ctx)
	elif request=="getCapabilities":
		return vosi.VOSICapabilityRenderer(ctx, service)
	return ErrorResource("Invalid REQUEST: '%s'"%request)


class MethodAwareResource(rend.Page):
	"""is a rend.Page with behaviour depending on the HTTP method.
	"""
	def __init__(self, service):
		self.service = service
		rend.Page.__init__(self)

	def _doBADMETHOD(self, ctx, request):
		raise svcs.BadMethod(request.method)

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		handlingMethod = getattr(self, "_do"+request.method, self._doBADMETHOD)
		return threads.deferToThread(handlingMethod, ctx, request
			).addCallback(self._deliverResult, request
			).addErrback(self._deliverError, request)


class UWSErrorMixin(object):
	def _deliverError(self, failure, request):
		failure.printTraceback()
		request.setHeader("content-type", "text/xml")
		return ErrorResource(failure.getErrorMessage())


class JoblistResource(MethodAwareResource, UWSErrorMixin):
	"""The web resource corresponding to async root.

	GET yields a job list, POST creates a job.
	"""
	def _doGET(self, ctx, request):
		return uwsactions.getJobList()
	
	def _doPOST(self, ctx, request):
		with tap.TAPJob.createFromRequest(request) as job:
			jobId = job.jobId
		return UWSRedirect("async/%s"%jobId)

	def _deliverResult(self, res, request):
		request.setHeader("content-type", "text/xml")
		return res


class JobResource(rend.Page, UWSErrorMixin):
	"""The web resource corresponding to async requests for jobs.
	"""
	def __init__(self, service, segments):
		self.service, self.segments = service, segments

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		return threads.deferToThread(
			uwsactions.doJobAction, request, self.segments
		).addCallback(self._deliverResult, request
		).addErrback(self._redirectAsNecessary, ctx
		).addErrback(self._deliverError, request)

	def _redirectAsNecessary(self, failure, ctx):
		failure.trap(svcs.WebRedirect)
		return UWSRedirect(failure.value.rawDest)

	def _deliverResult(self, result, request):
		if hasattr(result, "renderHTTP"):  # it's a finished resource
			return result
		request.setHeader("content-type", "text/xml")
		request.write(utils.xmlrender(result).encode("utf-8"))
		return ""
	

def getAsyncResource(service, ctx, segments):
	if segments:
		return JobResource(service, segments)
	else:
		return JoblistResource(service)


# Sadly, TAP protocol keys need to be case insensitive (2.3.10)
# In general, this is, of course, an extremely unwelcome feature,
# so we restrict it to the keys specified in the TAP spec.
_caseInsensitiveKeys = set(["REQUEST", "VERSION", "LANG", "QUERY", 
	"FORMAT", "MAXREC", "RUNID", "UPLOAD"])

def reparseRequestArgs(ctx):
	"""adds attributes scalars and files to ctx's request.

	Scalars contains non-field arguments, files the files.  Both are
	dictionaries containing the first item found for a key.
	"""
	request = inevow.IRequest(ctx)
	request.scalars, request.files = {}, {}
	if request.fields:
		for key in request.fields:
			field = request.fields[key]
			if field.filename:
				request.files[key] = field
			else:
				if key.upper() in _caseInsensitiveKeys:
					key = key.upper()
				request.scalars[key] = request.fields.getfirst(key)


class TAPRenderer(grend.ServiceBasedRenderer):
	"""A renderer for the synchronous version of TAP.

	Basically, this just dispatches to the sync and async resources.
	"""
	name = "tap"

	def locateChild(self, ctx, segments):
		reparseRequestArgs(ctx)
		try:
			if common.getfirst(ctx, "VERSION", tap.TAP_VERSION)!=tap.TAP_VERSION:
				return ErrorResource("Version mismatch; this service only supports"
					" TAP version %s."%tap.TAP_VERSION), ()
			if segments:
				if segments[0]=='sync':
					res = getSyncResource(self.service, ctx, segments[1:])
				elif segments[0]=='async':
					res = getAsyncResource(self.service, ctx, segments[1:])
				else:
					res = None
				return res, ()
		except svcs.UnknownURI:
			raise
		except base.Error, ex:
			log.err(_why="TAP error")
			return ErrorResource(str(ex)), ()
		raise common.UnknownURI("Bad TAP path %s"%"/".join(segments))

svcs.registerRenderer(TAPRenderer)
