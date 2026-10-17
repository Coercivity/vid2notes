namespace Vid2Notes.Api.Contracts;

public record AnalysisCompleted(
    Guid JobId,
    string? Title,
    double DurationSeconds,
    int Width,
    int Height,
    string VideoKey,
    IReadOnlyList<string> PreviewKeys,
    CropMessage SuggestedCrop,
    string SuggestedLayout);
