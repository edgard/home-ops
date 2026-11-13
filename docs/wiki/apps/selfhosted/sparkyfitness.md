# SparkyFitness

Purpose: private fitness and nutrition tracking with native OpenAI features.
Status: current. Reviewed against: `f1b33764a7773877d10b843e1a0aa02b9ec19365`.

## Deployment and account setup

One app-template Application owns the frontend with bundled Nginx, backend,
dedicated PostgreSQL Deployments. Only the frontend has an HTTPS
route. The backend applies its normal startup migrations and maintains its
restricted database role, including generating that role's password.

ESO supplies only the PostgreSQL owner password, API-encryption key and
authentication secret. Keep these stable in Bitwarden; encrypted provider tokens
and authentication data need the same keys after recovery. The automation
machine account remains read-only. The administrator email is ordinary
configuration, and no administrator password is stored in the deployment.

The configured administrator email is `castro@edgard.org`. Registration is closed
with `SPARKY_FITNESS_DISABLE_SIGNUP=true`; existing accounts continue to sign in
with their chosen passwords. Temporarily reopening registration requires an
explicit GitOps change.

The frontend uses its packaged configuration, non-root port and fully qualified
backend hostname. The backend trusts the existing gateway plus bundled frontend
proxy chain. A writable ephemeral `/run` holds Nginx's PID for non-root startup.
The backend uses writable `/tmp` for temporary upload files. Native restore
stages the recovered upload tree on the data volume under `/data/uploads/_staging`.

Garmin Connect is disconnected and its optional sync service is not deployed.
Previously imported fitness records remain in PostgreSQL. An older native
backup can restore the saved connection; unlink it again if it reappears.

## AI onboarding

Use the existing Bitwarden `openai_api_key` when configuring providers through
the native UI. SparkyFitness encrypts the saved keys in PostgreSQL; an OpenAI
environment variable does not configure its database-backed provider settings.
If that shared key is rotated, update the native provider settings too.

Configure an active global OpenAI Chat and Vision service with `gpt-6.1-sol`,
high reasoning and the full tool profile. Select it as the global vision default
and explicitly select it for the administrator's chat and vision preferences.
Allow user AI configuration, enable AI-assisted conversions, and add an active
OpenAI Voice configuration using `gpt-transcribe` with audio input enabled.
Select AI transcription and that Voice configuration in the user's voice settings.
Microphone permission remains a browser/mobile-client action.

This enables the native assistant's food-photo and label recognition, nutrition
estimation, diary actions, recipes and meal planning, web research, preferences
and saved tasks, exercise/water/measurement logging, calorie-target reviews,
training/run reviews and proposed plan changes. Retain native confirmations;
developer SQL tools and private-network access keep their defaults. Chat,
structured image analysis and voice use the application's supported OpenAI
transports. OpenAI processes submitted AI text, images and audio.

## Storage and backups

One retained NFS claim contains PostgreSQL, uploads and backup subdirectories.
The backend mounts the parent at `/data` and uses `/data/uploads` and
`/data/backups`. Native restore swaps staged entries into the uploads directory
on the same filesystem and retains the previous files. PostgreSQL mounts only its own subdirectory
at `/var/lib/postgresql`, with versioned PGDATA beneath it. Preserve the common
volume group while allowing the official PostgreSQL entrypoint to initialize its
private data directory and drop privileges.

During onboarding, enable the native full backup every day at `00:00` UTC with
seven-day retention. Its scheduler uses UTC regardless of the application time
zone: this is 01:00 Warsaw in winter and 02:00 in summer, before nightly Restic.
The backend image already includes matching PostgreSQL client tools. Native
backup packages compressed SQL and uploads, publishing the finished archive
after temporary work completes. Restic includes uploads and completed archives,
excluding live PostgreSQL and backup `.tmp` contents.

These are online backups, with separate database and upload capture times.
Check the native backup status and a completed archive; a healthy route does not
prove a successful backup. For a live app, recover an archive if necessary and
use Admin backup/restore. Validate records, upload hashes, login and decrypted
provider settings after import, rather than relying only on its success message.

For cold recovery, follow the [application recovery procedure](../../operations/restic-backup-restore.md#sparkyfitness-database-and-files).
Generic Restic file restoration alone does not import PostgreSQL data.

## Sources

- [App metadata](../../../../apps/selfhosted/sparkyfitness/app.yaml)
- [Helm values](../../../../apps/selfhosted/sparkyfitness/values.yaml)
- [ExternalSecret](../../../../apps/selfhosted/sparkyfitness/manifests/sparkyfitness-credentials.externalsecret.yaml)
- [Restic exclusions](../../../../apps/selfhosted/restic/values.yaml)
- [Upstream Garmin unlink route](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.12.1/SparkyFitnessServer/routes/garminRoutes.ts) removes the saved connection.
- [Upstream startup requirements](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.12.1/SparkyFitnessServer/utils/preflightChecks.ts)
- [Upstream AI features](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.12.1/docs/src/features/ai-assistant.md)
- [Native backups and restoration](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.12.1/SparkyFitnessServer/services/backupService.ts)
- [Native backup scheduler](https://github.com/CodeWithCJ/SparkyFitness/blob/v1.12.1/SparkyFitnessServer/services/backupScheduler.ts)

## Related pages

- [Backup and recovery](../../architecture/backup-recovery.md)
- [Secrets](../../architecture/secrets.md)
- [Uptime monitoring](../../architecture/uptime.md)
