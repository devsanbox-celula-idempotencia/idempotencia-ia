/* ============================================================
   Ollama Gateway — tablas nuevas
   SQL Server. Se apoya en tu tabla Users existente.
   Ejecutar una sola vez sobre tu base de datos.
   ============================================================ */

/* ------------------------------------------------------------
   1) ApiKeys — claves que usan tus clientes (sk_live_...)
   ------------------------------------------------------------ */
IF OBJECT_ID('dbo.ApiKeys', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ApiKeys (
        ApiKeyId           INT IDENTITY(1,1) NOT NULL,
        UserId             INT             NOT NULL,
        Name               NVARCHAR(100)   NOT NULL,
        KeyHash            NVARCHAR(64)    NOT NULL,   -- SHA-256 en hexadecimal
        KeyPrefix          NVARCHAR(20)    NOT NULL,   -- "sk_live_abc1" para el panel
        IsActive           BIT             NOT NULL CONSTRAINT DF_ApiKeys_IsActive DEFAULT (1),
        CreatedAt          DATETIME2(0)    NOT NULL CONSTRAINT DF_ApiKeys_CreatedAt DEFAULT (SYSUTCDATETIME()),
        ExpiresAt          DATETIME2(0)    NULL,
        LastUsedAt         DATETIME2(0)    NULL,
        DailyTokenLimit    INT             NULL,
        MonthlyTokenLimit  INT             NULL,
        RequestsPerMinute  INT             NULL,
        CONSTRAINT PK_ApiKeys PRIMARY KEY (ApiKeyId),
        CONSTRAINT UQ_ApiKeys_KeyHash UNIQUE (KeyHash),
        CONSTRAINT FK_ApiKeys_Users FOREIGN KEY (UserId) REFERENCES dbo.Users (UserId)
    );

    CREATE INDEX IX_ApiKeys_UserId ON dbo.ApiKeys (UserId);
END
GO

/* ------------------------------------------------------------
   2) ApiKeyUsage — consumo acumulado por clave y día
   ------------------------------------------------------------ */
IF OBJECT_ID('dbo.ApiKeyUsage', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ApiKeyUsage (
        UsageId           BIGINT IDENTITY(1,1) NOT NULL,
        ApiKeyId          INT     NOT NULL,
        [Day]             DATE    NOT NULL,
        PromptTokens      BIGINT  NOT NULL CONSTRAINT DF_Usage_Prompt     DEFAULT (0),
        CompletionTokens  BIGINT  NOT NULL CONSTRAINT DF_Usage_Completion DEFAULT (0),
        TotalTokens       BIGINT  NOT NULL CONSTRAINT DF_Usage_Total      DEFAULT (0),
        Requests          INT     NOT NULL CONSTRAINT DF_Usage_Requests   DEFAULT (0),
        CONSTRAINT PK_ApiKeyUsage PRIMARY KEY (UsageId),
        CONSTRAINT UQ_ApiKeyUsage_ApiKey_Day UNIQUE (ApiKeyId, [Day]),
        CONSTRAINT FK_ApiKeyUsage_ApiKeys FOREIGN KEY (ApiKeyId) REFERENCES dbo.ApiKeys (ApiKeyId)
    );
END
GO

/* ------------------------------------------------------------
   3) RequestLogs — auditoría de cada petición
   ------------------------------------------------------------ */
IF OBJECT_ID('dbo.RequestLogs', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.RequestLogs (
        RequestLogId      BIGINT IDENTITY(1,1) NOT NULL,
        ApiKeyId          INT             NULL,        -- NULL si falló la autenticación
        Model             NVARCHAR(100)   NOT NULL,
        Endpoint          NVARCHAR(100)   NOT NULL,
        PromptTokens      INT             NOT NULL CONSTRAINT DF_Logs_Prompt     DEFAULT (0),
        CompletionTokens  INT             NOT NULL CONSTRAINT DF_Logs_Completion DEFAULT (0),
        TotalTokens       INT             NOT NULL CONSTRAINT DF_Logs_Total      DEFAULT (0),
        DurationMs        INT             NOT NULL CONSTRAINT DF_Logs_Duration   DEFAULT (0),
        StatusCode        INT             NOT NULL CONSTRAINT DF_Logs_Status     DEFAULT (200),
        ClientIp          NVARCHAR(45)    NULL,
        Error             NVARCHAR(1000)  NULL,
        CreatedAt         DATETIME2(0)    NOT NULL CONSTRAINT DF_Logs_CreatedAt  DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_RequestLogs PRIMARY KEY (RequestLogId),
        CONSTRAINT FK_RequestLogs_ApiKeys FOREIGN KEY (ApiKeyId) REFERENCES dbo.ApiKeys (ApiKeyId)
    );

    CREATE INDEX IX_RequestLogs_ApiKey_CreatedAt ON dbo.RequestLogs (ApiKeyId, CreatedAt DESC);
    CREATE INDEX IX_RequestLogs_CreatedAt        ON dbo.RequestLogs (CreatedAt DESC);
END
GO

/* ------------------------------------------------------------
   4) LlmModels — catálogo de modelos que expone el gateway
   ------------------------------------------------------------ */
IF OBJECT_ID('dbo.LlmModels', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LlmModels (
        LlmModelId          INT IDENTITY(1,1) NOT NULL,
        ModelId             NVARCHAR(100) NOT NULL,   -- nombre público: "qwen2.5:3b"
        ProviderModel       NVARCHAR(100) NOT NULL,   -- nombre real en Ollama
        OwnedBy             NVARCHAR(50)  NOT NULL CONSTRAINT DF_Models_OwnedBy DEFAULT ('local'),
        ContextLength       INT           NULL,
        SupportsEmbeddings  BIT           NOT NULL CONSTRAINT DF_Models_Emb     DEFAULT (0),
        IsActive            BIT           NOT NULL CONSTRAINT DF_Models_Active  DEFAULT (1),
        CreatedAt           DATETIME2(0)  NOT NULL CONSTRAINT DF_Models_Created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_LlmModels PRIMARY KEY (LlmModelId),
        CONSTRAINT UQ_LlmModels_ModelId UNIQUE (ModelId)
    );
END
GO

/* ------------------------------------------------------------
   Carga inicial del modelo
   ------------------------------------------------------------ */
IF NOT EXISTS (SELECT 1 FROM dbo.LlmModels WHERE ModelId = 'qwen2.5:3b')
BEGIN
    INSERT INTO dbo.LlmModels (ModelId, ProviderModel, OwnedBy, ContextLength, SupportsEmbeddings)
    VALUES ('qwen2.5:3b', 'qwen2.5:3b', 'local', 32768, 0);
END
GO
