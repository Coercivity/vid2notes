namespace Vid2Notes.Api.Data;

public class Job
{
    public Guid Id { get; set; }
    public required string Url { get; set; }
    public JobStatus Status { get; set; }
    public string? Stage { get; set; }
    public int Progress { get; set; }
    public string? Title { get; set; }
    public double? DurationSeconds { get; set; }
    public int? Width { get; set; }
    public int? Height { get; set; }
    public string? VideoKey { get; set; }
    public List<string> PreviewKeys { get; set; } = [];
    public SheetLayout? SuggestedLayout { get; set; }
    public CropRegion? SuggestedCrop { get; set; }
    public SheetLayout? Layout { get; set; }
    public CropRegion? Crop { get; set; }
    public double? StartSeconds { get; set; }
    public double? EndSeconds { get; set; }
    public string? PdfKey { get; set; }
    public int? PageCount { get; set; }
    public string? MidiKey { get; set; }
    public int? NoteCount { get; set; }
    public string? MusicXmlKey { get; set; }
    public double? Tempo { get; set; }
    public string? TimeSignature { get; set; }
    public string? KeyName { get; set; }
    public string? Error { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }

    public void SetStatus(JobStatus status, string? stage = null, int progress = 0)
    {
        Status = status;
        Stage = stage;
        Progress = progress;
        UpdatedAt = DateTimeOffset.UtcNow;
    }
}
