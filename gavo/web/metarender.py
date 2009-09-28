"""
Renderers that take services "as arguments".
"""

import os
import urllib

from nevow import inevow
from nevow import loaders
from nevow import tags as T, entities as E
from nevow import url

from zope.interface import implements

from gavo import base
from gavo import svcs
from gavo.web import common
from gavo.web import grend
from gavo.web import resourcebased
from gavo.web import weberrors


class MetaRenderer(grend.ServiceBasedRenderer):
	"""Renderers that are allowed on all services.
	"""
	checkedRenderer = False


class BlockRDRenderer(MetaRenderer):
	"""is a renderer used for blocking RDs from the web interface.
	"""
	name = "block"

	def data_blockstate(self, ctx, data):
		if hasattr(self.service.rd, "currently_blocked"):
			return "blocked"
		return "unblocked"

	def data_rdId(self, ctx, data):
		return str(self.service.rd.sourceId)

	def renderHTTP(self, ctx):
		return common.runAuthenticated(ctx, "admin", self.realRenderHTTP,
			ctx)

	def realRenderHTTP(self, ctx):
		self.service.rd.currently_blocked = True
		return grend.ServiceBasedRenderer.renderHTTP(self, ctx)

	defaultDocFactory = loaders.stan(
		T.html[
			T.head[
				T.title["RD blocked"],
			],
			T.body[
				T.h1["RD blocked"],
				T.p["All services defined in ", 
					T.invisible(render=T.directive("data"), data=T.directive(
						"rdId")),
					" are now ",
					T.invisible(render=T.directive("data"), data=T.directive(
						"blockstate")),
					".  To unblock, restart the server.",
				],
			]
		])

svcs.registerRenderer(BlockRDRenderer)

class RendExplainer(object):
	"""is a container for various functions having to do with explaining
	renderers on services.

	Use the explain(renderer, service) class method.
	"""

	@classmethod
	def _explain_form(cls, service):
		return T.invisible["allows access via an ",
			T.a(href=service.getURL("form"))["HTML form"]]

	@classmethod
	def _explain_soap(cls, service):

		def generateArguments():
			# Slightly obfuscated -- I need to get ", " in between the items.
			fieldIter = iter(svcs.getRenderer("soap").getInputFields(service))
			try:
				next = fieldIter.next()
				while True:
					desc = "%s/%s"%(next.name, next.type)
					if next.required:
						desc = T.strong[desc]
					yield desc
					next = fieldIter.next()
					yield ', '
			except StopIteration:
				pass

		return T.invisible["enables remote procedure calls; to use it,"
			" feed the ", 
			T.a(href=service.getURL("soap")+"/go?wsdl")["WSDL URL"],
			" to your SOAP library; the function signature is"
			"  useService(",
			generateArguments(),
			").  See also our ", 
			T.a(render=T.directive("rootlink"), href="/static/doc/soaplocal.shtml")[
				"local soap hints"]]

	@classmethod
	def _explain_custom(cls, service):
		return T.invisible["a custom rendering of the service, typically"
			" for interactive web applications; see ", 
			T.a(href=service.getURL("custom"))["entry page"]]
	
	@classmethod
	def _explain_static(cls, service):
		return T.invisible["static (i.e. prepared) data or custom client-side"
			" code; probably used to access ancillary files here"]
	
	@classmethod
	def _explain_text(cls, service):
		return T.invisible["a text interface not intended for user"
			" applications"]

	@classmethod
	def _explain_siap_xml(cls, service):
		return T.invisible["a standard SIAP interface as defined by the"
			" IVOA to access collections of celestial images; SIAP clients"
			" use ", service.getURL("siap.xml"), " to access the service",
			T.invisible(render=T.directive("ifadmin"))[" -- ",
				T.a(href="http://nvo.ncsa.uiuc.edu/dalvalidate/SIAValidater?endpoint="+
					urllib.quote(service.getURL("siap.xml"))+
					"&RA=180.0&DEC=60.0&RASIZE=1.0&DECSIZE=1.0&FORMAT=ALL&"
					"format=html&show=fail&show=warn&show=rec&op=Validate")["Validate"]]]

	@classmethod
	def _explain_scs_xml(cls, service):
		return T.invisible["a standard SCS interface as defined by the"
			" IVOA to access catalog-type data; SCS clients"
			" use ", service.getURL("scs.xml"), " to access the service",
			T.invisible(render=T.directive("ifadmin"))[" -- ",
				T.a(href="http://nvo.ncsa.uiuc.edu/dalvalidate/"
					"ConeSearchValidater?endpoint="+
					urllib.quote(service.getURL("scs.xml"))+
					"&RA=180.0&DEC=60.0&SR=1.0&format=html&show=fail&show=warn&show=rec"
					"&op=Validate")["Validate"]]]

	@classmethod
	def _explain_qp(cls, service):
		return T.invisible["an interface that uses the last path element"
			" to query the column %s in the underlying table."%
			service.getProperty("queryField", "defunct")]

	@classmethod
	def _explain_upload(cls, service):
		return T.invisible["a ",
			T.a(href=service.getURL("upload"))["form-based interface"],
			" for uploading data"]

	@classmethod
	def _explain_mupload(cls, service):
		return T.invisible["an upload interface for use with custom"
			" upload programs.  These should access ",
			service.getURL("mupload")]
	
	@classmethod
	def _explain_img_jpeg(cls, service):
		return T.invisible["a ",
			T.a(href=service.getURL("img.jpeg"))["form-based interface"],
			" to generate jpeg images from the underlying data"]

	@classmethod
	def _explain_mimg_jpeg(cls, service):
		return T.invisible["a ",
			T.a(href=service.getURL("img.jpeg"))["form-based interface"],
			" to generate jpeg images from the underlying data; the replies"
			" are intended for machine consumption"]

	@classmethod
	def _explainEverything(cls, service):
		return T.invisible["a renderer with some custom access method that"
			" should be mentioned in the service description"]

	@classmethod
	def explain(cls, renderer, service):
		return getattr(cls, "_explain_"+renderer.replace(".", "_"), 
			cls._explainEverything)(service)


