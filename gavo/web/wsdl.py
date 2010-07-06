"""
Code to expose our services via SOAP and WSDL.
"""

import cStringIO
import datetime
import sys

import ZSI
from ZSI import TC

from gavo import base
from gavo import svcs
from gavo.base import valuemappers
from gavo.utils.stanxml import (Element, schemaURL, xsiPrefix,
	registerPrefix)
from gavo.utils import ElementTree


SOAPNamespace = 'http://schemas.xmlsoap.org/wsdl/soap/'
HTTPNamespace = 'http://schemas.xmlsoap.org/wsdl/http/'
MIMENamespace = 'http://schemas.xmlsoap.org/wsdl/mime/'
WSDLNamespace = 'http://schemas.xmlsoap.org/wsdl/'
XSDNamespace = "http://www.w3.org/2001/XMLSchema"

registerPrefix("soap", SOAPNamespace,
	schemaURL("wsdlsoap-1.1.xsd"))
registerPrefix("http", HTTPNamespace,
	schemaURL("wsdlhttp-1.1.xsd"))
registerPrefix("mime", MIMENamespace,
	schemaURL("wsdlmime-1.1.xsd"))
registerPrefix("wsdl", WSDLNamespace,
	schemaURL("wsdl-1.1.xsd"))
registerPrefix("xsd", XSDNamespace,
	schemaURL("XMLSchema.xsd"))



class WSDL(object):
	"""is a container for elements from the wsdl 1.1 schema.
	"""
	class WSDLElement(Element):
		_prefix = "wsdl"

	class _tParam(WSDLElement):
		_a_message = None
		_a_name = None

	class binding(WSDLElement):
		_a_name = None
		_a_type = None

	class definitions(WSDLElement):
		_additionalPrefixes = frozenset(["xsi"])
		_a_name = None
		_a_targetNamespace = None
		_a_xmlns_tns = None
		_name_a_xmlns_tns_name = "xmlns:tns"
		_a_xmlns_xsd = XSDNamespace
		_name_a_xmlns_xsd = "xmlns:xsd"
	
	class documentation(WSDLElement): pass
	
	class fault(WSDLElement):
		_a_name = None
	
	class import_(WSDLElement):
		name_ = "import"
		_a_location = None
		_a_namespace = None

	class input(_tParam): 
		_mayBeEmpty = True

	class message(WSDLElement):
		_a_name = None
	
	class operation(WSDLElement):
		_a_name = None
		_a_parameterOrder = None

	class output(_tParam):
		_mayBeEmpty = True
		_a_name = None
		_a_message = None

	class part(WSDLElement):
		_mayBeEmpty = True
		_a_name = None
		_a_type = None

	class port(WSDLElement):
		_mayBeEmpty = True
		_a_binding = None
		_a_name = None

	class portType(WSDLElement):
		_a_name = None

	class service(WSDLElement):
		_a_name = None
	
	class types(WSDLElement): pass
	

class SOAP(object):
	class SOAPElement(Element):
		_prefix = "soap"

	class binding(SOAPElement):
		_mayBeEmpty = True
		_a_style = "rpc"
		_a_transport = "http://schemas.xmlsoap.org/soap/http"

	class body(SOAPElement):
		_mayBeEmpty = True
		_a_use = "encoded"
		_a_namespace = None
		_a_encodingStyle = "http://schemas.xmlsoap.org/soap/encoding"
	
	class operation(SOAPElement):
		_a_name = None
		_a_soapAction = None
		_a_style = "rpc"
	
	class address(SOAPElement):
		_mayBeEmpty = True
		_a_location = None


class XSD(object):
	"""is a container for elements from XML schema.
	"""
	class XSDElement(Element):
		_prefix = "xsd"
		_local = True

	class schema(XSDElement):
		_a_xmlns = XSDNamespace
		_a_targetNamespace = None

	class element(XSDElement):
		_mayBeEmpty = True
		_a_name = None
		_a_type = None
	
	class complexType(XSDElement):
		_a_name = None
	
	class all(XSDElement): pass

	class list(XSDElement):
		_mayBeEmpty = True
		_a_itemType = None
	
	class simpleType(XSDElement):
		_a_name = None
	

