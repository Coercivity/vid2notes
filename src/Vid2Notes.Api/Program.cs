using Vid2Notes.Api.Extensions;

var builder = WebApplication.CreateBuilder(args);

builder.Services
    .AddPersistence(builder.Configuration)
    .AddObjectStorage(builder.Configuration)
    .AddMessaging(builder.Configuration)
    .AddApi();

var app = builder.Build();

await app.MigrateDatabaseAsync();
app.MapApi();

app.Run();
