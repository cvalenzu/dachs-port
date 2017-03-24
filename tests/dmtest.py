"""
Tests to do with new-style data modelling and VO-DML serialisation.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

from cStringIO import StringIO
import re

from gavo import base
from gavo import dm
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import svcs
from gavo.dm import dmrd
from gavo.dm import sil
from gavo.formats import votablewrite


def normalizeSIL(sil):
	return re.sub("\s+", " ", sil).strip()


INLINE_MODEL = """
<vo-dml:model xmlns:vo-dml="http://www.ivoa.net/xml/VODML/v1.0">
  <name>localinline</name>
  <title>Local inline DM</title>
  <version>1.0</version>
  <lastModified>2016-07-14Z11:17:00</lastModified>

  <objectType>
  	<vodml-id>Polar</vodml-id>
  	<name>Polar</name>
  	<attribute>
  		<vodml-id>Polar.rule</vodml-id>
  		<name>rule</name>
  		<datatype>
  			<vodml-ref>dachstoy:Cooler</vodml-ref>
  		</datatype>
  	</attribute>
  </objectType>
</vo-dml:model>
"""


class _InlineModel(testhelpers.TestResource):
	def make(self, ignored):
		return dm.Model.fromFile(StringIO(INLINE_MODEL))

_inlineModel = _InlineModel()


class ModelTest(testhelpers.VerboseTest):
	resources = [("inlineModel", _inlineModel)]

	def testMetadataParsing(self):
		toydm = dm.getModelForPrefix("dachstoy")
		self.assertEqual(toydm.description, 
			"A toy model for DaCHS regression testing")
		self.assertEqual(toydm.title, "DaCHS Toy model")
		self.assertEqual(toydm.version, "1.0a-pl23.44c")
		self.assertEqual(toydm.url, "http://docs.g-vo.org/dachstoy")
	
	def testIdAccess(self):
		toydm = dm.getModelForPrefix("dachstoy")
		res = toydm.getByVODMLId("Ruler.width")
		self.assertEqual(res.find("description").text, "A dimension")

	def testPrefixIgnored(self):
		toydm = dm.getModelForPrefix("dachstoy")
		res = toydm.getByVODMLId("dachstoy:Ruler.width")
		self.assertEqual(res.find("description").text, "A dimension")

	def testNoIdAccess(self):
		toydm = dm.getModelForPrefix("dachstoy")
		self.assertRaisesWithMsg(base.NotFoundError,
			"data model element 'Broken.toy' could not be located"
			" in dachstoy data model",
			toydm.getByVODMLId,
			("Broken.toy",))
	
	def testIndexBuilt(self):
		index = dm.getModelForPrefix("dachstoy").idIndex
		self.assertTrue(isinstance(index, dict))
		key, value = index.iteritems().next()
		self.assertTrue(isinstance(key, basestring))
		self.assertTrue(hasattr(value, "attrib"))

	def testGlobalResolution(self):
		res = dm.resolveVODMLId("dachstoy:Ruler.width")
		self.assertEqual(res.find("description").text, "A dimension")

	def testLoadFromFile(self):
		att = self.inlineModel.getByVODMLId("localinline:Polar.rule")
		self.assertEqual(att.find("datatype/vodml-ref").text, "dachstoy:Cooler")
		self.assertEqual(self.inlineModel.prefix, "localinline")

	def testCrossFileResolution(self):
		res = dm.resolveVODMLId("dachstoy:Cooler.tempLimit.value")
		self.assertEqual(res.find("vodml-id").text,
			"quantity.RealQuantity.value")

	def testCrossFileResolutionRecursive(self):
		res = dm.resolveVODMLId("localinline:Polar.rule.tempLimit.value")

	def testUnknownPrefix(self):
		# this standin DM behaviour should change to an exception as this matures
		model = dm.getModelForPrefix("notexisting")
		self.assertEqual(model.title, "DaCHS standin model")
		self.assertEqual(model.url, "urn:dachsjunk:not-model:notexisting")


class TestSILGrammar(testhelpers.VerboseTest):
	def testPlainObject(self):
		res = sil.getGrammar().parseString("""
			(:testclass) {
				attr1: plain12-14
				attr2: "this is a ""weird"" literal"
			}""")
		self.assertEqual(res[0],
			('obj', ':testclass', [
				('attr', 'attr1', 'plain12-14'), 
				('attr', 'attr2', 'this is a "weird" literal')]))
	
	def testNestedObject(self):
		res = sil.getGrammar().parseString("""
			(:testclass) {
				attr1: (:otherclass) {
						attr2: val
					}
			}""")
		self.assertEqual(res[0],
			('obj', ':testclass', [
				('attr', 'attr1', 
					('obj', ':otherclass', [ 
						('attr', 'attr2', 'val')]))]))

	def testObjectCollection(self):
		res = sil.getGrammar().parseString("""
			(:testclass) {
				seq: (:otherclass)[
					{attr1: a}
					{attr1: b}
					{attr1: c}]}""")
		self.assertEqual(res[0], 
			('obj', ':testclass', [
				('attr', 'seq', 
					('coll', ':otherclass', [
						('obj', None, [('attr', 'attr1', 'a')]),
						('obj', None, [('attr', 'attr1', 'b')]),
						('obj', None, [('attr', 'attr1', 'c')]),]))]))

	def testImmediateCollection(self):
		res = sil.getGrammar().parseString("""
			(:testclass) {
				seq: [a "b c d" @e]}""")
		self.assertEqual(res[0],
			('obj', ':testclass', 
				[('attr', 'seq', 
					('coll', None, ['a', 'b c d', 'e']))]))


class TestSILParser(testhelpers.VerboseTest):
	def testNestedObject(self):
		res = sil.getAnnotation("""
			(testdm:testclass) {
				attr1: (testdm:otherclass) {
						attr2: val
					}
			}""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { (testdm:otherclass) { attr2: val} }')

	def testObjectCollection(self):
		res = sil.getAnnotation("""
			(testdm:testclass) {
				seq: (testdm:otherclass)[
					{attr1: a}
					{attr1: b}
					{attr1: c}]}""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { seq: (testdm:otherclass)'
			' [{ attr1: a} { attr1: b} { attr1: c} ] }')

	def testAtomicCollection(self):
		res = sil.getAnnotation("""
			(testdm:testclass) {
				seq: [a "b c" 3.2]}""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { seq: [a "b c" 3.2] }')

	def testComments(self):
		res = sil.getAnnotation("""/* comment with stuff */
			(testdm:testclass) /* another comment */ { /* and yet one */
				seq: [a "b c" 3.2] /* here's an additional comment */}
				/* final comment */""", dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { seq: [a "b c" 3.2] }')

	def testNoUntypedRoot(self):
		self.assertRaisesWithMsg(base.StructureError,
			"Root of Data Model annotation must have a type.",
			sil.getAnnotation,
			("{attr1: (testdm:otherclass) {attr2: val}}",
				dmrd.getAnnotationMaker(None)))

	def testWithoutType(self):
		res =sil.getAnnotation("(testdm:testclass){attr1: {attr2: val}}",
			dmrd.getAnnotationMaker(None))
		self.assertEqual(normalizeSIL(res.asSIL()),
			'(testdm:testclass) { { attr2: val} }')

def getByID(tree, id):
	# (for checking VOTables)
	res = tree.xpath("//*[@ID='%s']"%id)
	assert len(res)==1, "Resolving ID %s gave %d matches"%(id, len(res))
	return res[0]


class AnnotationTest(testhelpers.VerboseTest):
	def testAtomicValue(self):
		t = base.parseFromString(rscdef.TableDef,
			"""<table id="foo">
				<dm>
					(testdm:testclass) {
						attr1: test
					}
				</dm></table>""")
		self.assertEqual(t.annotations[0].type, "testdm:testclass")
		self.assertEqual(t.annotations[0].childRoles["attr1"].value,
			"test")
		self.assertEqual(t.annotations[0].childRoles["attr1"].instance(), 
			t.annotations[0])
	
	def testColumnReference(self):
		t = base.parseFromString(rscdef.TableDef,
			"""<table id="foo">
				<dm>
					(testdm:testclass) {
						attr1: @col1
					}
				</dm><column name="col1" ucd="stuff"/></table>""")
		col = t.annotations[0].childRoles["attr1"].value
		self.assertEqual(col.ucd, "stuff")


# Use this table (rather than _RealDMTable) to build tests against
# DMs we can control for testing purposes.
class _AnnotationTable(testhelpers.TestResource):
	def make(self, deps):
		td = base.parseFromString(rscdef.TableDef,
			"""<table id="foo">
					<dm>
						(dachstoy:Ruler) {
							width: @col1
							location: 
								(dachstoy:Location) {
									x: 0.1
									y: @raj2000
									z: @dej2000
								}
							maker: [
								Oma "Opa Rudolf" @artisan]
						}
					</dm>
					<dm>
						(geojson:FeatureCollection) {
							feature: {
								geometry: sepcoo
								long: @raj2000
								lat: @col1
							}
						}
					</dm>
					<param name="artisan" type="text">Onkel Fritz</param>
					<column name="col1" ucd="stuff" type="text"/>
					<column name="raj2000"/>
					<column name="dej2000"/>
				</table>""")
		
		return rsc.TableForDef(td, rows=[
			{"col1": "1.5", "raj2000": 0.3, "dej2000": 3.1}])

_ANNOTATION_TABLE = _AnnotationTable()


class _DirectVOT(testhelpers.TestResource):
	resources = [("table", _ANNOTATION_TABLE)]

	def make(self, deps):
		return testhelpers.getXMLTree(votablewrite.getAsVOTable(	
			deps["table"],
			ctx=votablewrite.VOTableContext(version=(1,4))), debug=False)


class DirectSerTest(testhelpers.VerboseTest):
	resources = [("tree", _DirectVOT())]

	def testVODMLModelDefined(self):
		dmgroup = self.tree.xpath(
			"//GROUP[@vodml-type='vo-dml:Model']"
			"[PARAM[@vodml-role='name']/@value='vo-dml']")[0]
		self.assertEqual(
			dmgroup.xpath("PARAM[@vodml-role='name']")[0].get("value"),
			"vo-dml")
		self.assertEqual(
			dmgroup.xpath("PARAM[@vodml-role='url']")[0].get("value"),
			"http://www.ivoa.net/dm/VO-DML.vo-dml.xml")
		self.assertEqual(
			dmgroup.xpath("PARAM[@vodml-role='version']")[0].get("value"),
			"0.x")

	def testTestModelDefined(self):
		dmgroup = self.tree.xpath(
			"//GROUP[@vodml-type='vo-dml:Model']"
			"[PARAM[@vodml-role='name']/@value='dachstoy']")[0]

		self.assertEqual(
			dmgroup.xpath("PARAM[@vodml-role='url']")[0].get("value"),
			"http://docs.g-vo.org/dachstoy")
		self.assertEqual(
			dmgroup.xpath("PARAM[@vodml-role='version']")[0].get("value"),
			"1.0a-pl23.44c")

	def testNoExtraModels(self):
		self.assertEqual(3,
			len(self.tree.xpath("//GROUP[@vodml-type='vo-dml:Model']")))

	def testTestclassInstancePresent(self):
		res = self.tree.xpath(
			"RESOURCE/TABLE/GROUP[@vodml-type='dachstoy:Ruler']")
		self.assertEqual(len(res), 1)
	
	def testLiteralSerialized(self):
		par = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[@vodml-type='dachstoy:Location']"
			"/PARAM[@vodml-role='x']")[0]
		self.assertEqual(par.get("value"), "0.1")
		self.assertEqual(par.get("datatype"), "unicodeChar")

	def testChildColumnAnnotated(self):
		fr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP[@vodml-type='dachstoy:Ruler']"
			"/FIELDref[@vodml-role='width']")[0]
		col = getByID(self.tree, fr.get("ref"))
		self.assertEqual(col.get("name"), "col1")

	def testNestedColumnAnnotated(self):
		fr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[@vodml-type='dachstoy:Location']"
			"/FIELDref[@vodml-role='y']")[0]
		col = getByID(self.tree, fr.get("ref"))
		self.assertEqual(col.get("name"), "raj2000")

	def testCollection(self):
		gr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[@vodml-role='maker']")
		self.assertEqual(len(gr), 1)
		params = gr[0].xpath("PARAM")
		self.assertEqual(len(params), 2)
		self.assertEqual(params[0].get("value"), "Oma")
		self.assertEqual(params[1].get("value"), "Opa Rudolf")

	def testParamReferenced(self):
		gr = self.tree.xpath(
			"RESOURCE/TABLE/GROUP/GROUP[@vodml-role='maker']")[0]
		paramref = gr.xpath("PARAMref")[0]
		self.assertEqual(paramref.get("vodml-role"), "maker")
		par = getByID(self.tree, paramref.get("ref"))
		self.assertEqual(par.get("value"), "Onkel Fritz")


