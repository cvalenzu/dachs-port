"""
This module contains code to query and format the database according to
querulator templates.
"""

import os
import sys
import urllib
import urlparse
import cStringIO
import tarfile
from mx import DateTime

import gavo
from gavo import sqlsupport
from gavo import votable
from gavo.web import querulator


_resultsJs = """
<script type="text/javascript">
emptyImage = new Image();
emptyImage.src = "%(staticURL)s/empty.png";

function showThumbnail(srcUrl) {
	thumb = new Image();
	thumb.src = srcUrl;
	window.document.getElementById("thumbtarget").src = thumb.src;
}

function clearThumbnail() {
	window.document.getElementById("thumbtarget").src = emptyImage.src;
}
</script>
"""%{
	"staticURL": querulator.staticURL,
}

_thumbTarget = """
<img src="%s/empty.png" id="thumbtarget" 
	style="position:fixed;top:0px;left:0px">
"""%(querulator.staticURL)


class Formatter:
	"""is a container for functions that format values from the
	database for the various output formats.

	The idea is that formatting has two phases -- one common to all
	output formats, called preprocessing (useful for completing URLs,
	unserializing stuff, etc), and one that does the real conversion.

	The converters are simply methods with defined names:

	_cook_xxx takes some value from the database and returns another
	value for format hint xxx.

	_xxx_to_fff brings a value with format hint xxx to format fff.

	If a method is not defined, the value is not touched.
	"""
	def __init__(self, template):
		self.template = template

	def _htmlEscape(self, value):
		return str(value).replace("&", "&amp;").replace("<", "&lt;")


	def _cook_date(self, value):
		"""(should check if value is a datetime instance...)
		"""
		return str(value).split()[0]

	def _cook_juliandate(self, value):
		"""(should check if value really is mx.DateTime)
		"""
		return value.jdn

	def _cook_product(self, path):
		"""returns pieces to format a product URL.
		
		Specifically, it qualifies path to a complete URL for the product and
		returns this together with a relative URL for a thumbnail and a
		sufficiently sensible title.
		"""
		return urlparse.urljoin(querulator.serverURL,
			"%s/getproduct/%s?path=%s"%(querulator.rootURL, 
			self.template.getPath(), urllib.quote(path))), \
			"%s/thumbnail/%s?path=%s"%(querulator.rootURL, 
			self.template.getPath(), urllib.quote(path)),\
			os.path.basename(path)

	def _cook_aladinload(self, path):
		"""wraps path into a URL that can be sent to aladin for loading the image.
		"""
		return urlparse.urljoin(querulator.serverURL,
			"%s/getproduct/%s?path=%s"%(querulator.rootURL, 
			self.template.getPath(), urllib.quote(path)))

	def _product_to_html(self, args):
		prodUrl, thumbUrl, title = args
		return ('<a href="%s">%s</a><br>'
			'<a href="%s"  target="thumbs"'
			' onMouseover="showThumbnail(\''
			'%s\')" onMouseout="clearThumbnail()">'
			'[preview]</a>')%(
			prodUrl,
			title,
			thumbUrl, thumbUrl)

	def _product_to_votable(self, args):
		return args[0]
			
	def _url_to_html(self, url):
		return '<a href="%s">[%s]</a>'%(self._htmlEscape(url), 
			self._htmlEscape(urlparse.urlparse(value)[1]))

	def _aladinquery_to_html(self, value):
		aladinPrefix = ("http://aladin.u-strasbg.fr/java/nph-aladin.pl"
			"?frame=launching&script=get%20aladin%28%29%20")
		return '<a href="%s%s" target="aladin">[Aladin]</a>'%(
			aladinPrefix, urllib.quote(value))

	def _aladinquery_to_votable(self, value):
		return ""

	def _aladinload_to_html(self, value):
		aladinPrefix = ("http://aladin.u-strasbg.fr/java/nph-aladin.pl"
			"?frame=launching&script=load%20")
		return '<a href="%s%s" target="aladin">[Aladin]</a>'%(
			aladinPrefix, urllib.quote(value))

	def _string_to_html(self, value):
		return self._htmlEscape(value)

	def format(self, hint, targetFormat, value):
		cooker = getattr(self, "_cook_%s"%hint, lambda a: a)
		formatter = getattr(self, "_%s_to_%s"%(hint, targetFormat),
			lambda a:a)
		return formatter(cooker(value))


