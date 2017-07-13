<!-- a resource descriptor containing services "running" external applets
or otherwise mainly spitting out templates with little manipulation.
-->

<resource resdir="__tests" schema="dc">
	<service id="specview" allowed="fixed">
		<meta name="title">Specview Applet Runner</meta>
		<nullCore/>
		<template key="fixed">//specview.html</template>
	</service>

	<service id="voplot" allowed="fixed">
		<meta name="title">VOPlot Applet Runner</meta>
		<nullCore/>
		<template key="fixed">//voplot.html</template>
	</service>

	<service id="genrd" allowed="fixed">	
		<meta name="title">RD bootstrapper</meta>
		<meta name="description" format="plain">
			This is a javascript-based facility for
			bootstrapping RDs that lets you enter the common parts of an RD
			in a HTML form interface.

			Note that this software cannot read back RDs; the recommended workflow
			is to develop the RD on by editing the XML.
		</meta>
		<nullCore/>
		<template key="fixed">//genrd.html</template>
	</service>
</resource>