class MetaRenderMixin(object):
	"""is a mixin providing some methods useful primarily to metarenderers.
	"""
	def render_tableOfFields(self, ctx, data):
		"""renders a list of dicts in data as a table.

		The columns and header of the table are defined in the headers and data
		patterns.  See the serviceinfo.html template for examples.
		"""
		colNames = [s.strip() for s in 
			ctx.tag.attributes.get("columns", self.defaultColNames).split(",")]
		header = ctx.tag.patternGenerator("header", default=self.defaultHeading)
		return ctx.tag.clear()(
				render=T.directive("sequence"), class_="shorttable")[
			header(pattern="header"),
			T.tr(pattern="item", render=T.directive("mapping"))[
				[T.td[T.slot(name=name)] for name in colNames]]]

	def data_otherServices(self, ctx, data):
		"""returns a list of dicts describing other services provided by the
		the describing RD.

		The class mixing this in needs to provide a describingRD attribute for
		this to work.  This may be the same as self.service.rd, and the
		current service will be excluded from the list in this case.
		"""
		res = []
		for svc in self.describingRD.services:
			if svc is not self.service:
				res.append({"infoURL": svc.getURL("info"),
					"title": unicode(svc.getMeta("title"))})
		return res
	

class ServiceInfoRenderer(MetaRenderer,
		MetaRenderMixin):
	"""is a renderer that shows information about a service.
	"""
	name = "info"
	
	customTemplate = common.loadSystemTemplate("serviceinfo.html")

	def __init__(self, *args, **kwargs):
		grend.ServiceBasedRenderer.__init__(self, *args, **kwargs)
		self.describingRD = self.service.rd

	def render_title(self, ctx, data):
		return ctx.tag["Information on Service '%s'"%unicode(
			self.service.getMeta("title"))]

	defaultColNames = "name,tablehead,description,unit,ucd"
	defaultHeading = T.tr[
		T.th["Name"], T.th["Table Head"], T.th["Description"],
		T.th["Unit"], T.th["UCD"]]
			
	def data_inputFields(self, ctx, data):
		res = [f.asInfoDict() for f in self.service.getInputFields()+
			self.service.serviceKeys]
		res.sort(lambda a,b: cmp(a["name"], b["name"]))
		return res

	def data_htmlOutputFields(self, ctx, data):
		res = [f.asInfoDict() for f in self.service.getCurOutputFields()]
		res.sort(lambda a,b: cmp(a["name"], b["name"]))
		res.sort()
		return res

	def data_votableOutputFields(self, ctx, data):
		queryMeta = svcs.QueryMeta({"_FORMAT": "VOTable", "_VERB": 3})
		res = [f.asInfoDict() 
			for f in self.service.getCurOutputFields(queryMeta)]
		res.sort(lambda a,b: cmp(a["verbLevel"], b["verbLevel"]))
		return res

	def data_rendAvail(self, ctx, data):
		return [{"rendName": rend, 
				"rendExpl": RendExplainer.explain(rend, self.service)}
			for rend in self.service.allowed]

	def data_publications(self, ctx, data):
		res = [{"sets": ",".join(p.sets), "render": p.render} 
			for p in self.service.publications if p.sets]
		return sorted(res, key=lambda v: v["render"])

	defaultDocFactory = common.doctypedStan(
		T.html[
			T.head[
				T.title["Missing Template"]],
			T.body[
				T.p["Infos are only available with a serviceinfo.html template"]]
		])

