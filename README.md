# Neutron Bytes Nuclear Sector Intelligence

Interactive source-linked nuclear news tracker with the original Neutron Bytes navy/blue/light-gray design.

- **Research archive:** 2020–2024 quarterly; 2025–2026 monthly.
- **Filters:** Global keyword search across the full indexed dataset, Year, Month (2025–26 only), Technology, and Commercial category.
- **Multi-tagging:** Stories may appear under multiple technology and commercial tags; clicking tags applies filters.
- **Weekly Updates:** Most recent first, up to seven issues, starting September 2026.
- **Update cadence:** Every Monday at 07:00 America/Chicago via GitHub Actions. Site redeployment can be handled by a connected Vercel project.

The archive includes historical entries restored from an earlier approved Neutron Bytes HTML file, preserved separately as [legacy-archive.html](legacy-archive.html). Each news item links first to the dated Neutron Bytes article and then to any verified outside source links extracted from the original. Full article bodies are not reproduced. No commercial API or LLM API key is required.

The collectors classify each story across Traditional Fission / Advanced Fission / Microreactors / Fusion and independently across Restarts & Uprates; Offtakes & Customers; Construction & Licensing; Fuel & Supply Chain; Capital & Financing; Policy & International.

**Vercel:** If your live Vercel deployment was originally created through a manual HTML upload or from a different Git repository, it will **not** update when this repository changes. In Vercel Settings → Git, connect the live project to **shbansal6/neutron-bytes-digest**, with production branch **main**, or import this repository as a fresh Vercel project. For a plain HTML/CSS/JS site choose **Other**, root **./**, and leave Build Command and Output Directory overrides disabled.

**Research caveat:** The Neutron Bytes website often bundles multiple developments inside one dated post. The collector separates posts into discrete source-linked topics when headings clearly identify a story. These are brief attributions, not original journalism or independent fact verification; the source should always be reviewed before investment decisions.
