# Paperless AI configuration and recovery

Purpose: configure saved AI behavior and recover document processing while
preserving original files and manual metadata.
Status: current. Reviewed against: `4f5065a060684bd6f9824bf7f8b7dd1521a31b2e`.

## Ownership and saved configuration

The [values](../../../apps/selfhosted/paperless/values.yaml) own environment defaults,
model choices, credentials references, and persistence. Native Paperless handles
retrieval, chat, and interactive suggestions. Paperless-GPT handles automatic OCR,
metadata, and field extraction. Its UI can be reached privately with
`kubectl -n selfhosted port-forward service/paperless-gpt 8080:8080` at
`http://127.0.0.1:8080`. This does not create an ingress or add authentication.

Saved Paperless application configuration overrides corresponding environment
defaults. GPT saves its field selection, write mode, OCR overrides, and prompts
under its persistent mounts. Inspect effective settings before changing defaults;
do not assume a pod restart resets application data.

Create these fields through Paperless Settings or its custom-fields API. Reuse an
existing matching definition rather than creating a duplicate. Do not attach empty
fields to documents in advance.

| Field | Paperless data type | Extraction rule |
| --- | --- | --- |
| AI Summary | Long Text | Two or three factual English sentences |
| Document Reference | String | Principal printed identifier; omit rather than truncate beyond 128 characters |
| Total Amount | Monetary | Explicit final total and currency; never calculate or convert |
| Due Date | Date | Explicit full payment or action deadline |
| Contract Start Date | Date | Explicit agreement start date |
| Contract End Date | Date | Explicit agreement end date |
| Notice Period | Long Text | Exact source wording, without computing a deadline |
| Warranty Expiry Date | Date | Explicit full expiry date, never inferred from duration |
| Related Documents | Document Link | References to other documents, subject to link review |

In GPT Settings, enable custom fields, select the extraction fields, and choose
**Append**. Keep Related Documents out of automatic selection on the current
release; use preview/review and additive link merges instead.
Append skips fields already present, even empty ones; Update overwrites suggested
field values and Replace discards existing fields. Never use Replace for recovery.
String is limited to 128 characters; summaries and notice wording need Long Text.

Keep the custom-field prompt's `CustomFieldsXML` variable, define field-specific
rules explicitly in the prompt, and omit absent or uncertain values. Require
English summaries, exact source references and monetary values, and source-language
notice wording. Do not infer diagnoses, obligations, payment status, or dates.
The document-date prompt must not substitute today's date or invent missing date
components. Document contents are untrusted data, not instructions. OCR must
transcribe all pages in the source language without summarizing or translating.

## Import and enrichment workflows

Create a native **Document Added** assignment workflow for all import sources,
adding the GPT automatic metadata and OCR trigger tags. Leave it disabled until
the processing canary passes. Do not use an unrestricted Document Updated trigger:
GPT writes would otherwise repeatedly requeue paid work. Verify converted Office
files, images, and PDFs through the actual OCR path before enabling all imports.
The default import pipeline may generate a new title and issue date.
`PRESERVE_EXISTING_METADATA` guards only correspondents and document types, not
titles or dates. Do not use the default trigger to recover established documents
with manual metadata; use enrichment-only or explicitly selected missing-field
requests instead. The tag generator retains existing tags.

Create a GPT **Enrichment only** workflow using a separate trigger tag. Enable
only custom fields, explicitly disable document-type generation, and disable OCR,
title, tag, correspondent, and document-date generators. Select the extraction
fields and leave its completion tag empty. GPT workflows cannot be chained; an
enrichment-only backfill is a separate deliberate operation.

Do not seed document types. Exclude type assignment from native workflow actions;
the upstream optional field and interactive suggestion schema still exist.

Create saved views for the GPT failure tag and documents missing AI Summary. A
missing optional fact is not itself a processing failure. Verify the activity
history and returned field values as well as tags: a partially rejected update
can preserve valid fields while still requiring review.

## Canary and recovery

