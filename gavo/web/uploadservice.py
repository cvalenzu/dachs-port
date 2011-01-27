"""
Services and cores to upload things into databases.
"""

from nevow import inevow
from nevow import loaders
from nevow import tags as T, entities as E

from gavo import base
from gavo import svcs
from gavo.web import formrender


class Uploader(formrender.Form):
	"""A renderer allowing for updates to individual records using file upload.

	This renderer exposes a form with a file widget.  It is likely that
	the interface will change.
	"""

	name = "upload"

	def render_uploadInfo(self, ctx, data):
		if data is None:
			return T.invisible()
		else:
			for key, val in data.original.getPrimaryTable().rows[0].iteritems():
				ctx.tag.fillSlots(key, str(val))
			return ctx.tag

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Upload"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body(render=T.directive("withsidebar"))[
			T.h1(render=T.directive("meta"))["title"],
			T.p(class_="procMessage", data=T.directive("result"), 
					render=T.directive("uploadInfo"))[
				T.slot(name="nAffected"),
				" record(s) modified."
			],
			T.invisible(render=T.directive("form genForm"))
		]
	])


class MachineUploader(Uploader):
	"""A renderer allowing for updates to individual records using file 
	uploads.

	The difference to Uploader is that no form-redisplay will be done.
	All errors are reported through HTTP response codes and text strings.
	It is likely that this renderer will change and/or go away.
	"""

	name = "mupload"

	def _handleInputErrors(self, failure, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		request.setHeader("content-type", "text/plain;charset=utf-8")
		request.write(failure.getErrorMessage().encode("utf-8"))
		base.ui.notifyError("Failure while machine uploading.")
		return ""

	def _formatOutput(self, data, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(200)
		request.setHeader("content-type", "text/plain;charset=utf-8")
		request.write(("%s uploaded, %d records modified\n"%(
			data.inputTable.getParamDict()["File"][0],
			data.original.getPrimaryTable().rows[0]["nAffected"])).encode("utf-8"))
		return ""
