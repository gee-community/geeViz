//From https://developers.google.com/analytics/devguides/collection/analyticsjs-->
(function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
(i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
})(window,document,'script','https://www.google-analytics.com/analytics.js','ga');

var analyticsObj = {'LCMS':'UA-188090968-1',
					'LT': 'UA-188090968-1',
					'lcms-base-learner':'UA-188090968-1',
					'LCMS-pilot':'UA-188090968-1',
					'FHP':'UA-188090968-1',
					'MTBS':'UA-188090968-2',
					'geeViz':'UA-188090968-3',
					'Ancillary':'UA-188090968-4',
					'STORM':'UA-188090968-5',
					'dev-viewer':'UA-188090968-6'}
if(window.document.documentMode){alert('This website will not work with Microsoft Internet Explorer. Please switch to a browser such as Chrome, Firefox, Edge, Safari, etc')}

if(window.location.search.indexOf('analytics=dev') !== -1){
	console.log('Using dev analytics')
	ga('create', analyticsObj['dev-viewer'], 'auto');
}else{
	try{
		console.log('Using analytics for: '+mode)
		ga('create', analyticsObj[mode], 'auto');
		if(mode !== 'LCMS'){
			ga('send', 'event','load', mode, mode);
		}
		
	}catch(err){
		console.log('Using default analytics')
		console.log(err)
		ga('create', 'UA-188090968-1', 'auto');
	}	
};

ga('send', 'pageview');
