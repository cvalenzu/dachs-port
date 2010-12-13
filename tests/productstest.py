"""
Tests for the products infrastructure.
"""

from cStringIO import StringIO
import os
import tarfile

from gavo import api
from gavo import svcs
from gavo.helpers import testhelpers
from gavo.protocols import products
from gavo.web import producttar

import tresc


class _TestWithProductsTable(testhelpers.VerboseTest):
	resources = [('conn', tresc.prodtestTable), ('users', tresc.testUsers)]

	def setUp(self):
		testhelpers.VerboseTest.setUp(self)
		self.service = api.getRD("//products").getById("p")


class ProductCoreTest(_TestWithProductsTable):
	"""tests for the products core.
	"""
	timeout = 10

	def _assertMatchedProducts(self, prodClass, prodDescs, foundRows):
		expectedRows = [{"source": prodClass(os.path.abspath(p), m)}
			for p, m in prodDescs]
		# ouch: I should be comparing *sets* here, but for now I'm
		# too lazy to make all products easily hashable.
		self.assertEqual(expectedRows, foundRows)
			
	def testNormal(self):
		"""tests for resolution of "normal" products.
		"""
		res = self.service.runFromDict({"accref": "data/b.imp"}, "get")
		self._assertMatchedProducts(products.PlainProduct,
			[('data/b.imp', 'text/plain')],
			res.original.getPrimaryTable().rows)

	def testRestrictedAnonymous(self):
		"""tests for resolution of restricted products for an anonymous user.
		"""
		res = self.service.runFromDict({"accref": "data/a.imp"})
		self._assertMatchedProducts(products.UnauthorizedProduct,
			[('data/a.imp', 'text/plain')],
			res.original.getPrimaryTable().rows)

	def testRestrictedGoodAuth(self):
		"""tests for return of a protected product with good cred.
		"""
		qm = svcs.QueryMeta()
		qm["user"], qm["password"] = "X_test", "megapass"
		res = self.service.runFromDict({"accref": "data/a.imp"}, queryMeta=qm)
		self._assertMatchedProducts(products.PlainProduct,
			[('data/a.imp', 'text/plain')],
			res.original.getPrimaryTable().rows)
		src = res.original.getPrimaryTable().rows[0]["source"]
		f = StringIO()
		src(f)
		self.assertEqual(f.getvalue(), 'alpha: 23 34 33.45\ndelta:'
			' -45 34 59.7\nobject: gabriel\nembargo: 2030-12-31\n')

	def testRestrictedBadAuth(self):
		"""tests for return of a protected product with bad cred.
		"""
		qm = svcs.QueryMeta()
		qm["user"], qm["password"] = "test", "wrong"
		res = self.service.runFromDict({"accref": "data/a.imp"}, queryMeta=qm)
		self._assertMatchedProducts(products.UnauthorizedProduct,
			[('data/a.imp', 'text/plain')],
			res.original.getPrimaryTable().rows)

	def testRestrictedWrongUser(self):
		"""tests for return of a protected product with bad cred.
		"""
		qm = svcs.QueryMeta()
		qm["user"], qm["password"] = "Y_test", "megapass"
		res = self.service.runFromDict({"accref": "data/a.imp"}, queryMeta=qm)
		self._assertMatchedProducts(products.UnauthorizedProduct,
			[('data/a.imp', 'text/plain')],
			res.original.getPrimaryTable().rows)

### XXX TODO: Play with content types


class TarTest(_TestWithProductsTable):
	def setUp(self):
		_TestWithProductsTable.setUp(self)
		self.tarService = self.service.rd.getById("getTar")

	def _getTar(self, inDict, qm=None):
		res = self.tarService.runFromDict(inDict, "form", queryMeta=qm)
		dest = StringIO()
		producttar.getTarMaker()._productsToTar(res.original, dest)
		return dest.getvalue()

	def _assertIsTar(self, res):
		f = tarfile.open("data.tar", "r:*", StringIO(res))
		f.close()

	def testFreeNoAuth(self):
		res = self._getTar({"pattern": "test.prodtest#data/b.imp"})
		self._assertIsTar(res)
		self.failUnless("\nobject: michael" in res)

	def testAllNoAuth(self):
		res = self._getTar({"pattern": "test.prodtest#%"})
		self._assertIsTar(res)
		self.failUnless("\nobject: michael" in res)
		self.failUnless("This file is embargoed.  Sorry" in res)
		self.failIf("\nobject: gabriel" in res)
	
	def testAllWithAuth(self):
		qm = svcs.QueryMeta()
		qm["user"], qm["password"] = "X_test", "megapass"
		res = self._getTar({"pattern": "test.prodtest#%"}, qm)
		self._assertIsTar(res)
		self.failUnless("\nobject: michael" in res)
		self.failIf("This file is embargoed.  Sorry" in res)
		self.failUnless("\nobject: gabriel" in res)
	
	def testAllWithWrongAuth(self):
		qm = svcs.QueryMeta()
		qm["user"], qm["password"] = "Y_test", "megapass"
		res = self._getTar({"pattern": "test.prodtest#%"}, qm)
		self._assertIsTar(res)
		self.failUnless("\nobject: michael" in res)
		self.failUnless("This file is embargoed.  Sorry" in res)
		self.failIf("\nobject: gabriel" in res)


if __name__=="__main__":
	testhelpers.main(TarTest)