svcs.registerRenderer(ServiceInfoRenderer)

def basename(tableName):
	if "." in tableName:
		return tableName.split(".")[-1]
	else:
		return tableName


class TableInfoRenderer(grend.ServiceBasedRenderer,
		MetaRenderMixin):
	name = "tableinfo"
	customTemplate = common.loadSystemTemplate("tableinfo.html")

	defaultColNames = "name,tablehead,description,unit,ucd"
	defaultHeading = T.tr[
		T.th["Name"], T.th["Table Head"], T.th["Description"],
		T.th["Unit"], T.th["UCD"]]

	def __init__(self, ctx, service):
		grend.ServiceBasedRenderer.__init__(self, ctx, service)
		self.tableName = inevow.IRequest(ctx).args["tableName"][0]
		self._fillTableInfo()
	
	def _fillTableInfo(self):
		q = base.SimpleQuerier()
		c = q.query("SELECT sourceRd, adql FROM dc.tablemeta WHERE"
			" tableName=%(tableName)s", {"tableName": self.tableName})
		res = c.fetchall()
		if len(res)!=1:
			raise svcs.UnknownURI(
				"%s is no accessible table in the data center"%self.tableName)
		rdId, adql = res[0]
		self.describingRD = base.caches.getRD(rdId)
		self.table = self.describingRD.getById(basename(self.tableName))

	def data_forADQL(self, ctx, data):
		return self.table.adql

	def data_fields(self, ctx, data):
		res = [f.asInfoDict() for f in self.table]
		if not "dbOrder" in inevow.IRequest(ctx).args:
			res.sort(key=lambda item: item["name"])
		return res

	def render_title(self, ctx, data):
		return ctx.tag["Table information for '%s'"%self.tableName]
	
	def render_tablemeta(self, ctx, data):
		return self._doRenderMeta(ctx, metaCarrier=self.table)

	def render_iftablemeta(self, metaName):
		if self.table.getMeta(metaName, propagate=False):
			return lambda ctx, data: ctx.tag
		else:
			return lambda ctx, data: ""

	def render_iftablemetap(self, metaName):
		if self.table.getMeta(metaName, propagate=False):
			return lambda ctx, data: ctx.tag
		else:
			return lambda ctx, data: ""

	def render_rdmeta(self, ctx, data):
		return self._doRenderMeta(ctx, metaCarrier=self.table.rd)

	def render_ifrdmeta(self, metaName):
		if self.table.rd.getMeta(metaName, propagate=False):
			return lambda ctx, data: ctx.tag
		else:
			return lambda ctx, data: ""

	def render_sortOrder(self, ctx, data):
		request = inevow.IRequest(ctx)
		if "dbOrder" in request.args:
			return ctx.tag["Sorted by DB column index. ",
				T.a(href=url.URL.fromRequest(request).remove("dbOrder"))[
					"[Sort alphabetically]"]]
		else:
			return ctx.tag["Sorted alphabetically. ",
				T.a(href=url.URL.fromRequest(request).add("dbOrder", "True"))[
					"[Sort by DB column index]"]]

	# overridden to insert table instead of the service as the thing to take
	# metadata from.
	def _doRenderMeta(self, ctx, raiseOnFail=False, plain=False, 
			metaCarrier=None):
		if not metaCarrier:
			metaCarrier = self.table
		res = grend.ServiceBasedRenderer._doRenderMeta(
			self, ctx, raiseOnFail, plain, metaCarrier)
		return res

	def render_ifmeta(self, metaName, metaCarrier=None):
		if metaCarrier is None:
			metaCarrier = self.table
		return grend.ServiceBasedRenderer._doRenderMeta(
			self, metaName, metaCarrier)

	defaultDocFactory = common.doctypedStan(
		T.html[
			T.head[
				T.title["Missing Template"]],
			T.body[
				T.p["Infos are only available with a tableinfo.html template"]]
		])

svcs.registerRenderer(TableInfoRenderer)


class ExternalRenderer(grend.ServiceBasedRenderer):
	"""A renderer redirecting to an external resource.

	These try to access an external publication on the parent service
	and ask it for an accessURL.  If it doesn't define one, this will
	lead to a redirect loop.

	In the DC, external renderers are mainly used for registration of
	third-party browser-based services.
	"""
	name = "external"

	def renderHTTP(self, ctx):
		# look for a matching publication in the parent service...
		for pub in self.service.publications:
			if pub.render==self.name:
				break
		else: # no publication, 404
			raise svcs.UnknownURI()
		return weberrors.RedirectPage(str(pub.getMeta("accessURL")))

svcs.registerRenderer(ExternalRenderer)
