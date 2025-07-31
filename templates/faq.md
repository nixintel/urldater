### Frequently Asked Questions


### How does the analysis work?
The tool uses a combination of techniques:
- RDAP queries for domain registration information, powered by [OpenRDAP](https://openrdap.org). 
- Certificate Transparency logs (via [crt.sh](https://crt.sh)) for SSL certificate history 
- HTTP header analysis for media file timestamps 

You can choose to run all analyses or focus on specific types using the radio buttons.

### Is this tool active or passive?
The tool uses both active and passive techniques:  

- **Passive:** RDAP queries and SSL certificate history lookups are passive and do not interact directly with the target site. RDAP queries will query the relevant RDAP server for that TLD. SSL certificate history is obtained from crt.sh. There is no interaction with the target website.  

- **Active:** Last-Modified header information requires an active connection to the target website. The tool does this by creating a headless browser session, connecting to the URL, and parsing the value of any Last-Modified headers in the response. 

### What are the limitations?
- RDAP data may not be available for all TLDs. Although RDAP has superseded WHOIS, not all TLDs have RDAP servers or provide full registration date information. 
- Some websites may block automated requests with captchas etc. This tool is respectful of captchas and paywalls and does not attempt to bypass them.
- Not all webservers choose to use Last-Modified headers. In this case the technique will not work and you will not see any results.
- Certificate history depends on public CT logs. These have generally been available since 2013, but sites older than this may have been issued with certificates prior to this that do not appear in public CT logs.

### Which TLDs support RDAP?

The vast majority of TLDs support RDAP, but there are a few outliers that do not and so will not return search results. For an up to date list of supported TLDs visit [rdap.org](https://deployment.rdap.org).

### How can I interpret the results?
The timeline view helps visualize the chronological relationship between:  

- When the domain was registered  

- When SSL certificates were first issued   

- When image files were last modified on the target webserver  

- Use mouse scroll to zoom in and out on the timeline. 

This can help establish how long a website has been active and identify recent changes. My original use case for this tool was to obtain reliable information for sites used for phishing, fraud, disinformation and other deceptive purposes. The tool provides timestamp information from reliable sources and helps to age a website or article much more accurately, regardless of any impersonation or deception by the target website.

### How can I save my results?

All results from your queries can be exported as CSV files.

### Why don't I see any data for the Last-Modified headers from the URL that I queried?
Not all websites use Last-Modified headers, so this technique will not work for them.

### Can I get Last-Modified header information for a site that requires authentication?

Probably not. The tool cannot bypass authentication requirements or log in to sites on your behalf.

### Is Last-Modified header information the same as file metadata/EXIF?
No. This tool does not collect image metadata information. Last-Modified header timestamps are based on when the origin webserver believes that particular content was modified on the server. Neither the origin server nor this tool examine the file metadata. To do that you need to download the files directly and analyse them with Exiftool or similar.

### I don't get any results from the domain registration query.
Most TLDs support RDAP and will provide registration date and time results. However not all TLDs (such as .de or .us) currently do so at time of writing. 

Some RDAP servers may also choose to rate limit or block requests.

If a domain has expired and no longer has a current RDAP record then it is likely no data will be returned. The tool does not query historic registration databases, only live ones.

### Why not use WHOIS?
WHOIS was deprecated in favour of RDAP in January 2025. WHOIS records are provided in an unstructured, non-standardised text format and are extremely frustrating to work with programatically. If you are really struggling for RDAP results, try [Big Domain Data](https://bigdomaindata.com) for WHOIS records.

### Why use SSL certificates?
SSL certificates are a highly reliable source of open data. Since about 2013 every SSL certificate ever issued has been publicly logged via Certificate Transparency (CT) logs. Sites that do not have SSL certificates are not trusted by browsers and are de-ranked by search engines, so even deceptive or malicious websites still need to obtain an SSL certificate. This tool identifies the first CT log entry for the target domain, and so provides a  reliable datapoint about when the site first became active.

### Why does it take so long to get data?
The SSL certificate data is obtained via [crt.sh](https://crt.sh). The site is sometimes slow or unavailable and this is reflected in the analysis time. If crt.sh is down or taking an excessively long time to return data then URL Dater will abandon the query and notify you in the browser.

If you'd rather not get SSL data you can run the domain registration and Last-Modified header modules separately.

### Why not use article publication timestamps?
It is [very easy](https://www.admincolumns.com/change-date-on-wordpress-post/) to retrospectively change or alter publication timestamps on website content after an article has been created. While the majority of sites do not do this, some deceptive sites manually alter publication timestamps to make websites appear older than they really are. 

By contrast Last-Modified headers are derived from the origin server's own time settings. While it is theoretically possible to try and modify the server clock, making significant changes to a server's time will cause much of its functionality to break. 

It is much more difficult to falsify a Last-Modified header than it is to amend an article publication date in WordPress for example.

### The results show that the first SSL certificate was obtained before the domain was even registered - how is this even possible?
Some RDAP results do not take breaks in ownership into account when determining a domain's first registration date. 

For example: a domain is first registered on 1st Jan 2018 and obtains an SSL certificate on the same date. On 31st December 2018 the owner decides not to renew the domain registration and the domain is put up for deletion and the SSL certificate eventually expires.  


On 1st Jan 2025 a new owner purchases the domain. An RDAP server with no knowledge of the inital registration in 2018 and will report the 2025 registration as the first registration date, but the SSL module will still (correctly) report that the first certificate was issued in 2018.

This will cause the results to show that the certificate was obtained before the domain was ever registered, which looks like it should be impossible.

This is a quirk of some RDAP records when there have been breaks in domain ownership. If in doubt I recommend consulting historic registration repositories like [Whoxy.com](https://whoxy.com) or [BigDomainData.com](https://bigdomaindata.com) to validate the first registration date.

### Can I host this myself?

Yes. The code to self-host this utility is open source and can be cloned from the [GitHub repository](https://github.com/nixintel/urldater). Instructions for set up are in the repo. The license requirements mean you may **NOT** use the code as part of any commercial software.

### What if there is a bug?

Report any issues via the [GitHub repository](https://github.com/nixintel/urldater). You must submit

### What other useful things can I use SSL certificates for?

If you are an investigator or researcher and want to learn more about other uses for SSL Certificates in OSINT then checkout [this video](https://www.youtube.com/watch?v=MM9gKmpBOVs) of my talk at the 2025 SANS OSINT Summit.

### What information do you collect about my queries?

URL Dater logs the IP address you connect from, the user agent, and the URL that you query. The data is retained for a short period for debugging and to prevent abuse. It is not further processed or transferred to third parties. 

If you're concerned about privacy you can download and host URL Dater yourself via [GitHub](https://github.com/nixintel/urldater).