def makeTypesForService(service, queryMeta):
	"""returns stanxml definitions for the (SOAP) type of service.

	Only "atomic" input parameters are supported so far, so we can
	skip those.  The output type is always called outList and contains
	of outRec elements.
	"""
	return WSDL.types[
		XSD.schema(targetNamespace=str(service.getMeta("identifier")))[
			XSD.element(name="outRec")[
				XSD.complexType[
					XSD.all[[
						XSD.element(name=f.name, type=base.sqltypeToXSD(
							f.type))[
								WSDL.documentation[f.description],
								WSDL.documentation[f.unit]]
							for f in service.getCurOutputFields(queryMeta)]]]],
			XSD.element(name="outList")[
				XSD.simpleType[
					XSD.list(itemType="outRec")]]]]


def makeMessagesForService(service):
	"""returns stanxml definitions for the SOAP messages exchanged when
	using the service.

	Basically, the input message (called srvInput) consists of some 
	combination of the service's input fields, the output message
	(called srvOutput) is just an outArr.
	"""
	return [
		WSDL.message(name="srvInput")[[
			WSDL.part(name=f.name, type="xsd:"+base.sqltypeToXSD(
				f.type))[
					WSDL.documentation[f.description],
					WSDL.documentation[f.unit]]
				for f in svcs.getRenderer("soap").getInputFields(service)]],
		WSDL.message(name="srvOutput")[
			WSDL.part(name="srvOutput", type="tns:outList")]]


def makePortTypeForService(service):
	"""returns stanxml for a port type named serviceSOAP.
	"""
	parameterOrder = " ".join([f.name 
		for f in svcs.getRenderer("soap").getInputFields(service)])
	return WSDL.portType(name="serviceSOAP")[
		WSDL.operation(name="useService", parameterOrder=parameterOrder) [
			WSDL.input(name="inPars", message="tns:srvInput"),
			WSDL.output(name="outPars", message="tns:srvOutput"),
# XXX TODO: Define fault
		]]


def makeSOAPBindingForService(service):
	"""returns stanxml for a SOAP binding of service.
	"""
	tns = str(service.getMeta("identifier"))
	return WSDL.binding(name="soapBinding", type="tns:serviceSOAP")[
		SOAP.binding,
		WSDL.operation(name="useService")[
			SOAP.operation(soapAction="", name="useService"),
			WSDL.input(name="inPars")[
				SOAP.body(use="encoded", namespace=tns)],
			WSDL.output(name="inPars")[
				SOAP.body(use="encoded", namespace=tns)],
		]
	]
			

def makeSOAPServiceForService(service):
	"""returns stanxml for a WSDL service definition of the SOAP interface
	to service.
	"""
	shortName = str(service.getMeta("shortName"))
	return WSDL.service(name=shortName)[
		WSDL.port(name="soap_%s"%shortName, binding="tns:soapBinding")[
			SOAP.address(location=service.getURL("soap")),
		]
	]


def makeSOAPWSDLForService(service, queryMeta):
	"""returns an stanxml definitions element describing service.

	The definitions element also introduces a namespace named after the
	ivoa id of the service, accessible through the tns prefix.
	"""
	serviceId = str(service.getMeta("identifier"))
	return WSDL.definitions(targetNamespace=serviceId,
			xmlns_tns=serviceId,
			name="%s_wsdl"%str(service.getMeta("shortName")).replace(" ", "_"))[
		WSDL.import_,
		makeTypesForService(service, queryMeta),
		makeMessagesForService(service),
		makePortTypeForService(service),
		makeSOAPBindingForService(service),
		makeSOAPServiceForService(service),
	]