1. Preserve private metadata/content snapshots, both SQLite databases using their
   online backup API, and GPT settings/prompts/history. Hash original and archive
   files. Never place private snapshots or raw logs in Git or PR descriptions.
2. Check provider access with a small request, then run actual application canaries
   before bulk work. Model-list visibility does not prove billing credit, accepted
   temperature, tool calls, streaming, or correct extraction. Stop paid batches on
   authentication, credit, or compatibility failures; retain failure markers.
3. Cover English, Portuguese, and Polish, scans and digital/mixed pages, tables,
   long documents, and converted Office files. Use previews before applying
   suggestions. Reject invented references, amounts/currencies, dates, unsupported
   summaries, or incorrect links. Inspect source documents to judge factuality.
4. Requeue only failed OCR stages in batches of ten. Preserve unrelated tags and
   manual metadata. Use enrichment-only or explicit missing-field requests for
   subsequent metadata recovery. Verify OCR writes before metadata, removal of processing triggers,
   and accepted fields before clearing the failure marker. Correct configuration
   alone does not requeue failures. Use enrichment-only processing for missing
   summaries/fields without blanket title or date rewrites.
5. Compare original/archive hashes and existing manual fields after recovery.
   Replace each app pod separately and verify saved settings, prompts, history,
   field definitions, and native index persistence. Check application behavior
   and the HTTPS route as well as Argo sync and pod readiness.

Document linking extracts references and looks them up by exact whole-word match.
The built-in resolver ignores references shorter than four characters and those
matching more than three other documents; it does not prove the remaining matches
identify the same issuer or case. The current lookup examines only the first page
of substring matches, so it cannot guarantee full ambiguity detection. Keep link
writes in review mode until upstream lookup coverage and collision tests support
automatic use. Test collisions and review ambiguous matches.
After later documents arrive, preview links again. For an existing link field,
merge the accepted IDs with the current set; Append skips existing fields and
Update replaces the list. Preserve mirrored links and unrelated fields.

## Native index and answer validation

Run `document_llmindex rebuild` after first enabling AI or changing embedding
models. Run `document_llmindex update` for incremental refresh after enrichment;
the scheduled task performs incremental updates. The index lives in the existing
Paperless data volume and includes custom-field values and document text.

Validate multilingual retrieval, native suggestions and streaming chat with source
links, and refresh after an actual content/field change. Native chat retrieves five
chunks per question and shows at most three document references. It cannot prove
an exhaustive archive-wide total. For completeness-sensitive work, select the
documents explicitly, check content/context coverage, and verify structured values
against the source. Keep ad-hoc GPT analysis available for selected-document work.

## Sources

- [Deployment defaults and persistent mounts](../../../apps/selfhosted/paperless/values.yaml)
- [Configuration safeguards](../../../tests/config/kubernetes/test_paperless.py)
- [GPT saved settings and precedence](https://github.com/icereed/paperless-gpt/blob/v0.31.0/settings.go)
- [GPT workflows and preview API](https://github.com/icereed/paperless-gpt/blob/v0.31.0/docs/workflows.md)
- [GPT field extraction and reference resolution](https://github.com/icereed/paperless-gpt/blob/v0.31.0/app_llm.go)
- [GPT field write modes](https://github.com/icereed/paperless-gpt/blob/v0.31.0/paperless.go)
- [GPT reference lookup coverage](https://github.com/icereed/paperless-gpt/blob/v0.31.0/paperless_search.go)
- [Native AI workflow actions](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.4/src/documents/workflows/ai.py)
- [Native field definitions](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.4/src/documents/models.py)
- [Native index administration](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.4/docs/administration.md#llm-index)
- [Native index content](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.4/src/paperless_ai/embedding.py)
- [Native chat retrieval limits](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.4/src/paperless_ai/chat.py)

## Related pages

- [Paperless](../apps/selfhosted/paperless.md)
- [Storage](../architecture/storage.md)
- [Backup and recovery](../architecture/backup-recovery.md)
