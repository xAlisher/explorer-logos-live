# explorer.logos.live

Read-only proof explorer for Logos **raw ChannelInscribe** inscriptions — the layer the LEZ
explorer/zonescan don't decode (tariqa-infra#59). Static single page, no backend.

Reads `/channel/<id>` + `/cryptarchia/info` from a public node (Paradox, CORS `*`) →
**finalized** (slot ≤ LIB) / **safe** (in a block) / **not inscribed**.
Shareable proof link: `explorer.logos.live/#<channel_id>`.

Source of record: [logos-live](https://github.com/xAlisher/logos-live) `explorer/` (logos-live#14, #13).
This repo exists only to host the subdomain (GitHub Pages takes one custom domain per repo).