def _doQuery(template, context):
	sqlQuery, args = template.asSql(context)
	if not args:
		raise querulator.Error("No valid query parameter found.")

	sys.stderr.write(">>>>> %s %s\n"%(sqlQuery, args))
	querier = sqlsupport.SimpleQuerier()
	return querier.query(sqlQuery, args).fetchall()


def _formatAsVoTable(template, context, stream=False):
	"""returns a callable that writes queryResult as VOTable.
	"""
	queryResult = _doQuery(template, context)
	colDesc = []
	metaTable = sqlsupport.MetaTableHandler()
	defaultTableName = template.getDefaultTable()
	for itemdef in template.getItemdefs():
		try:
			colDesc.append(metaTable.getFieldInfo(
				itemdef["name"], defaultTableName))
		except sqlsupport.FieldError:
			colDesc.append({"fieldName": "ignore", "type": "text"})
	formatter = Formatter(template)
	hints = [itemdef["hint"] for itemdef in template.getItemdefs()]
	rows = []
	for row in queryResult:
		rows.append([formatter.format(
				hint, "votable", item)
			for item, hint in zip(row, hints)])

	if stream:
		def produceOutput(outputFile):
			votable.writeSimpleTable(colDesc, rows, {}, 
				outputFile)
		return produceOutput
	
	else:
		f = cStringIO.StringIO()
		votable.writeSimpleTable(colDesc, rows, {}, f)
		return f.getvalue()


def _getHeaderRow(template):
	"""returns a header row for HTML table output.
	"""
	res = ['<tr>']
	itemdefs = template.getItemdefs()
	metaTable = sqlsupport.MetaTableHandler()
	defaultTableName = template.getDefaultTable()
	for itemdef in itemdefs:
		additionalTag, additionalContent = "", ""
		if itemdef["title"]:
			title = itemdef["title"]
		else:
			fieldInfo = metaTable.getFieldInfo(itemdef["name"], defaultTableName)
			title = fieldInfo["tablehead"]
			if fieldInfo["description"]:
				additionalTag += " title=%s"%repr(fieldInfo["description"])
			if fieldInfo["unit"]:
				additionalContent += "<br>[%s]</br>"%fieldInfo["unit"]
		res.append("<th%s>%s%s</th>"%(additionalTag, title, additionalContent))
	res.append("</tr>")
	return res


def _formatSize(anInt):
	"""returns a size in a "human-readable" form.
	"""
	if anInt<2000:
		return "%dB"%anInt
	if anInt<2000000:
		return "%dk"%(anInt/1000)
	if anInt<2000000000:
		return "%dM"%(anInt/1000000)
	return "%dG"%(anInt/1000000000)


