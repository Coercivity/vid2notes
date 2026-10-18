namespace Vid2Notes.Api.Contracts;

public record ExtractNotes(
    Guid JobId,
    string VideoKey,
    CropMessage Crop,
    string Layout,
    double? StartSeconds,
    double? EndSeconds,
    string? Title,
    double? Tempo,
    int? BeatsPerBar);
