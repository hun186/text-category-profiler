# Historical wiki article research text

The original tracked object `text_category_profiler/sample_data/俄烏戰爭@wiki`
has been relocated **without editing its contents** to
`experiments/fixtures/wiki_article/俄烏戰爭@wiki`.

- Original Git blob SHA-1: `85e7f0573296fe49f603a6bec14c043b378e64db`
- Original size: **83123 bytes**
- Format: extensionless text snapshot, as historically committed
- Purpose: preservation of an old manually collected research corpus, **not**
  a classifier input contract or a production data feed

The text identifies itself as content from a Wikipedia article about the
Russia–Ukraine War, but the original revision URL, capture date, full
attribution and **licensing** conditions have **not verified** provenance.
The page text is not re-fetched, normalized, excerpted or regenerated here;
review the actual source and applicable license before redistribution.

**External/manual callers are not verified.** The previous path is removed;
there is no symlink, re-export or fallback. First-party Python filename
literals are checked by the dependency-light boundary test, but dynamic
paths, non-Python scripts and out-of-repository callers cannot be ruled out.
Update such callers explicitly before expecting the new path to work.

This batch does not run NLP models, WorkPool jobs, network requests, or
external integrations.
