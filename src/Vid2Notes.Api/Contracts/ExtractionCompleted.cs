namespace Vid2Notes.Api.Contracts;

public record ExtractionCompleted(Guid JobId, string PdfKey, int PageCount);
