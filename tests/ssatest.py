"""
Some tests around the SSAP infrastructure.
"""

from gavo import api
from gavo.helpers import testhelpers

def getRD():
	return testhelpers.getTestRD("ssatest.rd")


class RDTest(testhelpers.VerboseTest):
# tests for some aspects of the ssap rd.
	def testUtypes(self):
		srcTable = getRD().getById("hcdtest")
		self.assertEqual("ssa:Access.Reference",
			srcTable.getColumnByName("accref").utype)

	def testDefaultedParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_spectralSI").value, 
			"m")

	def testNullDefaultedParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_creator").value, 
			None)

	def testOverriddenParam(self):
		self.assertEqual(
			getRD().getById("hcdtest").getParamByName("ssa_instrument").value, 
			"DaCHS test suite")
	def testNormalizedDescription(self):
		self.failUnless("matches your query" in
			getRD().getById("hcdouttest").getColumnByName("ssa_score"
				).description)
		
if __name__=="__main__":
	testhelpers.main(RDTest)