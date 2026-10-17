using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Endpoints.Models;

public record JobResponse(
    Guid Id,
    string Url,
    JobStatus Status,
    string? Stage,
    int Progress,
    string? Title,
    double? DurationSeconds,
    int? Width,
    int? Height,
    IReadOnlyList<string> Previews,
    SheetLayout? SuggestedLayout,
    CropDto? SuggestedCrop,
    SheetLayout? Layout,
    CropDto? Crop,
    double? StartSeconds,
    double? EndSeconds,
    string? PdfUrl,
    int? PageCount,
    string? Error,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt)
{
    public static JobResponse From(Job job) => new(
        job.Id,
        job.Url,
        job.Status,
        job.Stage,
        job.Progress,
        job.Title,
        job.DurationSeconds,
        job.Width,
        job.Height,
        job.PreviewKeys.Select((_, index) => $"/jobs/{job.Id}/previews/{index}").ToList(),
        job.SuggestedLayout,
        CropDto.From(job.SuggestedCrop),
        job.Layout,
        CropDto.From(job.Crop),
        job.StartSeconds,
        job.EndSeconds,
        job.PdfKey is null ? null : $"/jobs/{job.Id}/pdf",
        job.PageCount,
        job.Error,
        job.CreatedAt,
        job.UpdatedAt);
}
