<!-- a collection of various helpers for building dataling services. -->

<resource resdir="__system" schema="dc">

	<table id="dlresponse">
		<meta name="description">Data links for data sets.</meta>
		<column name="ID" type="text"
			ucd="meta.id;meta.main"
			tablehead="PubDID"
			description="Publisher data set id; this is an identifier for
				the dataset in question and can be used to retrieve the data."
			verbLevel="1"/>
		<column name="access_url" type="text"
			ucd="meta.ref.url"
			tablehead="URL"
			description="URL to retrieve the data or access the service."
			verbLevel="1" displayHint="type=url"/>
		<column name="service_def" type="text"
			ucd="meta.code"
			tablehead="Svc. Type"
			description="Identifier for the type of service if accessURL refers
				to a service."
			verbLevel="1"/>
		<column name="error_message" type="text"
			ucd="meta.code.error"
			tablehead="Why not?"
			description="If accessURL is empty, this column gives the reason why."
			verbLevel="20"/>
		<column name="description" type="text"
			ucd="meta.note"
			tablehead="Description"
			description="More information on this link"
			verbLevel="1"/>
		<column name="semantics" type="text"
			ucd="meta.code"
			tablehead="What?"
			description="What kind of data is linked here?  Standard identifiers
				here include science, calibration, preview, info, auxiliary" 
				verbLevel="1"/>
		<column name="content_type" type="text"
			ucd="meta.code.mime"
			tablehead="MIME"
			description="MIME type for the data returned."
			verbLevel="1"/>
		<column name="content_length" type="bigint"
			ucd="phys.size;meta.file" unit="byte"
			tablehead="Size"
			description="Size of the resource at access_url"
			verbLevel="1">
			<values nullLiteral="-1"/>
		</column>
	</table>

	<data id="make_response">
		<!-- this data build a datalink response table out of LinkDefs.
		The input parameters for the computational part are built in
		within datalink.getDatalinkDescriptionResource. -->
		<embeddedGrammar>
			<iterator>
				<code>
					for linkDef in self.sourceToken:
						yield linkDef.asDict()
				</code>
			</iterator>
		</embeddedGrammar>
		
		<make table="dlresponse"/>
	</data>

	<!-- ************************************************ async support -->

	<table id="datalinkjobs" onDisk="True" system="True">
		<meta name="description">A table managing datalink jobs submitted
			asynchronously (the dlasync renderer)</meta>

		<FEED source="//uws#uwsfields"/>
		<column name="pid" type="integer" 
				description="A unix pid to kill to make the job stop">
			<values nullLiteral="-1"/>
		</column>
	</table>

	<data id="import">
		<make table="datalinkjobs"/>
	</data>

</resource>