class ToTcConverter(base.FromSQLConverter):
	"""is a quick and partial converter from SQL types to ZSI's type codes.
	"""
	typeSystem = "ZSITypeCodes"
	simpleMap = {
		"smallint": TC.Integer,
		"integer": TC.Integer,
		"int": TC.Integer,
		"bigint": TC.Integer,
		"real": TC.FPfloat,
		"float": TC.FPfloat,
		"boolean": ("boolean", "1"),
		"double precision": TC.FPdouble,
		"double":  TC.FPdouble,
		"text": TC.String,
		"char": TC.String,
		"date": TC.gDate,
		"timestamp": TC.gDateTime,
		"time": TC.gTime,
		"raw": TC.String,
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return TC.String

sqltypeToTC = ToTcConverter().convert


# rather than fooling around with ZSI.SoapWriter's serialization, I use
# the machinery used for VOTables and HTML to serialize weird values.
# It's in place anyway.

_wsdlMFRegistry = valuemappers.ValueMapperFactoryRegistry()
_registerMF = _wsdlMFRegistry.registerFactory


def datetimeMapperFactory(colProps):
	"""returns mapper for datetime objects to python time tuples.
	"""
	if isinstance(colProps["sample"], (datetime.date, datetime.datetime)):
		def mapper(val):
			return val.timetuple()
		return mapper
	if isinstance(colProps["sample"], datetime.timedelta):
		def mapper(val):
			return (0, 0, 0, 0, 0, 0, 0, 0, 0) # FIX!!!
		return mapper
_registerMF(datetimeMapperFactory)

if hasattr(ZSI.SoapWriter, "serialize_header"):
	# New ZSI: Use real namespaces and str(x) to get result

	def serializePrimaryTable(data, service):
		"""returns a SOAP serialization of the DataSet data's primary table.
		"""
		table = data.getPrimaryTable()
		tns = str(service.getMeta("identifier"))
		class Row(TC.Struct):
			def __init__(self):
				TC.Struct.__init__(self, None, [
					sqltypeToTC(f.type)(pname=(tns, f.name))
						for f in table.tableDef],
					pname=(tns, "outRow"))

		class Table(list):
			typecode = TC.Array((tns, 'outRow'), Row(), 
				pname=(tns, 'outList'))

		mapped = Table(
			base.SerManager(table, mfRegistry=_wsdlMFRegistry).getMappedValues())
		sw = ZSI.SoapWriter(nsdict={"tns": tns})
		sw.serialize(mapped).close()
		return str(sw)

else:  # old ZSI -- nuke at some point

	def serializePrimaryTable(data, service):
		"""returns a SOAP serialization of the DataSet data's primary table.
		"""
		table = data.getPrimaryTable()
		class Row(TC.Struct):
			def __init__(self):
				TC.Struct.__init__(self, None, [
			sqltypeToTC(f.type)("tns:"+f.name)
				for f in table.tableDef], 'tns:outRow')

		class Table:
			def __init__(self, name):
				pass
		Table.typecode = TC.Array('outRow', Row(), 'tns:outList')

		outF = cStringIO.StringIO()
		sw = ZSI.SoapWriter(outF, 
			nsdict={"tns": str(service.getMeta("identifier"))})
		mapped = list(base.SerManager(table).getMappedValues(table))
		sw.serialize(mapped, Table.typecode)
		sw.close()
		return outF.getvalue()




def unicodeXML(obj):
	"""returns an XML-clean version of obj's unicode representation.

	I'd expect ZSI to worry about this, but clearly they don't.
	"""
	return unicode(obj
		).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def formatFault(exc, service):
	if isinstance(exc, base.ValidationError):
		val = ZSI.Fault(ZSI.Fault.Client, unicodeXML(exc))
	else:
		val = ZSI.Fault(ZSI.Fault.Server, unicodeXML(exc))
	return val.AsSOAP(
		nsdict={"tns": str(service.getMeta("identifier"))})


def _tryWSDL():
	from gavo.parsing import importparser
	from gavo import resourcecache
	from gavo.web import common
	rd = resourcecache.getRd("ucds/ui")
	sv = rd.get_service("ui")
	print makeSOAPWSDLForService(sv, common.QueryMeta()).render()


def _trySOAP():
	from gavo.parsing import importparser
	from gavo import resourcecache
	from gavo.web import common
	qm = common.QueryMeta()
	rd = resourcecache.getRd("ucds/ui")
	sv = rd.get_service("ui")
	core = sv.get_core()
	core._makeOutputDD()
	try:
		data = core._parseOutput(core._compute(""), qm)
		print serializePrimaryTable(data, sv)
	except Exception, exc:
		print formatFault(exc, sv)

if __name__=="__main__":
	_trySOAP()
