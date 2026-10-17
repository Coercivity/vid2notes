using MassTransit;
using Microsoft.EntityFrameworkCore;
using Vid2Notes.Api.Contracts;
using Vid2Notes.Api.Data;
using Vid2Notes.Api.Endpoints.Models;
using Vid2Notes.Api.Storage;

namespace Vid2Notes.Api.Endpoints;

public static class JobEndpoints
{
    public static void MapJobEndpoints(this IEndpointRouteBuilder app)
    {
        var jobs = app.MapGroup("/jobs").WithTags("Jobs");

        jobs.MapPost("/", CreateJob);
        jobs.MapGet("/{id:guid}", GetJob).WithName(nameof(GetJob));
        jobs.MapPost("/{id:guid}/extract", StartExtraction);
        jobs.MapGet("/{id:guid}/previews/{index:int}", GetPreview);
        jobs.MapGet("/{id:guid}/pdf", GetPdf);
    }

    private static async Task<IResult> CreateJob(
        CreateJobRequest request,
        AppDbContext db,
        ISendEndpointProvider sendEndpointProvider,
        CancellationToken cancellationToken)
    {
        if (!Uri.TryCreate(request.Url, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https"))
            return Results.ValidationProblem(new Dictionary<string, string[]> { ["url"] = ["A valid http(s) URL is required"] });

        var now = DateTimeOffset.UtcNow;
        var job = new Job
        {
            Id = NewId.NextSequentialGuid(),
            Url = uri.ToString(),
            Status = JobStatus.Analyzing,
            Stage = "queued",
            CreatedAt = now,
            UpdatedAt = now
        };
        db.Jobs.Add(job);

        var endpoint = await sendEndpointProvider.GetSendEndpoint(new Uri($"queue:{Queues.AnalyzeVideo}"));
        await endpoint.Send(new AnalyzeVideo(job.Id, job.Url), cancellationToken);
        await db.SaveChangesAsync(cancellationToken);

        return Results.AcceptedAtRoute(nameof(GetJob), new { id = job.Id }, JobResponse.From(job));
    }

    private static async Task<IResult> GetJob(Guid id, AppDbContext db, CancellationToken cancellationToken)
    {
        var job = await db.Jobs.AsNoTracking().FirstOrDefaultAsync(j => j.Id == id, cancellationToken);
        return job is null ? Results.NotFound() : Results.Ok(JobResponse.From(job));
    }

    private static async Task<IResult> StartExtraction(
        Guid id,
        ExtractRequest request,
        AppDbContext db,
        ISendEndpointProvider sendEndpointProvider,
        CancellationToken cancellationToken)
    {
        var job = await db.Jobs.FirstOrDefaultAsync(j => j.Id == id, cancellationToken);
        if (job is null)
            return Results.NotFound();

        var canExtract = job.VideoKey is not null
            && job.Status is JobStatus.AwaitingCrop or JobStatus.Completed or JobStatus.Failed;
        if (!canExtract)
            return Results.Conflict(new { error = $"Job in status {job.Status} cannot be extracted" });

        var crop = request.Crop is null
            ? job.SuggestedCrop?.Copy()
            : request.Crop.ToRegion();
        var errors = Validate(crop, request.StartSeconds, request.EndSeconds);
        if (errors.Count > 0)
            return Results.ValidationProblem(errors);

        job.Crop = crop;
        job.Layout = request.Layout ?? job.SuggestedLayout ?? SheetLayout.Pages;
        job.StartSeconds = request.StartSeconds;
        job.EndSeconds = request.EndSeconds;
        job.PdfKey = null;
        job.PageCount = null;
        job.Error = null;
        job.SetStatus(JobStatus.Extracting, "queued");

        var endpoint = await sendEndpointProvider.GetSendEndpoint(new Uri($"queue:{Queues.ExtractNotes}"));
        await endpoint.Send(
            new ExtractNotes(
                job.Id,
                job.VideoKey!,
                crop!.ToMessage(),
                LayoutNames.ToName(job.Layout.Value),
                job.StartSeconds,
                job.EndSeconds),
            cancellationToken);
        await db.SaveChangesAsync(cancellationToken);

        return Results.AcceptedAtRoute(nameof(GetJob), new { id = job.Id }, JobResponse.From(job));
    }

    private static async Task<IResult> GetPreview(
        Guid id,
        int index,
        AppDbContext db,
        ObjectStorage storage,
        CancellationToken cancellationToken)
    {
        var keys = await db.Jobs.Where(j => j.Id == id).Select(j => j.PreviewKeys).FirstOrDefaultAsync(cancellationToken);
        if (keys is null || index < 0 || index >= keys.Count)
            return Results.NotFound();

        var stored = await storage.OpenAsync(keys[index], cancellationToken);
        return stored is null ? Results.NotFound() : Results.Stream(stored.Content, stored.ContentType);
    }

    private static async Task<IResult> GetPdf(
        Guid id,
        AppDbContext db,
        ObjectStorage storage,
        CancellationToken cancellationToken)
    {
        var job = await db.Jobs.AsNoTracking()
            .Where(j => j.Id == id)
            .Select(j => new { j.PdfKey, j.Title })
            .FirstOrDefaultAsync(cancellationToken);
        if (job?.PdfKey is null)
            return Results.NotFound();

        var stored = await storage.OpenAsync(job.PdfKey, cancellationToken);
        if (stored is null)
            return Results.NotFound();

        var fileName = $"{SanitizeFileName(job.Title) ?? id.ToString()}.pdf";
        return Results.Stream(stored.Content, "application/pdf", fileName);
    }

    private static Dictionary<string, string[]> Validate(CropRegion? crop, double? start, double? end)
    {
        var errors = new Dictionary<string, string[]>();
        if (crop is null)
        {
            errors["crop"] = ["Crop is required"];
        }
        else if (crop.X < 0 || crop.Y < 0 || crop.Width <= 0 || crop.Height <= 0
                 || crop.X + crop.Width > 1.0001 || crop.Y + crop.Height > 1.0001)
        {
            errors["crop"] = ["Crop must be relative coordinates within [0, 1]"];
        }

        if (start < 0)
            errors["startSeconds"] = ["Must be non-negative"];
        if (start is not null && end is not null && end <= start)
            errors["endSeconds"] = ["Must be greater than startSeconds"];
        return errors;
    }

    private static string? SanitizeFileName(string? title)
    {
        if (string.IsNullOrWhiteSpace(title))
            return null;
        var invalid = Path.GetInvalidFileNameChars();
        var cleaned = new string(title.Select(c => invalid.Contains(c) ? '_' : c).ToArray()).Trim();
        return cleaned.Length == 0 ? null : cleaned[..Math.Min(cleaned.Length, 100)];
    }
}
