param(
    [string]$DbHost = "localhost",
    [int]$DbPort = 5432,
    [string]$DbUser = "wallet",
    [string]$DbPassword = "wallet",
    [string]$DbName = "wallet"
)

$env:PGPASSWORD = $DbPassword

psql "host=$DbHost port=$DbPort user=$DbUser dbname=$DbName" -f "sql/schema.sql"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

psql "host=$DbHost port=$DbPort user=$DbUser dbname=$DbName" -f "sql/seed.sql"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Database seeded successfully."
