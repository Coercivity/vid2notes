using MassTransit;
using Microsoft.EntityFrameworkCore;
using Vid2Notes.Api.Contracts;
using Vid2Notes.Api.Data;
using Vid2Notes.Api.Endpoints.Models;
using Vid2Notes.Api.Storage;

namespace Vid2Notes.Api.Endpoints;

public static class JobEndpoints
{
    private const double MinTempo = 20;
    private const double MaxTempo = 300;

    public static void MapJobEndpoints(this IEndpointRouteBuilder app)
    {
        var jobs = app.MapGroup("/jobs").WithTags("Jobs");

        jobs.MapPost("/", CreateJob);
        jobs.MapGet("/{id:guid}", GetJob).WithName(nameof(GetJob));
        jobs.MapPost("/{id:guid}/extract", StartExtraction);
        jobs.MapGet("/{id:guid}/previews/{index:int}", GetPreview);
        jobs.MapGet("/{id:guid}/pdf", GetPdf);
        jobs.MapGet("/{id:guid}/midi", GetMidi);
        jobs.MapGet("/{id:guid}/musicxml", GetMusicXml);
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
        var errors = Validate(crop, request);
        if (errors.Count > 0)
            return Results.ValidationProblem(errors);

        job.Crop = crop;
        job.Layout = request.Layout ?? job.SuggestedLayout ?? SheetLayout.Pages;
        job.StartSeconds = request.StartSeconds;
        job.EndSeconds = request.EndSeconds;
        job.PdfKey = null;
        job.PageCount = null;
        job.MidiKey = null;
        job.NoteCount = null;
        job.MusicXmlKey = null;
        job.Tempo = null;
        job.TimeSignature = null;
        job.KeyName = null;
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
                job.EndSeconds,
                job.Title,
                request.Tempo,
                request.BeatsPerBar),
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
            .Select(j => new { Key = j.PdfKey, j.Title })
            .FirstOrDefaultAsync(cancellationToken);
        return await Download(id, job?.Key, job?.Title, "pdf", "application/pdf", storage, cancellationToken);
    }

    private static async Task<IResult> GetMidi(
        Guid id,
        AppDbContext db,
        ObjectStorage storage,
        CancellationToken cancellationToken)
    {
        var job = await db.Jobs.AsNoTracking()
            .Where(j => j.Id == id)
            .Select(j => new { Key = j.MidiKey, j.Title })
            .FirstOrDefaultAsync(cancellationToken);
        return await Download(id, job?.Key, job?.Title, "mid", "audio/midi", storage, cancellationToken);
    }

    private static async Task<IResult> GetMusicXml(
        Guid id,
        AppDbContext db,
        ObjectStorage storage,
        CancellationToken cancellationToken)
    {
        var job = await db.Jobs.AsNoTracking()
            .Where(j => j.Id == id)
            .Select(j => new { Key = j.MusicXmlKey, j.Title })
            .FirstOrDefaultAsync(cancellationToken);
        return await Download(
            id,
            job?.Key,
            job?.Title,
            "musicxml",
            "application/vnd.recordare.musicxml+xml",
            storage,
            cancellationToken);
    }

    private static async Task<IResult> Download(
        Guid id,
        string? key,
        string? title,
        string extension,
        string contentType,
        ObjectStorage storage,
        CancellationToken cancellationToken)
    {
        if (key is null)
            return Results.NotFound();

        var stored = await storage.OpenAsync(key, cancellationToken);
        if (stored is null)
            return Results.NotFound();

        var fileName = $"{SanitizeFileName(title) ?? id.ToString()}.{extension}";
        return Results.Stream(stored.Content, contentType, fileName);
    }

    private static Dictionary<string, string[]> Validate(CropRegion? crop, ExtractRequest request)
    {
        var start = request.StartSeconds;
        var end = request.EndSeconds;
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
        if (request.Tempo is < MinTempo or > MaxTempo)
            errors["tempo"] = [$"Must be between {MinTempo} and {MaxTempo} BPM"];
        if (request.BeatsPerBar is < 2 or > 12)
            errors["beatsPerBar"] = ["Must be between 2 and 12"];
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
