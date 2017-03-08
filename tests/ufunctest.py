"""
Tests for ADQL user defined functions and Region expressions.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import re
import unittest

from gavo.helpers import testhelpers

from gavo import adql
from gavo import rscdesc
from gavo import utils
from gavo.protocols import adqlglue
from gavo.protocols import simbadinterface # for ufunc registration
from gavo.adql import nodes 
from gavo.adql import ufunctions 

import adqltest
import tresc


class BasicTest(unittest.TestCase):
	def testRaising(self):
		self.assertRaises(adql.UfuncError, adql.parseToTree,
			"SELECT x FROM y WHERE gavo_foo(8)=7")

	def testFlattening(self):
		self.assertEqual(
			adql.parseToTree("SELECT x FROM y WHERE 1=gavo_match('x.*', frob)"
				).flatten(),
			"SELECT x FROM y WHERE 1 = (CASE WHEN frob ~ 'x.*' THEN 1 ELSE 0 END)")


class _UfuncDefinition(testhelpers.TestResource):
	def make(self, nodeps):
		@adql.userFunction("gavo_testingXXX",
			"(x INTEGER) -> INTEGER",
			"""
			This function returns its argument decreased by one.
			
			This is the end.
			""")
		def _f1(args):
			if len(args)!=1:
				raise adql.UfuncError("gavo_testingXXX takes only a single argument")
			return "(%s+1)"%nodes.flatten(args[0])
		
		@adql.userFunction("gavo_testingYYY",
			"(x DOUBLE PRECISION) -> DOUBLE PRECISION",
			"This function will not work (since it's not defined in the DB)")
		def _f2(args):
			return None
	
	def clean(self, ignored):
		del ufunctions.UFUNC_REGISTRY["GAVO_TESTINGXXX"]
		del ufunctions.UFUNC_REGISTRY["GAVO_TESTINGYYY"]


_ufuncDefinition = _UfuncDefinition()

class UfuncDefTest(testhelpers.VerboseTest):
	resources = [("ufunc_defined", _ufuncDefinition),
		("adqlTestTable", adqltest.adqlTestTable),
		("querier", adqltest.adqlQuerier)]

	def testUfuncMeta(self):
		f = ufunctions.UFUNC_REGISTRY["GAVO_TESTINGXXX"]
		self.assertEqual(f.adqlUDF_name, "gavo_testingXXX")
		self.assertEqual(f.adqlUDF_signature, 
			"gavo_testingXXX(x INTEGER) -> INTEGER")
		self.assertEqual(f.adqlUDF_doc, "This function returns its argument"
			" decreased by one.\n\nThis is the end.")
	
	def testFlattening(self):
		self.assertEqual(
			adql.parseToTree("SELECT GAVO_TESTINGXXX(frob) FROM x"
				).flatten(),
			"SELECT (frob+1) FROM x")
	
	def testFlatteningTransparent(self):
		self.assertEqual(
			adql.parseToTree("SELECT GAVO_TESTINGYYY(CIRCLE('', a, b, c), u) FROM x"
				).flatten(),
			'SELECT GAVO_TESTINGYYY(CIRCLE(a, b, c), u) FROM x')

	def testQueryInSelectList(self):
		self.assertEqual(adqlglue.query(self.querier,
			"SELECT GAVO_TESTINGXXX(rV) FROM test.adql where mag<0").rows[0].values(),
			[29.])

	def testQueryInWhereClause(self):
		self.assertEqual(adqlglue.query(self.querier,
			"SELECT rV FROM test.adql where GAVO_TESTINGXXX(rV)>0").rows[0].values(),
			[0.])


class _UfuncTestbed(tresc.RDDataResource):
	"""A table that contains test material for ufuncs.

	If you write queries against this, make sure you survive schema
	*and data* extensions.  They are sure to come as new UDFs need exercise.
	Use the kind column as necessary.
	"""
	rdName = "data/ufuncex.rd"
	dataId = "import"

_ufuncTestbed = _UfuncTestbed()


class BuiltinUfuncTest(testhelpers.VerboseTest):
	resources = [
		("ssaTestTable", tresc.ssaTestTable),
		("ufuncTestTable", _ufuncTestbed),
		("querier", adqltest.adqlQuerier)]

	def testHaswordQuery(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ssa_targname from test.hcdtest where"
			" 1=ivo_hasword(ssa_targname, 'rat hole')").rows,
			[{'ssa_targname': u'rat hole in the yard'}])

	def testHaswordQueryInsensitive(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ssa_targname from test.hcdtest where"
			" 1=ivo_hasword(ssa_targname, 'Booger')").rows,
			[{'ssa_targname': u'booger star'}])

	def testHaswordQueryBorders(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ssa_targname from test.hcdtest where"
			" 1=ivo_hasword(ssa_targname, 'ooger')").rows,
			[])
	
	def testHashlistSimple(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ivo_hashlist_has('bork#nork#gaob norm', 'nork') as h"
				" FROM test.hcdtest").rows,
			[{'h': 1}])

	def testHashlistBorders(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ivo_hashlist_has('bork#nork#gaob norm', 'ork') as h"
				" FROM test.hcdtest").rows,
			[{'h': 0}])

	def testHashlistNocase(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select distinct ivo_hashlist_has('bork#nork#gaob norm', 'nOrk') as h"
				" FROM test.hcdtest").rows,
			[{'h': 1}])
	
	def testNocasematch(self):
		self.assertEqual(len(adqlglue.query(self.querier,
			"select ssa_targname FROM test.hcdtest"
				" WHERE 1=ivo_nocasematch(ssa_targname, 'BOOGER%')").rows),
			2)
	
	def testToMJD(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select gavo_to_mjd(dt) as mjd from test.ufuncex where testgroup='jd'"
			).rows, [{'mjd': 45917.5}])

	def testToJD(self):
		self.assertEqual(adqlglue.query(self.querier,
			"select gavo_to_jd(dt) as jd from test.ufuncex where testgroup='jd'"
			).rows, [{'jd': 2445918.0}])


class RegionTest(unittest.TestCase):
	"""tests for sane parsing of our default region expressions.
	"""
	resources = [("fs", tresc.fakedSimbad)]

	def testRaising(self):
		"""tests for plausible exceptions.
		"""
		self.assertRaises(adql.RegionError, adql.parseToTree,
			"SELECT x FROM y WHERE 1=CONTAINS(REGION('78y'), REGION('zzy9'))")
		self.assertRaises(adql.RegionError, adql.parseToTree,
			"SELECT x FROM y WHERE 1=CONTAINS(REGION(dbColumn || otherColumn),"
			" CIRCLE('ICRS', 10, 10 ,2))")


def getMorphed(query):
	return nodes.flatten(adql.morphPG(adql.parseToTree(query))[1])


class RRFunctionsTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	resources = [("ufuncTestTable", _ufuncTestbed)]
	def _runTest(self, sample):
		query, expected = sample
		self.assertEqualIgnoringAliases(getMorphed(query), expected)
	
	samples = [
		("select testgroup from test.ufuncex where 1=ivo_hasword(testgroup, 'abc')",
			"SELECT testgroup FROM test.ufuncex WHERE ("
			"to_tsvector('english', testgroup)"
				" @@ plainto_tsquery('english', 'abc'))"),
 		("select ivo_hasword(testgroup, 'abc') from test.ufuncex",
 			"SELECT IVO_HASWORD(testgroup, 'abc') ASWHATEVER FROM test.ufuncex"),
		("select testgroup from test.ufuncex where"
			" 1=ivo_hashlist_has('a#b#c', testgroup)",
			"SELECT testgroup FROM test.ufuncex WHERE lower(testgroup) ="
			" ANY(string_to_array('a#b#c', '#'))"),
		("select testgroup from test.ufuncex where"
			" 1=ivo_nocasematch(testgroup, 'honk%')",
			"SELECT testgroup FROM test.ufuncex WHERE (LOWER(testgroup) like 'honk%')")
	]
	

class AggFunctionsTest(testhelpers.VerboseTest):
	resources = [
		("ssaTestTable", tresc.ssaTestTable),
		("querier", adqltest.adqlQuerier)]

	def testStringAggMorph(self):
		self.assertEqualIgnoringAliases(
			getMorphed("select ivoid, ivo_string_agg(res_subject, ',')"
				" from rr.res_subject group by ivoid"),
			"SELECT ivoid, string_agg(res_subject, ',') ASWHATEVER"
			" FROM rr.res_subject GROUP BY ivoid")

	def testStringAddExec(self):
		res = adqlglue.query(self.querier,
			"SELECT ivo_string_agg(accref || mime, '#') as goo, ssa_pubdid"
				" from test.hcdtest group by ssa_pubdid order by ssa_pubdid").rows
		self.assertEqual(res[0]["ssa_pubdid"], 'ivo://test.inv/test1')
		self.assertEqual(set(res[0]["goo"].split("#")),
			set('data/spec1.ssatestimage/jpeg#data/spec1.ssatest.'
				'votapplication/x-votable+xml'.split("#")))


class HealpixFunctionsTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	resources = [("ufuncTestTable", _ufuncTestbed)]
	def _runTest(self, sample):
		query, expected = sample
		self.assertEqualIgnoringAliases(getMorphed(query), expected)
	
	samples = [
		("select ivo_healpix_index(10, point('', ra, dec)) from test.ufuncex",
			"SELECT healpix_nest(10, spoint(RADIANS(ra), RADIANS(dec))) ASWHATEVER FROM test.ufuncex"),
		("select ivo_healpix_index(10, p) from test.ufuncex",
			"SELECT healpix_nest(10, p) ASWHATEVER FROM test.ufuncex"),
		("select ivo_healpix_center(10, 40002) from test.ufuncex",
			"SELECT center_of_healpix_nest(10, 40002) ASWHATEVER FROM test.ufuncex"),
	]


class HealpixExecTest(testhelpers.VerboseTest):
	resources = [
		("querier", adqltest.adqlQuerier),
		("test_ufunc", _ufuncTestbed)]

	def testIndexAndPoint(self):
		res = adqlglue.query(self.querier,
			"SELECT ivo_healpix_index(10, p) as hpi"
			" from test.ufuncex WHERE dt<'1985-01-01'")
		self.assertEqual(res.rows[0]["hpi"], 2937727L)
	
	def testCenterFinding(self):
		res = adqlglue.query(self.querier,
			"SELECT ivo_healpix_center(10, ivo_healpix_index(10, ra, dec)) as pt"
			" from test.ufuncex WHERE dt<'1985-01-01'")
		self.assertAlmostEqual(res.rows[0]["pt"].y, -12.25362992*utils.DEG)
		self.assertAlmostEqual(res.rows[0]["pt"].x, 23.51074219*utils.DEG)
		self.assertEqual(res.tableDef.columns[0].type, "spoint")


class SimbadpointTest(testhelpers.VerboseTest):
	resources = [
		("test_ufunc", _ufuncTestbed)]

	def testBadArgcount(self):
		self.assertRaisesWithMsg(adql.UfuncError,
			"gavo_simbadpoint takes exactly one string literal as argument",
			getMorphed,
			("SELECT * from test.ufuncex WHERE 1=CONTAINS("
				"gavo_simbadpoint('aldebaran', 23), CIRCLE('ICRS', ra, dec, 1))",))

	def testBadArgtype(self):
		self.assertRaisesWithMsg(adql.UfuncError,
			"gavo_simbadpoint takes exactly one string literal as argument",
			getMorphed,
			("SELECT * from test.ufuncex WHERE 1=CONTAINS("
				"gavo_simbadpoint(testgroup), CIRCLE('ICRS', ra, dec, 1))",))

	def testBadName(self):
		self.assertRaisesWithMsg(adql.UfuncError,
			"No simbad position for 'Henker'",
			getMorphed,
			("SELECT * from test.ufuncex WHERE 1=CONTAINS("
				"gavo_simbadpoint('Henker'), CIRCLE('ICRS', ra, dec, 1))",))

	def testResolution(self):
		self.assertEqual(getMorphed("SELECT * from test.ufuncex WHERE 1=CONTAINS("
				"gavo_simbadpoint('M1'),"
				" CIRCLE('ICRS', ra, dec, 1))"),
			"SELECT * FROM test.ufuncex WHERE ((spoint(RADIANS(83.633083),"
			" RADIANS(22.014500))) @ (scircle(spoint(RADIANS(ra), RADIANS(dec)),"
			" RADIANS(1))))")


class MotionTest(testhelpers.VerboseTest):
	resources = [
		("test_ufunc", _ufuncTestbed),
		("querier", adqltest.adqlQuerier),]

	def testQueryPMSelect(self):
		res = adqlglue.query(self.querier,
			"SELECT ivo_apply_pm(ra, dec, 0.01, -0.01, 23)"
			" as newpos from test.ufuncex")
		self.assertEqual(res.rows[0]["newpos"].asSTCS('ICRS'),
			"Position ICRS 23.5491058437 -12.48")

	def testQueryConstraint(self):
		res = adqlglue.query(self.querier,
			"SELECT testgroup from test.ufuncex"
			" where 1=Contains("
			"ivo_apply_pm(ra, dec, 0.01, -0.01, 23),"
			"CIRCLE('ICRS', 23.5491058437, -12.48, 0.01))")
		self.assertEqual(len(res.rows), 1)
		self.assertEqual(res.rows[0]["testgroup"], "jd")


if __name__=="__main__":
	testhelpers.main(UfuncDefTest)
