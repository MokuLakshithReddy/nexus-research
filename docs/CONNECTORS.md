# Source connectors

| Provider | Integration | Credential | Output | Constraints |
|---|---|---|---|---|
| OpenAlex | Public Works API | None; optional `NEXUS_CONTACT_EMAIL` | Work metadata, authors, dates, reconstructed abstract, citation count | Rate limits and metadata coverage vary |
| Crossref | Public Works API | None; optional contact email | DOI metadata, authors, journal and abstract if deposited | Abstracts are often absent |
| arXiv | Atom API | None | Preprint metadata and abstracts | Preprints may not be peer reviewed |
| GDELT | DOC 2.0 ArtList | None | News discovery metadata and canonical URLs | Not full article text; import publisher URLs for readable text |
| Brave Search | Web Search API | `BRAVE_SEARCH_API_KEY` | Web result titles, URLs, descriptions | Requires an API subscription/key |
| YouTube | YouTube Data API v3 | `YOUTUBE_API_KEY` | Video titles, channels, descriptions and URLs | No transcript retrieval in this release |
| X | Recent Search API | `X_BEARER_TOKEN` | Recent public post text, timestamps, post metrics | Access tier, quotas and recency window apply |
| Instagram | Not implemented | Meta app access/permissions | None | Not an unrestricted scraping API |
| Facebook | Not implemented | Meta app access/permissions | None | Supported Page/content access only |
| Google Scholar | Not integrated | N/A | None | Use OpenAlex, Crossref and arXiv instead of automated bulk scraping |

## Adding a provider

1. Implement an async `provider_search(query, limit)` adapter in `backend/app/research/providers.py`.
2. Return normalized source dictionaries: `provider`, `source_type`, `title`, `url`, `authors`, `published_at`, `description`, `content`, `relevance`, and `metadata`.
3. Register the adapter in `PROVIDERS`.
4. Add its connector status in `connector_status()` in `backend/app/main.py`.
5. Add provider tests for response normalization, missing fields, provider errors, and duplicate URLs.
6. Confirm the provider's API terms, access tier, rate limits, caching rules and attribution requirements.

Never implement login bypass, private-account extraction, CAPTCHA evasion, or scraping that violates provider rules.
