# Paperless

Purpose: Paperless manages documents, extraction, and optional AI processing.
Status: current. Reviewed against: `4f168c05ab6022cbcdde791c7e230815b73cdc59`.

## Dependencies

The app uses Redis for its task queue, Tika and Gotenberg for document conversion,
and the credential ExternalSecret. GPT calls the Paperless API and the configured
OpenAI models separately for OCR and metadata suggestions.

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

Metadata uses a model family supported by the bundled OpenAI client's temperature
handling. Its reasoning-model detection recognizes GPT-5 names, while GPT-6
metadata requests receive an unsupported default temperature. The vision path
has its own explicit temperature setting. Recheck this restriction when updating
the client; successful direct API access alone does not prove application
compatibility. See the [client serializer](https://github.com/tmc/langchaingo/blob/v0.1.15/llms/openai/internal/openaiclient/chat.go#L95-L154)
and [Paperless GPT configuration](https://github.com/icereed/paperless-gpt/blob/v0.31.0/README.md#environment-variables).

Saved OCR defaults in `config/settings.json` override corresponding environment
defaults. Verify the effective page limit and upload/replacement options through
`GET /api/ocr/config` after changing configuration. Ordinary OCR updates searchable
text; PDF upload and replacement are separate options and remain disabled.

Repeated OCR or metadata failures remove the corresponding processing trigger and
apply `paperless-gpt-failed`. Correcting configuration alone does not requeue those
documents. After preserving their current state, restore the OCR trigger
`paperless-gpt-ocr-auto` and metadata trigger `paperless-gpt-auto` for documents
that need both stages. The background processor runs OCR before metadata. Verify
successful writes back to Paperless, preservation of the original files and
unrelated metadata, and removal of both triggers before clearing the failure
marker. Keep retry limits enabled to avoid indefinitely repeating paid failures.

## Sources

- [App metadata](../../../../apps/selfhosted/paperless/app.yaml)
- [Helm values](../../../../apps/selfhosted/paperless/values.yaml)
- [Raw manifests](../../../../apps/selfhosted/paperless/manifests)
- [OCR defaults and settings precedence](https://github.com/icereed/paperless-gpt/blob/v0.31.0/settings.go)
- [Background processing and failure tags](https://github.com/icereed/paperless-gpt/blob/v0.31.0/background.go)
- [Processing safeguards](../../../../tests/config/kubernetes/test_paperless.py)

## Related pages

- [GitOps delivery](../../architecture/gitops-delivery.md)
- [Storage](../../architecture/storage.md)
- [Networking](../../architecture/networking.md)