class CopyTest(testhelpers.VerboseTest):
	resources = [("table", _ANNOTATION_TABLE)]

	def testParamDMRoleLink(self):
		ann = self.table.tableDef.getByName("artisan").dmRoles[0]()
		self.assertEqual(ann.name, "maker")

	def testColumnDMRoleLink(self):
		ann = self.table.tableDef.getByName("raj2000").dmRoles[0]()
		self.assertEqual(ann.name, "y")
	
	def testDMRolesCopying(self):
		col = self.table.tableDef.getByName("raj2000")
		colCopy = col.copy(None)
		self.assertEqual(colCopy.dmRoles.__class__.__name__,
			"OldRoles")

	def testSimpleCopy(self):
		newTD = self.table.tableDef.copy(None)
		ann = newTD.getAnnotationOfType("dachstoy:Ruler")
		self.assertEqual(ann["maker"][0], "Oma")
		self.assertEqual(ann["maker"][2].value, newTD.getByName("artisan"))
		self.assertEqual(ann["width"].value, newTD.getByName("col1"))
		self.assertEqual(ann["location"]["x"], "0.1")
		self.assertEqual(ann["location"]["y"].value,
			newTD.getByName("raj2000"))

		ann = newTD.getAnnotationOfType("geojson:FeatureCollection")
		self.assertEqual(ann["feature"]["geometry"], "sepcoo")
		self.assertEqual(ann["feature"]["long"].value,
			newTD.getByName("raj2000"))

	def testPartialCopy(self):
		newTD = self.table.tableDef.change(id="copy", columns=[
			self.table.tableDef.getByName("dej2000").copy(None)],
			params=[])
		ann = newTD.getAnnotationOfType("dachstoy:Ruler")
		self.assertEqual(ann["maker"][0], "Oma")
		self.assertEqual(len(ann["maker"]), 2)
		self.assertEqual(ann["location"]["z"].value,
			newTD.getByName("dej2000"))
		self.assertFalse("y" in ann["location"])
		# the following assertion states that annotations without any
		# columns/params referenced are not copied into the destination
		# table.
		self.assertEqual(len(newTD.annotations), 1)
	
	def testOutputTableConstruction(self):
		newTD = base.makeStruct(svcs.OutputTableDef,
			columns=[
				self.table.tableDef.getByName("raj2000").copy(None),
				self.table.tableDef.getByName("dej2000").copy(None)],
			params=[
				self.table.tableDef.getByName("artisan").copy(None)])
		newTD.updateAnnotationFromChildren()
		ann = newTD.getAnnotationOfType("dachstoy:Ruler")
		self.assertEqual(ann["maker"][0], "Oma")
		self.assertEqual(ann["location"]["z"].value,
			newTD.getByName("dej2000"))
		self.assertEqual(len(ann["maker"]), 3)

		ann = newTD.getAnnotationOfType("geojson:FeatureCollection")
		self.assertEqual(ann["feature"]["geometry"], "sepcoo")
		self.assertEqual(ann["feature"]["long"].value,
			newTD.getByName("raj2000"))


