/* ============================================================
   Ollama Gateway — deshacer 001_create_tables.sql

   Borra ÚNICAMENTE las 4 tablas que creó el gateway.
   NO toca Users, ExternalLogins, ProvisionedDatabases ni
   DatabaseCredentials.

   El orden importa: primero las que tienen claves foráneas.

   OJO: esto borra los datos de consumo y auditoría. Úsalo solo
   si quieres empezar de cero.
   ============================================================ */

IF OBJECT_ID('dbo.RequestLogs', 'U') IS NOT NULL
    DROP TABLE dbo.RequestLogs;
GO

IF OBJECT_ID('dbo.ApiKeyUsage', 'U') IS NOT NULL
    DROP TABLE dbo.ApiKeyUsage;
GO

IF OBJECT_ID('dbo.ApiKeys', 'U') IS NOT NULL
    DROP TABLE dbo.ApiKeys;
GO

IF OBJECT_ID('dbo.LlmModels', 'U') IS NOT NULL
    DROP TABLE dbo.LlmModels;
GO
