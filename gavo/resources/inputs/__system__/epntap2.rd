<resource schema="__system">
	<STREAM id="_minmax">
		<doc>
			Generates a pair of minimum/maximum column pairs.  You must
			fill out basename, baseucd, basedescr, unit.
		</doc>
		<column name="\basename\+_min" type="double precision"
			ucd="\baseucd;stat.min" unit="\unit"
			description="\basedescr, lower limit."
			utype="\baseutype\+_min">
			<property key="std">1</property>
		</column>
		<column name="\basename\+_max" type="double precision"
			ucd="\baseucd;stat.max" unit="\unit"
			description="\basedescr, upper limit"
			utype="\baseutype\+_max">
			<property key="std">1</property>
		</column>
	</STREAM>
	<STREAM id="_c_minmax">
		<doc>
			Generates a pair of minimum/maximum column pairs.  You must
			fill out basename, baseucd, basedescr, unit.
		</doc>
		<column name="\basename\+min" type="double precision"
			ucd="\baseucd;stat.min" unit="\unit"
			description="\basedescr, lower limit."
			utype="\baseutype\+min">
			<property key="std">1</property>
		</column>
		<column name="\basename\+max" type="double precision"
			ucd="\baseucd;stat.max" unit="\unit"
			description="\basedescr, upper limit"
			utype="\baseutype\+max">
			<property key="std">1</property>
		</column>
	</STREAM>

	<table id="optional_columns">
		<!-- to get this list (for optional columns mixin docs), run in vi:
			!/<.table grep "<column" | sed -e 's/.*name="\([^"]*\)".*/\1/'
		-->
		<column name="access_url"	type="text" 
			ucd="meta.ref.url;meta.file" utype="Obs.Access.Reference"
			description="URL of the data file, case sensitive. Can point 
			to a script." 
			displayHint="type=url">
			<property key="std">1</property>
		</column>

		<column name="access_format"	type="text"
			ucd="meta.code.mime" utype="Obs.Access.Format"
			description="File format type (RFC 6838 Media Type a.k.a MIME type)">
			<property key="std">1</property>
		</column>

		<column name="access_estsize"	type="integer"
			ucd="phys.size;meta.file" unit="kbyte"
			utype="Obs.Access.Size"
			description="Estimated file size in kbyte.">
			<property key="std">1</property>
			<values nullLiteral="-1"/>
		</column>

		<column name="access_md5" type="text"
			ucd="meta.checksum;meta.file" 
			description="MD5 Hash for the file">
			<property key="std">1</property>
		</column>

		<column name="thumbnail_url" type="text" 
			ucd="meta.ref.url;meta.file"
			description="URL of a thumbnail image with predefined size (png ~200 
			pix, for use in a client only)."
			displayHint="type=url">
			<property key="std">1</property>
		</column>

		<column name="file_name" type="text" 
			ucd="meta.id;meta.file"
			description="Name of the data file only, case sensitive."
			displayHint="type=url">
			<property key="std">1</property>
		</column>

		<column name="species" type="text" 
			ucd="meta.id;phys.atmol"
			description="Identifies a chemical species, case sensitive">
			<property key="std">1</property>
		</column>

		<column name="filter" type="text" 
			ucd="inst.filter.id"
			description="Identifies a filter in use (e.g. imaging)">
			<property key="std">1</property>
		</column>

		<column name="alt_target_name" type="text" 
			ucd="meta.id;src"
			description="Provides alternative target name if more 
			common (e.g. comets)">
			<property key="std">1</property>
		</column>

		<column name="target_region"	type="text" 
			ucd="meta.id;class" 
			description="Type of region of interest">
			<property key="std">1</property>
		</column>

		<column name="feature_name" type="text"
			ucd="meta.id;pos"
			description="Secondary name (can be standard name of region of
				interest).">
			<property key="std">1</property>
		</column>

		<column name="bib_reference"	type="text" 
			ucd="meta.bib" 
			description="Bibcode preferred if available (does that include link?), 
							doi, or other biblio id, URL">
			<property key="std">1</property>
		</column>

		<column name="publisher"	type="text" 
			ucd="meta.ref" 
			description="A short string identifying the entity running
				the data service used.">
			<property key="std">1</property>
		</column>

		<column name="spatial_coordinate_description" type="text"
			ucd="meta.code.class;pos.frame"
			description="ID of specific coordinate system and version.">
			<property key="std">1</property>
		</column>

		<column name="spatial_origin" type="text"
			ucd="meta.ref;pos.frame"
			description="Defines the frame origin.">
			<property key="std">1</property>
		</column>

		<column name="time_origin" type="text"
			ucd="meta.ref;time.scale"
			description="Defines wehere the time is measured (e.g., ground vs.
				spacecraft).">
			<property key="std">1</property>
		</column>

		<column name="time_scale"	type="text" 
			ucd="time.scale" 
			description="Always UTC in data services (may be relaxed in computational 
							services such as ephemeris) - from enumerated list">
			<property key="std">1</property>
		</column>
	</table>

	<mixinDef id="table-2_0">
		<doc><![CDATA[
			This mixin defines a table suitable for publication via the
			EPN-TAP protocol.

			According to the standard definition, tables mixing this in
			should be called ``epn_core``.  The mixin already arranges
			for the table to be accessible by ADQL and be on disk.

			This also causes the product table to be populated.
			This means that grammars feeding such tables need a 
			`//products#define`_ row filter.  At the very least, you need to say::

				<rowfilter procDef="//products#define">
					<bind name="table">"\schema.epn_core"</bind>
				</rowfilter>

			If you absolutely cannot use //products#define, you will hve 
			to manually provide the prodtblFsize (file size in *bytes*),
			prodtblAccref (product URL), and prodtblPreview (thumbnail image
			or None) keys in what's coming from your grammar.

			Use the `//epntap2#populate-2_0`_ apply in rowmakers
			feeding tables mixing this in.
		]]></doc>

		<mixinPar key="spatial_frame_type" description="Flavour of the 
			coordinate system.  Since this determines the units of the
			coordinates columns, this must be set globally for the
			entire dataset. Values defined by EPN-TAP and understood
			by this mixin include celestial, body, cartesian, cylindrical, 
			spherical, healpix." />
		<mixinPar key="optional_columns" description="Space-separated list
			of names of optional columns to include.  Column names available
			include 
			access_url access_format access_estsize access_md5 thumbnail_url
			file_name species filter alt_target_name target_region feature_name
			bib_reference publisher spatial_coordinate_description spatial_origin
			time_origin time_scale">__EMPTY__</mixinPar>

		<processEarly>
			<setup>
				<code>
					from gavo import base
					from gavo import rscdef
					from gavo.protocols import sdm
					
					META_BY_FRAME_TYPE = {
						# (units, ucds, descriptions)
						"celestial": (
							("deg", "deg", "m"),
							("pos.eq.ra", "pos.eq.dec", "phys.distance"),
							(	"Right Ascension (ICRS)",
								"Declination (ICRS)",
								"Distance from coordiate origin")),

						"body": (
							("deg", "deg", "m"),
							("pos.bodyrc.long", "pos.bodyrc.lat", "pos.bodyrc.alt"),
							(	"Longitude on body",
								"Latitude on body",
								"Height over defined null")),

						"cartesian": (
							("m", "m", "m"),
							("pos.cartesian.x", "pos.cartesian.y", "pos.cartesian.z"),
							(	"Cartesian coordinate in x direction",
								"Cartesian coordinate in y direction",
								"Cartesian coordinate in z direction")),

						"spherical": (
							("m", "deg", "deg"),
							("phys.distance", "pos.az.zd", "pos.az.azi"),
							(	"Radial distance in spherical coordinates",
								"Polar angle or colatitude in spherical coordinates",
								"Azimuth in spherical coordinates")),

						"cylindrical": (
							("m", "deg", "m"),
							("pos", "pos.az.azi", "pos"),
							(	"Radial distance in cylindrical coordinates",
								"Azimuth in cylindrical coordinates",
								"Height in cylindrical coordinates")),
						}

					def setFrameMeta(tableDef, spatialFrameType):
						if spatialFrameType not in META_BY_FRAME_TYPE:
							raise base.StructureError("Unknown EPN-TAP frame type: %s."%
									spatialFrameType,
								hint="Known frame types are: %s"%(
									", ".join(META_BY_FRAME_TYPE)))

						units, ucds, descriptions = META_BY_FRAME_TYPE[spatialFrameType]
						for cooIndex in range(3):
							prefix = "c%d"%(cooIndex+1)
							for postfix in ["min", "max", 
									"_resol_min", "_resol_max"]:
								col = tableDef.getColumnByName(prefix+postfix)
								col.unit = col.unit.replace(
									"__replace_framed__", units[cooIndex])
								col.ucd = col.ucd.replace(
									"__replace_framed__", ucds[cooIndex])
								col.description = col.description.replace(
									"__replace_framed__", descriptions[cooIndex])

					def addOptionalColumns(tableDef, columnNames):
						sourceTable = base.resolveCrossId("//epntap2#optional_columns")
						for columnName in columnNames.split():
							tableDef.columns.append(
								sourceTable.getColumnByName(columnName))
				</code>
			</setup>
			<code>
				setFrameMeta(substrate, mixinPars["spatial_frame_type"])
				substrate.setProperty("spatial_frame_type", 
					mixinPars["spatial_frame_type"])
				if mixinPars["optional_columns"]:
					addOptionalColumns(substrate, mixinPars["optional_columns"])
			</code>
		</processEarly>

		<events>
			<adql>True</adql>
			<onDisk>True</onDisk>
			<meta name="utype">ivo.//vopdc.obspm/std/epncore#schema-2.0</meta>
			<meta name="info" infoName="SERVICE_PROTOCOL" 
				infoValue="2.0">EPN-TAP</meta>
			<column name="granule_uid" type="text" required="True"
				ucd="meta.id"
				description="Internal table row index 
					Unique ID in data service, also in v2. Can be alphanumeric.">
				<property key="std">1</property>
			</column>
			<column name="granule_gid" type="text" required="True"
				ucd="meta.id"
				description="Common to granules of same type (e.g. same map projection, 
					or geometry data products). Can be alphanumeric.">
				<property key="std">1</property>
			</column>
			<column name="obs_id" type="text" required="True"
				ucd="meta.id"
				description="Associates granules derived from the same data (e.g. 
					various representations/processing levels). 
					Can be alphanumeric, may be the ID of original observation.">
				<property key="std">1</property>
			</column>
			<column name="dataproduct_type"	type="text" 
				ucd="meta.code.class" utype="Epn.dataProductType"
				description="The high-level organization of the data product,
					from enumerated list (e.g., 'im' for image, sp for spectrum)"
				note="et_prod">
				<property key="std">1</property>
				<values>
					<option>im</option>
					<option>ma</option>
					<option>sp</option>
					<option>ds</option>
					<option>sc</option>
					<option>pr</option>
					<option>vo</option>
					<option>mo</option>
					<option>cu</option>
					<option>ts</option>
					<option>ca</option>
					<option>ci</option>
				</values>
			</column>
			<column name="target_name"	type="text" 
				ucd="meta.id;src" utype="Epn.TargetName"
				description="Standard IAU name of target (from a list related 
					to target class), case sensitive">
				<property key="std">1</property>
			</column>
			<column name="target_class"	type="text" 
				ucd="meta.code.class;src"  utype="Epn.TargetClass"
				description="Type of target, from enumerated list">
				<property key="std">1</property>
				<values>
					<option>asteroid</option>
					<option>dwarf_planet</option>
					<option>planet</option>
					<option>satellite</option>
					<option>comet</option>
					<option>exoplanet</option>
					<option>interplanetary_medium</option>
					<option>ring</option>
					<option>sample</option>
					<option>sky</option>
					<option>spacecraft</option>
					<option>spacejunk</option>
					<option>star</option>
				</values>
			</column>

			<column name="time_min"	
				ucd="time.start" unit="d"
				type="double precision"
				description="Acquisition start time (in JD)"/>
			<column name="time_max"	
				ucd="time.end" unit="d"
				type="double precision"
				description="Acquisition stop time (in JD)"/>

			<FEED source="_minmax"
				basename="time_sampling_step"
				baseucd="time.interval" unit="s"
				baseutype="Epn.Time.Time_sampling_step"
				basedescr="Sampling time for measurements of dynamical
					phenomena"/>
			<FEED source="_minmax"
				basename="time_exp"
				baseucd="time.duration;obs.exposure" unit="s"
				baseutype="Epn.Time.Time_exp"
				basedescr="Integration time of the measurement"/>
			<FEED source="_minmax"
				basename="spectral_range"
				baseucd="em.freq" unit="Hz"
				baseutype="Epn.Spectral.Spectral_range"
				basedescr="Spectral range (frequency)"/>

			<FEED source="_minmax"
				basename="spectral_sampling_step"
				baseucd="em.freq.step" unit="Hz"
				baseutype="Epn.Spectral.Spectral_sampling_step"
				basedescr="spectral sampling step"/>
			<FEED source="_minmax"
				basename="spectral_resolution"
				baseucd="spect.resolution" unit="Hz"
				baseutype="Epn.Spectral.Spectral_resolution"
				basedescr="Sectral resolution"/>

			<FEED source="_c_minmax"
				basename="c1"
				baseucd="__replace_framed__" unit="__replace_framed__"
				baseutype="Epn.Spatial.Spatial_range.c1"
				basedescr="__replace_framed__"/>
			<FEED source="_c_minmax"
				basename="c2"
				baseucd="__replace_framed__" unit="__replace_framed__"
				baseutype="Epn.Spatial.Spatial_range.c2"
				basedescr="__replace_framed__"/>
			<FEED source="_c_minmax"
				basename="c3"
				baseucd="__replace_framed__" unit="__replace_framed__"
				baseutype="Epn.Spatial.Spatial_range.c3"
				basedescr="__replace_framed__"/>

			<column name="s_region"	type="spoly" 
				ucd="phys.outline;obs.field" unit="" 
				description="ObsCore-like footprint, valid for celestial, 
					spherical, or body-fixed frames.">
				<property key="std">1</property>
			</column>
			<FEED source="_minmax"
				basename="c1_resol"
				baseucd="pos.resolution" unit="__replace_framed__"
				baseutype="Epn.Spatial.Spatial_resolution.c1_resol"
				basedescr="Resolution in the first coordinate"/>
			<FEED source="_minmax"
				basename="c2_resol"
				baseucd="pos.resolution" unit="__replace_framed__"
				baseutype="Epn.Spatial.Spatial_resolution.c2_resol"
				basedescr="Resolution in the second coordinate"/>
			<FEED source="_minmax"
				basename="c3_resol"
				baseucd="pos.resolution" unit="__replace_framed__"
				baseutype="Epn.Spatial.Spatial_resolution.c3_resol"
				basedescr="Resolution in the third coordinate"/>

			<column name="spatial_frame_type"	type="text" 
				ucd="meta.code.class;pos.frame"
				description="Flavor of coordinate system, 
					defines the nature of coordinates. From enumerated list">
				<property key="std">1</property>
				<values default="\spatial_frame_type">
					<option>celestial</option>
					<option>body</option>
					<option>cartesian</option>
					<option>cylindrical</option>
					<option>spherical</option>
					<option>healpix</option>
				</values>
			</column>
			<FEED source="_minmax"
				basename="incidence"
				baseucd="pos.posAng" unit="deg"
				baseutype="Epn.View_angle.Incidence_angle"
				basedescr="Incidence angle (solar zenithal angle) during
					data acquisition"/>
			<FEED source="_minmax"
				basename="emergence"
				baseucd="pos.posAng" unit="deg"
				baseutype="Epn.View_angle.Emergence_angle"
				basedescr="Emergence angle during data acquisition"/>
			<FEED source="_minmax"
				basename="phase"
				baseucd="pos.phaseAng" unit="deg"
				baseutype="Epn.View_angle.Phase_angle"
				basedescr="Phase angle during data acquisition"/>
			<column name="instrument_host_name"	type="text" 
				ucd="meta.id;instr.obsty"
				utype="Provenance.ObsConfig.Facility.name"
				description="Standard name of the observatory or spacecraft.">
				<property key="std">1</property>
			</column>
			<column name="instrument_name"	type="text" 
				ucd="meta.id;instr" 
				utype="Provenance.ObsConfig.Instrument.name"
				description="Standard name of instrument">
				<property key="std">1</property>
			</column>
			<column name="measurement_type"	type="text" 
				ucd="meta.ucd" 
				utype="Epn.Measurement_type"
				description="UCD(s) defining the data, with multiple entries
					separated by hash (#) characters.">
				<property key="std">1</property>
			</column>

			<column name="processing_level" type="integer" required="True"
				ucd="meta.code;obs.calib" 
				description="CODMAC calibration level; see the et_cal note
					http://dc.g-vo.org/tableinfo/titan.epn_core#note-et_cal for
					what values are defined here."
				note="et_cal">
				<property key="std">1</property>
			</column>

			<column name="creation_date"	type="timestamp" 
				ucd="time.creation" 	unit=""
				description="Date of first entry of this granule">
				<property key="std">1</property>
			</column>
			<column name="modification_date"	type="timestamp" 
				ucd="time.update" 		unit=""
				description="Date of last modification (used to handle mirroring)">
				<property key="std">1</property>
			</column>
			<column name="release_date" 	type="timestamp" 
				ucd="time.release" 	unit=""
				description="Start of public access period">
				<property key="std">1</property>
			</column>

			<column name="service_title"	type="text" 
				ucd="meta.title" 
				description="Title of resource (an acronym really, 
								will be used to handle multiservice results)">
				<property key="std">1</property>
			</column>


			<meta name="note" tag="et_prod">
				The following values are defined for this field:

				im -- image
					associated scalar fields with two spatial axes, e.g., images with
					multiple color planes like from multichannel or filter cameras. 
					Preview images (e.g. map with axis and caption) also belong here. 
					Conversely, all vectorial 2D fields are described as catalogue 
					(see below).
				ma -- map
					scalar field/rasters with two spatial axes covering a large 
					area and projected either on the sky or on a planetary body, 
					associated to a Projection parameter (with a short enumerated 
					list of possible values).  This is mostly intended to identify 
					complete coverages that can be used as reference basemaps
				sp-- spectrum
					measurements organized primarily along a spectral axis, e.g., 
					radiance spectra. This includes spectral aggregates (series 
					of related spectra with non-connected spectral ranges, e.g., 
					from several channels of the same instrument 
				ds -- dynamic_spectrum
					consecutive spectral measurements through time, organized 
					as a time series. This typically implies successive spectra of 
					the same target or field of view.
				sc -- spectral_cube
					sets of spectral measurements with 1 or 2 D spatial coverage, e.g.,
					imaging spectroscopy. The choice between Image and spectral_cube is
					related to the characteristics of the instrument (which dimension 
					is most resolved and which dimensions are acquired simultaneously). 
					The choice between dynamic_spectrum and spectral_cube is related 
					to the uniformity of the field of view.
				pr -- profile
					scalar or vectorial measurements along 1 spatial dimension, e.g.,
					atmospheric profiles, atmospheric paths, sub-surface profiles…
				vo -- volume
					other measurements with 3 spatial dimensions, e.g., internal or
					atmospheric structures, including shells/shape models (3D surfaces).
				mo -- movie
					sets of chronological 2 D spatial measurements.
				cu -- cube
					multidimensional data with 3 or more axes, e.g., all that is not
					described by other 3 D data types such as spectral cubes or volume.
					This is mostly intended to accommodate unusual data with multiple 
					dimensions.
				ts -- time_series
					measurements organized primarily as a function of time (with 
					exception of dynamical spectra and movies, i.e. usually a scalar 
					quantity). Typical examples of time series include space-borne 
					dust detector measurements, daily or seasonal curves measured at 
					a given location (e.g., a lander), and light curves.
				ca -- catalog 
					applies to a single granule providing a list of events, a catalog 
					of object parameters, a list of features… Spatial vectors 
					(e.g., vector information from a GIS, spatial footprints…) belong 
					here. This is relevant, e. g., for collections of vectorial elements 
					(e.g., crater lists or ROI definitions) which can be handled directly 
					in a specialized environment such as a GIS. This includes maps of 
					vectors, e.g., wind maps.
				ci -- catalogue_item
					applies when the service itself provides a catalogue, with entries 
					described as individual granules. The service can be, e.g., a list
					of asteroid properties or spectral lines. Catalogue_item can be 
					limited to scalar quantities (including strings), and possibly to 
					a single element. This organization allows the user to search inside 
					the catalogue from the TAP query interface.
			</meta>

			<meta name="note" tag="et_cal">
				CODMAC levels are:

				1 -- raw

				2 -- edited

				3 -- calibrated

				4 -- resampled

				5 -- derived

				6 -- ancillary
			</meta>
		</events>

	</mixinDef>


	<mixinDef id="localfile-2_0">
		<doc>
			Use this mixin if your epntap table is filled with local products
			(i.e., sources matches files on your hard disk that DaCHS should
			hand out itself).  This will arrange for your products to be
			entered into the products table, and it will automatically
			compute file size, etc.

			This wants a `//products#define`_ rowfilter in your grammar
			and a `//epntap2#populate-localfile-2_0`_ apply in your rowmaker.
		</doc>
		<events>
			<index columns="accref"/>
			<column original="//products#products.accref"/>
		</events>
		<FEED source="//products#hackProductsData"/>
	</mixinDef>


	<procDef type="apply" id="populate-2_0">
		<doc>
			Sets metadata for an epntap data set, including its products definition.

			The values are left in vars, so you need to do manual copying,
			e.g., using idmaps="*".
		</doc>

		<setup>
			<par key="index_" description="A numeric reference for the
				item.  By default, this is just the row number.  As this will
				(usually) change when new data is added, you should override it
				with some unique integer number specific to the data product 
				when there is such a thing." late="True">\rowsMade</par>
			<par key="target_name" description="Name of the target object,
				preferably according to the official IAU nomenclature.
				As appropriate, take these from the exoplanet encyclopedia
				http://exoplanet.eu, the meteor catalog at 
				http://www.lpi.usra.edu/meteor/, the catalog of stardust
				samples at http://curator.jsc.nasa.gov/stardust/catalog/" 
				late="True"/>
			<par key="time_scale" description="Time scale used for the
				various times, as given by IVOA's STC data model.  Choose
				from TT, TDB, TOG, TOB, TAI, UTC, GPS, UNKNOWN" 
				late="True">"UNKNOWN"</par>
			<par key="instrument_host_name" description="Name of the observatory
				or spacecraft that the observation originated from; for
				ground-based data, use IAU observatory codes, 
				http://www.minorplanetcenter.net/iau/lists/ObsCodesF.html,
				for space-borne instruments use
				http://nssdc.gsfc.nasa.gov/nmc/" late="True"/>
			<par key="instrument_name" description="Service providers are
				invited to include multiple values for instrumentname, e.g.,
				complete name + usual acronym. This will allow queries on either
				'VISIBLE AND INFRARED THERMAL IMAGING SPECTROMETER' or VIRTIS to
				produce the same reply." late="True">None</par>
			<par key="target_region" description="This is a complement to the
				target name to identify a substructure of the target that was
				being observed (e.g., Atmosphere, Surface).  Take terms from
				them Spase dictionary at http://www.spase-group.org or the
				IVOA thesaurus." late="True">None</par>
			<par key="target_class" description="The type of the target;
				choose from asteroid, dwarf_planet, planet, satellite, comet, 
				exoplanet, interplanetary_medium, ring, sample, sky, spacecraft, 
				spacejunk, star" late="True">"UNKNOWN"</par>

			<!-- Note: only late parameters allowed in here.  Also, don't
			define anything here unless you have to; we pick up the
			columns from the mixin's stream automatically. -->

			<!-- if you add more manual parameters, make sure you list them
			in overridden below -->

			<LOOP>
				<codeItems>
					# overridden is a set of column names for which the parameters
					# are manually defined above or which are set in some other way.
					overridden = set(["index_",
						"target_name", "time_scale",
						"instrument_host_name", "instrument_name",
						"target_region", "target_class",
						"spatial_frame_type"])

					mixin = context.getById("table-2_0")
					colDict = {}
					for type, name, content, pos in mixin.events.events_:
						if type=="value":
							colDict[name] = content
						elif type=="end":
							if name=="column":
								if colDict.get("name") not in overridden:
									if colDict.get("required", False):
										colDict["default"] = ''
									else:
										colDict["default"] = 'None'
									yield colDict
								colDict = {}
				</codeItems>
				<events>
					<par key="\name" description="\description"
						late="True">\default</par>
				</events>
			</LOOP>
			<code>
				# find myself to get the list of my parameters
				for app in parent.apps:
					if app.procDef and app.procDef.id=='populate-2_0':
						break
				else:
					raise base.Error("Internal: epntap#populate-2_0 cannot find itself")

				EPNTAP_KEYS = [p.key for p in app.procDef.setups[0].pars]
				del app
				del p
			</code>
		</setup>
		
		<code>
			l = locals()
			for key in EPNTAP_KEYS:
				vars[key] = l[key]
			vars["spatial_frame_type"] = targetTable.tableDef.getProperty(
				"spatial_frame_type", None)
		</code>
	</procDef>

	<procDef id="populate-localfile-2_0" type="apply">
		<doc>
			Use this apply when you use `the //epntap2#localfile-2_0 mixin`_.
			This will only (properly) work when you use a `//products#define`_
			rowfilter; if you have that, this will work without further 
			configuration.
		</doc>
		<code>			
			# map things from products#define
			vars["access_estsize"] = vars["prodtblFsize"]/1024
			vars["access_url"] = makeProductLink(vars["prodtblAccref"])
			if @prodtblPreview:
				vars["thumbnail"] = @prodtblPreview
			vars["accref"] = vars["prodtblAccref"]
		</code>
	</procDef>
</resource>