# When you're looking for a table to pollute with custom 
# constructs, use _AnnotationTable.
class _RealDMTable(testhelpers.TestResource):
	# well, of course, these are not the real DMs at this point.
	# as the come out, they should go in here, and this should
	# be used to test validation.
	def make(self, deps):
		rd = base.parseFromString(rscdesc.RD,
# this needs a resource container since we need id resolution
			"""
<resource schema="test">
<table id="foo">
	<dm>
		(ds:DataSet) {
			ProductType: timeseries
			calibLevel: 1
			dataId: @pubDID
			creator: [ 
				"Joe Cool"
				"Charlie Brown"
			]
			observationID: @pubDID 
			target: {
				name: @targetName
				position: @targetPos
			}
		}
	</dm>

	<dm id="targetPos">
		(stc2:Coordinates) {
			spatial: {
				frame: {
					referenceSystem: ICRS
				}
				c1: @raj2000
				c2: @dej2000
			}
			temporal: {
				frame: {
					timeScale: TT
					referencePosition: HELIOCENTER
				}
				value: @HJD
			}
		}
	</dm>

	<param name="raj2000" type="double precision"
		ucd="pos.eq.ra" unit="deg"/>
	<param name="dej2000" type="double precision"
		ucd="pos.eq.dec" unit="deg"/>
	<param name="targetName" type="text"/>
	<param name="pubDID" type="text"/>

	<column name="HJD" type="double precision"/>

</table>
</resource>""")
		
		t = rsc.TableForDef(rd.tables[0], rows=[
			{"HJD": 2000000.125}])
		t.setParam("raj2000", 230)
		t.setParam("dej2000", -45)
		return t

