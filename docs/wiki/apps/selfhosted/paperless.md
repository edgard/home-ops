# Paperless

Purpose: Paperless manages documents, extraction, and optional AI processing.
Status: current. Reviewed against: `757e232266dbc2be725280a696efa476fcdc810e`.

## Dependencies

The app uses Redis for its task queue, Tika and Gotenberg for document conversion,
and the credential ExternalSecret. GPT calls the Paperless API and the configured
OpenAI models separately for OCR and metadata suggestions. Native Paperless AI
uses the existing OpenAI credential for embeddings, retrieval, document chat, and
interactive suggestions. GPT owns automatic metadata and custom-field enrichment;
do not add a second automatic writer for those fields.

The main container's startup probe allows cold AI initialization to finish before
restarting it. Readiness still gates traffic while it starts; the startup budget
is owned by the [deployment values](../../../../apps/selfhosted/paperless/values.yaml).

Document-type generation is disabled in GPT. Keep it explicitly disabled in GPT
workflow overrides and exclude it from any native AI workflow action. Paperless
has no global switch removing its optional document-type field or the native
interactive suggestion schema.

## Data and recovery

The app-owned `data` PVC stores the Paperless database, documents, export, and
inbox directories. GPT mounts its settings, prompts, and SQLite history from
`data/gpt` on that same claim. These directories must survive pod replacement;
they contain saved behavior and undo/OCR history. Preserve existing container-local
GPT files before first enabling these mounts. Check
[restore eligibility](../../architecture/backup-recovery.md) against the current
claim and storage class; restoring this claim affects both Paperless and GPT.
GPT's `PUID`/`PGID` match Paperless's `USERMAP_UID`/`USERMAP_GID` because the
Paperless entrypoint recursively sets data-directory ownership on startup.
Keep these aligned so restarting either controller preserves GPT write access.
The native vector index lives in `data/llm_index` on the same claim. It is derived
data and can be rebuilt after changing embedding models. Field definitions,
saved views, and native import workflows live in the Paperless database; GPT
field selection, write mode, prompt edits, and enrichment workflows are saved
application data rather than environment variables. Back up both databases and
the GPT configuration together before recovery or migration.

## Networking and monitoring

The app values configure a route through the shared Gateway. Check [Gatus values](../../../../apps/platform-system/gatus/values.yaml) for the current explicit uptime target and probe path.

## Operational note

Document import, OCR, AI behavior, and recovery have distinct failure modes; test the requested path directly.

The [values](../../../../apps/selfhosted/paperless/values.yaml) bound rendered
page dimensions and DPI before vision requests. Large images can exceed the
provider's per-image patch limit even when their compressed file size is small.
Upstream PDF rendering has a minimum DPI; exceptionally large page formats can
still exceed the configured dimensions and require resizing the input.
Automatic OCR processes every page because it replaces the document's searchable
text; a page cap would replace that text with only part of the document.
Clean digital pages can reuse their original text; image-only or hidden-text scans
still need the OCR path. OCR preserves source language, while generated titles and
summaries use English. Keep original PDF upload/replacement disabled with the
current LLM OCR provider; searchable-PDF generation requires hOCR support.

Metadata uses a model family supported by the bundled OpenAI client's temperature
handling. Its reasoning-model detection recognizes GPT-5 names, while GPT-6
metadata requests receive an unsupported default temperature. The vision path
has its own explicit temperature setting. Recheck this restriction when updating
the client; successful direct API access alone does not prove application
compatibility. See the [client serializer](https://github.com/tmc/langchaingo/blob/v0.1.15/llms/openai/internal/openaiclient/chat.go#L95-L154)
and [Paperless GPT configuration](https://github.com/icereed/paperless-gpt/blob/v0.31.0/README.md#environment-variables).

Native AI uses a different client: suggestions call Chat Completions tools, so
the configured model needs tool support on that endpoint and the explicit
reasoning/temperature parameters in the values. A model listed by the provider
is not proof of request compatibility or available billing credit. Native chat
retrieves five text chunks per question; it is retrieval-assisted Q&A, not an
exhaustive archive-wide calculation. See the [native client](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.4/src/paperless_ai/client.py)
and [chat retrieval](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.4/src/paperless_ai/chat.py).

Saved OCR defaults in `config/settings.json` override corresponding environment
defaults. Verify the effective page limit and upload/replacement options through
`GET /api/ocr/config` after changing configuration. Ordinary OCR updates searchable
text; PDF upload and replacement are separate options and remain disabled.

Repeated OCR or metadata failures remove the corresponding processing trigger and
apply `paperless-gpt-failed`. Correcting configuration alone does not requeue those
documents. After preserving their current state, restore only the OCR trigger
`paperless-gpt-ocr-auto` for documents whose OCR failed. Verify those writes before
running enrichment-only or explicitly selected missing-field requests. Do not
blanket requeue existing documents with `paperless-gpt-auto`: default processing
generates titles and dates, and `PRESERVE_EXISTING_METADATA` protects only existing
correspondents and types. The default pipeline remains appropriate for new
imports; the background processor runs OCR before metadata. Verify original files,
unrelated metadata, accepted fields, and removal of processing triggers before
clearing the failure marker. Keep bounded retries enabled.
Use the [AI configuration and recovery procedure](../../operations/paperless-ai.md)
for field definitions, import routing, enrichment-only backfills, canary gates,
reference-link review, and index validation. Never publish document contents,
private snapshots, or unsanitized application logs as verification evidence.

## Sources

- [App metadata](../../../../apps/selfhosted/paperless/app.yaml)
- [Helm values](../../../../apps/selfhosted/paperless/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/paperless/manifests)
- [OCR defaults and settings precedence](https://github.com/icereed/paperless-gpt/blob/v0.31.0/settings.go)
- [Background processing and failure tags](https://github.com/icereed/paperless-gpt/blob/v0.31.0/background.go)
- [Processing safeguards](../../../../tests/config/kubernetes/test_paperless.py)
- [Native AI configuration](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.4/docs/advanced_usage.md#ai-features)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
- [AI configuration and recovery](../../operations/paperless-ai.md)
