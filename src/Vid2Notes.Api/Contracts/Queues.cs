namespace Vid2Notes.Api.Contracts;

public static class Queues
{
    public const string AnalyzeVideo = "analyze-video";
    public const string ExtractNotes = "extract-notes";
    public const string JobProgress = "job-progress";
    public const string AnalysisCompleted = "analysis-completed";
    public const string ExtractionCompleted = "extraction-completed";
    public const string JobFailed = "job-failed";
}
