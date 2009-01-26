<?xml version="1.0" encoding="utf-8"?>

<!-- definitions needed for the product mixin and the products delivery
machinery -->

<resource resdir="__system">
	<schema>public</schema>

	<!-- the following two will be inserted into all data elements
	that have tables implementing products -->
	<table id="products" primary="key" system="True" onDisk="True">
		<column name="key" type="text" tablehead="Product key"
			description="System-globally unique key identifying the product"
			verbLevel="1"/>
		<column name="owner" type="text" tablehead="Owner"
			verbLevel="21" description="Owner of the data as an interface group"/>
		<column name="embargo" type="date" tablehead="Embargo ends" 
			verbLevel="21" description=
			"Date on which the data becomes or became freely accessible"/>
		<column name="accessPath" type="text" tablehead="Path to access data" 
			required="True" verbLevel="5" 
			description="Inputs-relative filesystem path to the file"/>
		<column name="sourceTable" type="text" verbLevel="10"
			tablehead="Source Table"
			description="Name of table containing metadata" required="True"/>
		<column name="mime" type="text" verbLevel="20"
			tablehead="Type"
			description="MIME type of the file served"/>
		<primary>key</primary>
	</table>
	<rowmaker id="productsMaker">
 		<map dest="key" src="prodtblKey"/>
		<map dest="owner" src="prodtblOwner"/>
		<map dest="embargo">prodtblEmbargo</map>
		<map dest="accessPath" src="prodtblPath"/>
		<map dest="sourceTable" src="prodtblTable"/>
		<map dest="mime" src="prodtblMime"/>
	</rowmaker>

	<!-- materials for tables mixing in products -->
	<table id="productColumns">
		<column name="accref" ucd="VOX:Image_AccessReference"
			type="text" verbLevel="1" displayHint="type=product" 
			tablehead="Product" description="Access key for the data"/>
		<column name="owner" type="text"
			tablehead="Product owner" verbLevel="25"
			description="Data owner"/>
		<column name="embargo" type="date"
			tablehead="Embargo ends" unit="Y-M-D" verbLevel="25"
			description="Date the data will become/became public"/>
		<column name="accsize" ucd="VOX:Image_FileSize"
			tablehead="File size" description="Size of the data in bytes"
			type="integer" verbLevel="11" unit="byte"/>
		<!-- The following rule makes sure the product
		table entry is removed when a row is deleted.  There has to be
		a better way to do this, but referencing doesn't help here,
		since the reference would have to go from the product table
		to this one here, and there are may of those -->
		<script type="preIndexSQL" name="create product cleanup rule">
			CREATE OR REPLACE RULE cleanupProducts AS ON DELETE TO\
				\curtable DO ALSO\
				DELETE FROM products WHERE key=OLD.accref
		</script>
		<script type="afterDrop" name="clean product table">
			DELETE FROM products WHERE sourceTable='\curtable'
		</script>
	</table>

	<rowgen name="defineProduct" isGlobal="True">
		<doc>
			enters the values defined by the product interface into result.

			See the documentation on the product interface.
		</doc>
		<arg key="key" default="\inputRelativePath"/>
		<arg key="owner" default="None"/>
		<arg key="embargo" default="None"/>
		<arg key="path" default="None"/>
		<arg key="table" default="base.Undefined"/>
		<arg key="fsize" default="\inputSize"/>
		<arg key="mime" default="'image/fits'"/>
			newVars = {}
			if path is None:
				path = key
			row["prodtblKey"] = key
			row["prodtblOwner"] = owner
			row["prodtblEmbargo"] = embargo
			row["prodtblPath"] = path
			row["prodtblFsize"] = fsize
			row["prodtblTable"] = table
			row["prodtblMime"] = mime
			yield row
	</rowgen>

	<rowmaker id="prodcolUsertable">
		<!-- fragment for mapping the result of defineProduct into a user table -->
		<map dest="accref" src="prodtblKey"/>
		<map dest="owner" src="prodtblOwner"/>
		<map dest="embargo" src="prodtblEmbargo"/>
		<map dest="accsize" src="prodtblFsize"/>
	</rowmaker>

	<table id="pCoreInput" namePath="products">
		<meta name="description">Input table for the product core</meta>
		<column original="key"/>
	</table>

	<productCore id="core" queriedTable="products">
		<!-- core used for the product delivery service -->
		<inputDD>
			<rowmaker id="build_input">
				<map dest="key">key</map>
			</rowmaker>
			<make table="pCoreInput" rowmaker="build_input" role="parameters"/>
		</inputDD>
		<condDesc buildFrom="pCoreInput.key"/>

		<outputTable id="pCoreOutput">
			<column name="source" type="raw"
				tablehead="Access info" verbLevel="1"/>
		</outputTable>
	</productCore>

	<productCore id="forTar" original="core" limit="10000">
		<!-- core used by producttar; many matches are possible here;
		producttar uses an inputDD of its own here. -->
		<inputDD>
			<rowmaker id="build_forTar">
				<map dest="key">accref</map>
			</rowmaker>
			<make table="pCoreInput" role="primary"/>
		</inputDD>
	</productCore>

	<table id="parsedKeys">
		<meta name="description">Used internally by the product core.</meta>
		<column original="products.key"/>
		<column name="ra"/>
		<column name="dec"/>
		<column name="sra"/>
		<column name="sdec"/>
	</table>

	<service id="p" core="core" allowed="get, form">
		<meta name="description">The main product deliverer</meta>
	</service>
</resource>
