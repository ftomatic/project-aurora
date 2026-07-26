Aurora Agent Operating Notes
============================

Production agents must preserve the safety order:

Research -> Seasonal Intelligence -> Product Transformation -> Creative Director
-> Product Blueprint -> Structured Prompt Builder -> Image Generation
-> Commercial Image QA -> Merchant Preflight -> Etsy Draft Creation.

Do not create Etsy drafts before Commercial Image QA passes.

Default generated-art text policy is `FORBIDDEN`. Do not ask an image model to
create years, dates, words, labels, logos, typography, captions, signatures, or
watermarks. If a future product needs text, create a text-free image first and
add verified typography through a controlled template/post-processing step.

All generated files for a production job must stay inside that job's isolated
workspace under `data/aurora/jobs/<job_id>_<product_slug>/`. Upload and repair
workflows must reject stale or mismatched assets rather than globbing broad
runtime directories.

Use:

```bash
.venv/bin/python scripts/preview_creative_brief.py --product "Back to School Watercolor Clipart"
```

to inspect seasonal decision, creative brief, blueprints, prompts, and QA rules
without calling OpenAI or Etsy.