def _formatAsHtml(template, context):
	"""returns an HTML formatted table showing the result of a query for
	template using the arguments specified in context.

	TODO: Refactor, use to figure out a smart way to do templating.
	"""
	def makeTarForm(template):
		doc = []
		if template.getProductCols():
			doc.append('<form action="%s/run/%s" method="post" class="tarForm">\n'%(
				querulator.rootURL, template.getPath()))
			doc.append(template.getHiddenForm(context))
			try:
				sizeEstimate = ' (approx. %s)'%_formatSize(
					template.getProductSizes(context))
			except sqlsupport.OperationalError:
				sizeEstimate = ""
			doc.append('<input type="submit" name="tar" value="Get tar of '
				' matched products%s">\n'%sizeEstimate)
			doc.append('</form>')
		return "\n".join(doc)

	if template.getProductCols():
		# if there's a product col, we assume the table supports the product
		# interface.
		if context.loggedUser:
			template.addConjunction(
				"embargo<=current_date OR owner='%s'"%context.loggedUser)
		else:
			template.addConjunction("embargo<=current_date AND")

	queryResult = _doQuery(template, context)
	tarForm = makeTarForm(template)
	headerRow = _getHeaderRow(template)
	doc = ["<head><title>Result of your query</title>",
		_resultsJs,
		'<link rel="stylesheet" type="text/css"'
			'href="%s/querulator.css">'%querulator.staticURL,
		"</head><body><h1>Result of your query</h1>", _thumbTarget]
	numberMatched = len(queryResult)
	doc.append('<div class="resultMeta">')
	if numberMatched:
		doc.append('<p>Selected items: %d</p>'%numberMatched)
	else:
		doc.append("<p>No data matched your query.</p></body>")
	doc.append('<ul class="queries">%s</ul>'%("\n".join([
		"<li>%s</li>"%qf for qf in template.getConditionsAsText(context)])))
	doc.append("</div>")
	if not numberMatched:
		return "\n".join(doc+["</body>\n"])
	doc.append(template.getLegal())

	if numberMatched>20:
		doc.append(tarForm)
	doc.append('<table border="1" class="results">')
	hints = [itemdef["hint"] for itemdef in template.getItemdefs()]
	formatter = Formatter(template)
	for count, row in enumerate(queryResult):
		if not count%20:
			doc.extend(headerRow)
		doc.append("<tr>%s</tr>"%("".join(["<td>%s</td>"%formatter.format(
				hint, "html", item)
			for item, hint in zip(row, hints)])))
	doc.append("</table>\n")
	doc.append(tarForm)
	doc.append("</body>")
	return "\n".join(doc)


def _formatAsTarStream(template, context):
	"""returns a callable that writes a tar stream of all products matching
	template with arguments in form.

	This assumes that the query supports the "product interface", i.e.,
	has columns owner and embargo.
	"""
	if context.loggedUser:
		template.addConjunction(
			"embargo<=current_date OR owner='%s'"%context.loggedUser)
	else:
		template.addConjunction("embargo<=current_date AND")
	template.setSelectItems("{{datapath||product}}")
	### Ugly ugly ugly -- I really need a good interface to
	### the grammar (or do I just need to improve the grammar and
	### feed in text?
	querier = sqlsupport.SimpleQuerier()
	query, args = template.asSql(context)
	queryResult = querier.query("SELECT accessPath FROM products"
			" WHERE key in (%s)"%query, args).fetchall()
	productCols = template.getProductCols()
	productRoot = gavo.inputsDir
	
	def produceOutput(outputFile):
		outputTar = tarfile.TarFile("results.tar", "w", outputFile)
		for rowInd, row in enumerate(queryResult):
			for colInd in productCols:
				path = querulator.resolvePath(productRoot, row[colInd])
				outputTar.add(path, "%d%04d_%s"%(colInd, 
					rowInd, os.path.basename(path)))
		outputTar.close()

	return produceOutput


def processQuery(template, context):
	"""returns a content type, the result of the query and a dictionary of
	additional headers for a cgi query.

	The return value is for direct plugin into querulator's "framework".
	"""
	if context.hasArgument("submit"):
		return "text/html", _formatAsHtml(template, context), {}
	elif context.hasArgument("submit-votable"):
		return "application/x-votable", _formatAsVoTable(template, context
			), {"Content-disposition": 'attachment; filename="result.xml"'}
	elif context.hasArgument("submit-tar"):
		return "application/tar", _formatAsTarStream(template, context), {
			"Content-disposition": 'attachment; filename="result.tar"'}
	raise querulator.Error("Invalid query.")


def getProduct(context):
	"""returns all data necessary to deliver one product to the user.
	"""
	prodKey = context.getfirst("path")
	querier = sqlsupport.SimpleQuerier()
	matches = querier.query("select owner, embargo, accessPath from products"
		" where key=%(key)s", {"key": prodKey}).fetchall()
	if not matches:
		raise querulator.Error("No product %s known -- you're not guessing,"
			" are you?"%prodKey)
	owner, embargo, accessPath = matches[0]
	if embargo>DateTime.today() and owner!=context.loggedUser:
		raise querulator.Error("The product %s still is under embargo.  The "
			" embargo will be lifted on %s"%(prodKey, embargo))
	return "image/fits", open(os.path.join(
			gavo.inputsDir, accessPath)).read(), {
		"Content-disposition": 'attachment; filename="%s"'%os.path.basename(
			context.getfirst("path")),}
