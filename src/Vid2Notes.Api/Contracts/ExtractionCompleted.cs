namespace Vid2Notes.Api.Contracts;

public record ExtractionCompleted(
    Guid JobId,
    string? PdfKey,
    int? PageCount,
    string? MidiKey,
    int? NoteCount,
    string? MusicXmlKey,
    double? Tempo,
    string? TimeSignature,
    string? KeyName);
