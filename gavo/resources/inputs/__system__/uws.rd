<resource schema="uws" resdir="__system">
	<meta name="description">Helpers for the support of 
	universial worker services.</meta>
	<!-- the uwsfields STREAM contains what's necessary for
	protocols.uws.BaseUWSJob; in particular, don't mess with the table
	attributes given at the top. -->

	<STREAM id="uwsfields">
		<onDisk>True</onDisk>
		<primary>jobId</primary>
		<forceUnique>True</forceUnique>
		<allProfiles>feed,trustedquery</allProfiles>
		<dupePolicy>overwrite</dupePolicy>
		<!-- the entire UWS shares a single directory for the job directories. -->
		<column name="jobId" type="text" 
			description="Internal id of the job.  At the same time, 
				uwsDir-relative name of the job directory."/>
		<column name="phase" type="text" 
			description="The state of the job.">
			<values>
				<option>PENDING</option>
				<option>QUEUED</option>
				<option>EXECUTING</option>
				<option>COMPLETED</option>
				<option>ERROR</option>
				<option>ABORTED</option>
				<option>UNKNOWN</option>
			</values>
		</column>
		<column name="executionDuration" type="integer"
			unit="s"
			description="Job time limit">
			<values nullLiteral="-1"/>
		</column>
		<column name="destructionTime" type="timestamp"
			description="Time at which the job, including ancillary 
			data, will be deleted"/>
		<column name="owner" type="text" 
			description="Submitter of the job, if verified"/>
		<column name="parameters" type="text" 
			description="Pickled representation of the parameters (except uploads)"/>
		<column name="runId" type="text" 
			description="User-chosen run Id"/>
		<column name="startTime" type="timestamp" 
			description="UTC job execution started"/>
		<column name="endTime" type="timestamp" 
			description="UTC job execution finished"/>
		<column name="error" type="text"
			description="some suitable representation an error that has
			occurred while executing the job (null means no error information
			has been logged)"/>
		<column name="creationTime" type="timestamp"
			description="UTC job was created"/>
	</STREAM>

	<!-- have an empty data so gavo imp does not complain -->
	<data id="empty"/>

	<data id="upgrade_0.6.3_0.7" auto="false">
		<!-- remove old uws tables; this needs a special script because
		the drop functionality was broken for system tables before 0.7 -->
		<sources items="0"/>
		<nullGrammar/>
		<make>
			<table onDisk="True" temporary="True" id="tmp"/>
			<script lang="AC_SQL" name="drop old UWS tables" type="newSource">
				drop table uws.jobs;
				drop table uws.uwsresults;
				delete from dc.tablemeta where tablename='uws.jobs';
				delete from dc.tablemeta where tablename='uws.uwsresults';
				delete from dc.columnmeta where tablename='uws.jobs';
				delete from dc.columnmeta where tablename='uws.uwsresults';
			</script>
		</make>
	</data>


	<table id="userjobs" onDisk="True" system="True">
		<meta name="description">The jobs table for user-defined UWS
		jobs. As the jobs can come from all kinds of services, this
		must encode the jobClass (as the id of the originating service).
		</meta>

		<FEED source="uwsfields"/>
		<column name="pid" type="integer" 
				description="A unix pid to kill to make the job stop">
			<values nullLiteral="-1"/>
		</column>
		<column name="jobClass" type="text"
			description="Key for the job class to use here.  This is,
				as an implementation detail, simply the cross-id of the service
				processing this."/>
	</table>

	<data id="enable_useruws" auto="False">
		<make table="userjobs"/>
	</data>

	<service id="joblist_wrapper">
		<!-- this is not an actual service but just defines the interface
		for the UWS 1.1 joblist -->
		<nullCore>
			<inputTable>
				<inputKey name="PHASE" type="text" multiplicity="single"
					description="Restrict result to jobs in this phase">
					<values>
						<option>PENDING</option>
						<option>QUEUED</option>
						<option>EXECUTING</option>
						<option>COMPLETED</option>
						<option>ERROR</option>
						<option>ABORTED</option>
						<option>UNKNOWN</option>
						<option>HELD</option>
						<option>SUSPENDED</option>
						<option>ARCHIVED</option>
					</values>
				</inputKey>
				<inputKey name="AFTER" type="timestamp" multiplicity="single"
					description="Restrict result to jobs created after this point in time"/>
				<inputKey name="LAST" type="integer" multiplicity="single"
					description="Restrict output to this many records, and choose the
						most recent ones"/>
			</inputTable>
		</nullCore>
	</service>

	<service id="jobresource_wrapper">
		<nullCore>
			<inputTable>
				<inputKey name="PHASE" type="text" multiplicity="single"
					description="Return immediately unless job is in this phase.">
					<values>
						<!-- we reject polling against PENDING, too, since it doesn't make
						much sense -->
						<option>QUEUED</option>
						<option>EXECUTING</option>
					</values>
				</inputKey>
				<inputKey name="WAIT" type="integer" multiplicity="single"
					description="Seconds to wait with an answer if no change occurred."/>
			</inputTable>
		</nullCore>
	</service>

</resource>
