# Runtime secrets

Create these UTF-8 text files locally before starting production Compose:

- `postgres_password.txt`
- `minio_root_password.txt`
- `api_key_pepper.txt` (at least 32 random characters; this is not a client key)
- `provider_api_key.txt` (the selected hosted LLM provider credential)
- `grafana_admin_password.txt` (required only by the `observability` profile)

Generate independent random values and keep each file to one line. Example with PowerShell:

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
[Convert]::ToBase64String($bytes)
```

Do not commit generated files. The `.gitignore` in this directory tracks only this guide.
