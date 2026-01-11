## About URLDater

URL Dater is a utility designed to help researchers by providing reliable sources of information about the age of a website and its content. 

It does this by gathering information about the domain's registration date via RDAP, SSL certificate history, and the Last-Modified header timestamp of images embedded in the websites. It combines multiple techniques to provide a comprehensive view of a website's history and content and provides a timeline of a website's history.

It is possible to run each module individually or all three at once.

## Live Demo

You can use the web version of the tool at [URLDater.app](https://urldater.app). The demo server is very lightweight and will not perform as well when retrieving Last-Modified headers from very large web pages. I strongly recommend that you donwload and host this tool on your own infrastructure for better performance.

Instructions for self-hosting are below.

## What information can I get from this tool?

- **Domain Information:** Registration dates and updates from [RDAP records](https://www.icann.org/rdap). RDAP (Registration Data Access Protocol) is the replacement for WHOIS. URL Dater uses RDAP to determine when a domain was first registered, and when the domain registration was last updated.

- **SSL Certificates:** This module checks Certificate Transparency log data from [crt.sh](https://crt.sh) to find the very first time that an SSL certificate was issued for a domain. CT log data is accurate as far back as 2013, so for sites that are older than this it will show the first SSL certificate available from public CT logs. 
- **Media Dates:** Many webservers use the [Last-Modified header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Last-Modified) property to avoid unnecessary loading of content. This provides an accurate indicator as to when a specific image was added to a webserver, so we can leverage this data point accurately identify when a particular piece of content was created.
- **Timeline View:** Visual representation of all dates in chronological order on a timeline.

I got the original idea for this from Lazza's excellent [Carbon 14](https://github.com/Lazza/Carbon14).

## Installation

To run URL Dater locally simply clone the repo and build the Docker container. You will need to have Docker installed on your host machine.

```
git clone https://github.com/nixintel/urldater

cd urldater

docker compose up --build 
```

Once the Docker container is up and running open your browser and go to http://localhost:5000 to access the interface. You can edit the ports in `docker-compose.yml` as desired.

## Known Issues

Before filing any kind of bug report please ensure you have read the [FAQ](https://urldater.app/faq) to understand why the tool does not return data in some cases.

- The online demo version of URL Dater can struggle to load very large web pages when trying to retrieve Last-Modified headers and may timeout. This is a limitation of running on a lightweight web server. For better performance I recommend self-hosting.

- [Crt.sh](https://crt.sh) is used to retrieve SSL certificate information. It is occasionally unstable, offline, or suffers from slow performance. This in turn impacts the speed and availability of URL Dater results. Short of switching to a paid commercial API for certificate data I can't think of an easy way to work around it.