_REAL_DM_TABLE = _RealDMTable()


class _RealDMVOT(testhelpers.TestResource):
	resources = [("table", _REAL_DM_TABLE)]

	def make(self, deps):
		return testhelpers.getXMLTree(votablewrite.getAsVOTable(	
			deps["table"],
			ctx=votablewrite.VOTableContext(version=(1,4))), debug=False)

_REAL_DM_VOT = _RealDMVOT()


class ObjReftest(testhelpers.VerboseTest):
	resources = [("table", _REAL_DM_TABLE),
		("serialized", _REAL_DM_VOT)]

	def testInterInstanceAnnotation(self):
		ds = self.table.tableDef.getAnnotationOfType("ds:DataSet")
		pos = ds["target"]["position"].objectReferenced
		self.assertEqual(pos["spatial"]["frame"]["referenceSystem"],
			"ICRS")
		self.assertEqual(pos["spatial"]["c1"].value.name, "raj2000")

	def testInstanceRefSerialisation(self):
		grouprefs = self.serialized.xpath(
			"//GROUP[@vodml-type='ds:DataSet']/GROUP[@vodml-role='target']"
			"/GROUP[@vodml-role='position']")
		self.assertEqual(len(grouprefs), 1)
		pos = self.serialized.xpath(
			"//GROUP[@ID='%s']"%grouprefs[0].get("ref"))[0]
		self.assertEqual(pos.get("vodml-type"), "stc2:Coordinates")
		self.assertEqual(pos.xpath("GROUP[@vodml-role='temporal']"
			"/GROUP[@vodml-role='frame']"
			"/PARAM[@vodml-role='referencePosition']")[0].get("value"),
			"HELIOCENTER")


if __name__=="__main__":
	testhelpers.main(DirectSerTest)
