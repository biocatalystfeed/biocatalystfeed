# BioCatalystFeed Hosted Services: Privacy Policy

_Effective: [EFFECTIVE DATE, set on publication]_

This policy covers the hosted BioCatalystFeed services: the public hosted MCP endpoint and BioCatalystFeed marketplace
listings (such as Apify). **The open-source CLI/MCP server you run yourself sends nothing to us.** It talks only to
the public data sources you query.

## Hosted MCP endpoint
- **No account, no cookies, no trackers.** We don't ask for your name or email.
- **Rate limiting:** your IP address is used as the key for per-IP rate limiting. A small counter (window start time
  and request count) is kept in a Cloudflare Durable Object named after your IP address and is deleted automatically
  about one minute after the window ends. It is not stored as a log.
- **Our own logging:** our code does not log request bodies, tool arguments, or results.
- **Our hosting provider:** the endpoint runs on Cloudflare Workers. Cloudflare processes each request (including IP
  address, user agent, URL path, and timing) to deliver and secure it, and may keep request metadata and aggregate
  analytics under its own privacy policy. We have turned off Cloudflare's Workers Logs for this endpoint, so we keep no
  request logs. If we ever switch them on briefly to fix a problem, they hold request metadata (not bodies) and are
  deleted automatically after 3 days.
- **Upstream queries:** to answer a tool call, the endpoint sends your query terms (for example a drug or sponsor name)
  to the relevant public source (ClinicalTrials.gov, openFDA, PubMed, Federal Register). These requests carry no
  information that identifies you; they identify BioCatalystFeed and give contact@biocat.ai as the contact.

## Marketplace listings
When you use BioCatalystFeed through a marketplace such as Apify, the marketplace handles your account, billing, and
payment data under its own privacy policy. We see only what it shares with us (for example run inputs, run logs, and
plan or usage information), and we use it only to run, support, and fix the service. We never receive full card
numbers.

## What we don't do
We don't sell or rent personal data or your queries, use your queries to trade or tip anyone off, or run advertising
trackers.

## Sharing
Only with the providers that run the Service (Cloudflare for hosting; the marketplace you chose), or when the law
requires it.

## Retention
Rate-limit counters: about one minute. Request logs: none kept (Workers Logs off; if briefly enabled for debugging, deleted after 3 days). Marketplace data: as set by the
marketplace, and for any data we keep, no longer than 90 days unless needed for billing or legal records.

## Your rights
Contact us to ask about, access, or delete data relating to you. Because the hosted endpoint has no accounts, we
may not be able to link data to you without details such as your IP address and time of use. Depending on where you
live (for example under the GDPR or CCPA), you may have more rights, including the right to complain to a regulator.

## Security
Encryption in transit (HTTPS only), least-privilege access, and secrets kept out of code. No system is perfectly
secure.

## Children
The Service isn't for anyone under 18.

## International transfers
Cloudflare serves requests from its global network, and data may be processed in the United States and other
countries. Where the law requires a transfer mechanism (for example Standard Contractual Clauses), we rely on our
providers' mechanisms.

## Changes
We'll post updates in this file with a new effective date.

## Contact
contact@biocat.ai
