# About URL Dater



### What is URL Dater?

URL Dater is a utility that helps researchers by providing reliable sources of information about the age of a website and its content. It is intended to provide accurate date information and also to discover editorial changes.  

It does this by gathering information about the domain's registration date, SSL certificate history, and the Last-Modified header timestamp of images embedded in the websites. It combines multiple techniques to provide a comprehensive view of a website's history and content and provides a timeline of a website's history.

It is possible to run each module individually or all three at once.

### What information can I get from this tool?
- **Domain Information:** Registration dates and updates from [RDAP records](https://www.icann.org/rdap). RDAP (Registration Data Access Protocol) is the replacement for WHOIS. URL Dater uses RDAP to determine when a domain was first registered, and when the domain registration was last updated.
- **SSL Certificates:** This module checks Certificate Transparency log data from [crt.sh](https://crt.sh) to find the very first time that an SSL certificate was issued for a domain. CT log data is accurate as far back as 2013, so for sites that are older than this it will show the first SSL certificate available from public CT logs. 
- **Media Dates:** Many webservers use the [Last-Modified header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Last-Modified) property to avoid unnecessary loading of content. This provides an accurate indicator as to when a specific image was added to a webserver, so we can leverage this data point accurately identify when a particular piece of content.
- **Timeline View:** Visual representation of all dates in chronological order on a timeline.

I got the original idea for this from Lazza's excellent [Carbon 14](https://github.com/Lazza/Carbon14).

