<resource schema="test">
	<regSuite>
		<regTest title="Failing Test" id="failtest">
			<url testParam="10%w/o tax">foo</url>
			<code>
				self.assertHasStrings("Wittgenstein")
			</code>
		</regTest>
		<regTest title="Succeeding Test">
			<code>
				assert True
			</code>
		</regTest>
		<regTest title="failing XSD Test" id="xsdfail">
			<url testParam="10%w/o tax">foo</url>
			<code>
				self.assertValidatesXSD()
			</code>
		</regTest>
	</regSuite>
	
	<regSuite title="URL tests" id="urltests">
		<regTest title="a" id="atest">
			<url testParam="10%w/o tax">foo</url>
			<code>
				self.assertHasStrings("Kant", "Hume")
			</code>
		</regTest>
		<regTest title="b" url="/bar">
			<code>
				self.assertValidatesXSD()
			</code>
		</regTest>
		<regTest title="c"><url httpMethod="POST">
			<gobba>&amp;?</gobba>ivo://ivoa.net/std/quack</url>
			<code>
				self.assertHTTPStatus(200)
			</code>
		</regTest>
		<regTest title="d"><url>nork?urk=zoo<oo>1</oo><oo>2</oo></url>
		</regTest>
	</regSuite>
</resource>
