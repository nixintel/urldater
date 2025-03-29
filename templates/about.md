# About URL Dater

## Frequently Asked Questions

### What is URL Dater?
URL Dater is a utility that helps investigate websites by providing reliable sources of information to help date website content accurately, verify the age of a website and its content, and discover editorial changes.  

It does this by gathering information about the domain's registration date, SSL certificate history, and the Last-Modified header timestamp of images embedded in the websites. It combines multiple analysis techniques to provide a comprehensive view of a website's history and content.

It is possible to run each module individually or all three at once.

### What information can I get from this tool?
- **Domain Information:** Registration dates and updates from [RDAP records](https://www.icann.org/rdap). RDAP (Registration Data Access Protocol) is the replacement for WHOIS. URL Dater uses RDAP to determine when a domain was first registered, and when the domain registration was last updated.
- **SSL Certificates:** This module checks Certificate Transparency log data from [crt.sh](https://crt.sh) to find the very first time that an SSL certificate was issued for a domain. CT log data is accurate as far back as 2013, so for sites that are older than this it will show the first SSL certificate available from public CT logs.
- **Media Dates:** Many webservers use the [Last-Modified header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Last-Modified) property to avoid unnecessary loading of content. This provides an accurate indicator as to when a specific image was added to a webserver, so we can leverage this data point accurately identify when a particular piece of content.
- **Timeline View:** Visual representation of all dates in chronological order on a timeline.

### How does the analysis work?
The tool uses a combination of techniques:
- RDAP queries for domain registration information 
- Certificate Transparency logs (via [crt.sh](https://crt.sh)) for SSL certificate history 
- HTTP header analysis for media file timestamps 

You can choose to run all analyses or focus on specific types using the radio buttons.

### Is this tool active or passive?
The tool uses both active and passive techniques:  

- **Passive:** RDAP queries and SSL certificate history lookups are passive. RDAP queries will query the relevant RDAP server for that TLD. SSL certificate history is obtained from crt.sh. There is no interaction with the target website.  

- **Active:** Last-Modified header information requires an active connection to the target website. The tool does this by creating a headless browser session, connecting to the URL, and parsing the value of any Last-Modified headers in theresponse. The tool separates the Last-Modified headers depending on whether they are from regular images or from Favicons. Favicons are generally modified far less often than other images on a webpage, so being able to identify their Last-Modified timestamp separately from the other images is helpful when trying to pinpoint when a site became active or made a design change.

### What are the limitations?
- RDAP data may not be available for all TLDs. Although RDAP has superseded WHOIS, not all TLDs have reachable RDAP servers or provide full registration date information.
- Some websites may block automated requests with captchas etc. This tool is respectful of captchas and paywalls and does not attempt to bypass them.
- Not all webservers choose to use Last-Modified headers. In this case the technique will not work and you will not see any results.
- Certificate history depends on public CT logs. These have generally been available since 2013, but sites older than this may have been issued with certificates prior to this that do not appear in public CT logs.

### How can I interpret the results?
The timeline view helps visualize the chronological relationship between:  
- When the domain was registered  

- When SSL certificates were first issued   

- When image files were last modified on the target webserver  

- Use mouse scroll to zoom in and out on the timeline. 

This can help establish how long a website has been active and identify recent changes. My original use case for this tool was to obtain reliable information for sites used for phishing, fraud, disinformation and other deceptive purposes. The tool provides timestamp information from reliable sources and helps to age a website or article much more accurately, regardless of any impersonation or deception by the target website.

### Why don't I see any data for the Last-Modified headers from the URL that I queried?
Not all websites use Last-Modified headers, so this technique will not work for them.

### Is Last-Modified header information the same as file metadata/EXIF?
No. This tool does not collect image metadata information. Last-Modified header timestamps are based on when the origin webserver believes that particular content was modified on the server. Neither the origin server nor this tool examine the file metadata. To do that you need to download the files directly and analyse them with Exiftool or similar.

### I don't get any results from the Domain query.
Most TLDs support RDAP and will provide registration date and time results. However not all TLDs (such as .de or .us) currently do so at time of writing. Some RDAP servers may also choose to rate limit or block requests.

### Why not use WHOIS?
WHOIS was deprecated in favour of RDAP in January 2025. WHOIS records are provided in an unstructured, non-standardised text format and are extremely frustrating to work with programatically. If you are really struggling for RDAP results, try https://bigdomaindata.com for WHOIS records.

### Why use SSL certificates?
SSL certificates are a highly accurate source of data. Since about 2013 every SSL certificate ever issued has been publicly logged via Certificate Transparency (CT) logs. Sites that do not have SSL certificates are not trusted by browsers and are de-ranked by search engines, so even deceptive or malicious websites still need to obtain an SSL certificate. This tool identifies the first CT log entry for the target domain, and so provides a highly reliable datapoint about when the site likely became active.

### Why not use article publication timestamps?
It is [very easy](https://https://www.admincolumns.com/change-date-on-wordpress-post/) to retrospectively change or alter publication timestamps on website content after an article has been created. While the majority of sites do not do this, some deceptive sites manually alter publication timestamps to make websites appear older than they really are. By contrast Last-Modified headers are derived from the origin server's own time settings. While it is theoretically possible to try and modify the server clock, making significant changes to a server's time will cause much of its functionality to break. It is much more difficult to falsify a Last-Modified header than it is to amend an article publication date in WordPress for example.

### The results show that the first SSL certificate was obtained before the domain was even registered - how is this even possible?
I've noticed that some RDAP results do not take breaks in ownership into account when determining a domain's first registration date. For example: a domain was first registered on 1st Jan 2018 and obtained an SSL certificate the same date. On 31st December 2018 the owner decides not to renew and the domain is put up for sale and the cert eventually expires.  


On 1st Jan 2025 a new owner purchases the domain. Some RDAP servers have no knowledge of the inital registration in 2018 and will report the 2025 registration as the first registration date, but the SSL module will still (correctly) report that the first certificate was issued in 2018, therefore causing the results to show that the certificate was obtained before the domain was ever registered, which looks like it should be impossible.
This is a quirk of some RDAP servers when there have been breaks in domain ownership. If in doubt I recommend consulting historic registration repositories like [Whoxy.com](https://whoxy.com) or [BigDomainData.com](https://bigdomaindata.com) to validate the first registration date.