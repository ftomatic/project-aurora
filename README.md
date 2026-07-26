Project Aurora
===============

Aurora is RainbowMilkStudio's local production operating system for researching,
planning, creating, validating, and preparing Etsy digital products.

Sprint 34 Production Safety
---------------------------

The current production flow is:

Research -> Seasonal Intelligence -> Product Transformation -> Creative Director
-> Product Blueprint -> Structured Prompt Builder -> Image Generation
-> Commercial Image QA -> Merchant Preflight -> Etsy Draft Creation
-> Listing Image Upload -> Customer File Upload.

Seasonal Intelligence uses `config/seasonal_calendar.yaml` to decide whether a
product should be produced now, held, treated as evergreen, or built for an
upcoming season. Graduation products are not automatically produced in late July
unless explicitly treated as inventory build.

The Creative Director creates a structured product brief before image generation.
Briefs include target customer, commercial use case, required objects, forbidden
objects, palette, rendering family, text policy, and a product-level consistency
key.

The default text policy is `FORBIDDEN`: generated artwork must not include text,
words, letters, numbers, dates, years, logos, watermarks, signatures, labels, or
captions. Products that need typography should use a controlled post-processing
or template step rather than asking the image model to invent text.

Image blueprints define the four customer-facing roles for each product:
hero cover, collection overview, detail preview, and use-case/mockup. Every
prompt in a product set shares the same style, palette, rendering family, mood,
and consistency key.

Commercial Image QA is configured by `config/creative_quality.yaml`. It blocks
stale or mismatched files, explicit years, unintended text requests, image-count
mismatches, and inconsistent prompt roles before Etsy draft creation.

Safe Commands
-------------

Preview one creative brief without OpenAI or Etsy:

```bash
.venv/bin/python scripts/preview_creative_brief.py --product "Back to School Watercolor Clipart"
```

Run the full test suite:

```bash
.venv/bin/python -m pytest
```
