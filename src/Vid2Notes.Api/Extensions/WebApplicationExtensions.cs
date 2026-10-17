using Microsoft.EntityFrameworkCore;
using Vid2Notes.Api.Data;
using Vid2Notes.Api.Endpoints;

namespace Vid2Notes.Api.Extensions;

public static class WebApplicationExtensions
{
    public static async Task MigrateDatabaseAsync(this WebApplication app)
    {
        await using var scope = app.Services.CreateAsyncScope();
        await scope.ServiceProvider.GetRequiredService<AppDbContext>().Database.MigrateAsync();
    }

    public static WebApplication MapApi(this WebApplication app)
    {
        app.UseSwagger();
        app.UseSwaggerUI();

        app.MapGet("/", () => Results.Redirect("/swagger")).ExcludeFromDescription();
        app.MapJobEndpoints();
        return app;
    }
}
